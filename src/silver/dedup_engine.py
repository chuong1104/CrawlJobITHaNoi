import logging
import pandas as pd
import warnings

logger = logging.getLogger(__name__)

class CrossSourceDedupEngine:
    """
    Thực hiện gom cụm các tin tuyển dụng giống nhau giữa các nguồn.
    Phase 1: Gom cụm chính xác (Exact match) dựa trên identity_hash và content_hash.
    Phase 2: Sử dụng TF-IDF và Cosine Similarity trên title và description.
    """
    def __init__(self, pg_conn):
        self.pg_conn = pg_conn

    def run_deduplication(self, similarity_threshold: float = 0.85):
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
        except ImportError:
            logger.error("scikit-learn is required for deduplication. Skipping.")
            return

        logger.info("Starting cross-source deduplication...")
        
        # 1. Lấy danh sách các jobs đang ACTIVE, gom nhóm theo công ty
        query = """
            SELECT j.job_id, j.company_id, j.source_id, j.identity_hash, 
                   s.content_hash, s.title_clean, s.description
            FROM silver.jobs j
            JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = TRUE
            WHERE j.is_active = TRUE AND j.duplicate_group_id IS NULL
        """
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            try:
                df = pd.read_sql(query, self.pg_conn)
            except Exception as e:
                logger.error(f"Error fetching jobs for deduplication: {e}")
                return
            
        if df.empty:
            logger.info("No active ungrouped jobs found for deduplication.")
            return

        new_groups_created = 0
        new_members_added = 0

        grouped = df.groupby('company_id')
        vectorizer = TfidfVectorizer(stop_words='english', max_features=1000)

        with self.pg_conn.cursor() as cur:
            from psycopg2.extras import execute_values
            
            # Lists for batch inserts/updates
            new_groups = []
            new_members = []
            updates_to_jobs = []

            for company_id, group_df in grouped:
                if len(group_df) < 2:
                    continue
                    
                group_df = group_df.reset_index(drop=True)
                processed_indices = set()
                
                # --- PHASE 1: HASH MATCHING ---
                for i in range(len(group_df)):
                    if i in processed_indices:
                        continue
                        
                    similar_indices = [i]
                    id_hash_i = group_df.loc[i, 'identity_hash']
                    content_hash_i = group_df.loc[i, 'content_hash']
                    
                    for j in range(i + 1, len(group_df)):
                        if j not in processed_indices:
                            id_hash_j = group_df.loc[j, 'identity_hash']
                            content_hash_j = group_df.loc[j, 'content_hash']
                            
                            if (id_hash_i == id_hash_j) or (content_hash_i == content_hash_j):
                                similar_indices.append(j)
                                
                    if len(similar_indices) > 1:
                        title_clean = str(group_df.loc[i, 'title_clean'])
                        group_name = f"Exact Hash Match {title_clean[:40]}"
                        canonical_job_id = int(group_df.loc[i, 'job_id'])
                        
                        cur.execute("""
                            INSERT INTO silver.job_duplicate_groups (canonical_job_id, group_name)
                            VALUES (%s, %s) RETURNING group_id
                        """, (canonical_job_id, group_name))
                        group_id = cur.fetchone()[0]
                        new_groups_created += 1
                        
                        for idx in similar_indices:
                            job_id = int(group_df.loc[idx, 'job_id'])
                            new_members.append((group_id, job_id, 1.0, 'hash_exact'))
                            updates_to_jobs.append((group_id, job_id))
                            processed_indices.add(idx)
                            new_members_added += 1
                            
                # --- PHASE 2: TF-IDF COSINE SIMILARITY ---
                remaining_indices = [idx for idx in range(len(group_df)) if idx not in processed_indices]
                if len(remaining_indices) < 2:
                    continue
                    
                texts = (group_df['title_clean'].fillna('') + " " + group_df['description'].fillna('')).tolist()
                try:
                    tfidf_matrix = vectorizer.fit_transform(texts)
                    cosine_sim = cosine_similarity(tfidf_matrix)
                except ValueError:
                    continue
                
                for i in remaining_indices:
                    if i in processed_indices:
                        continue
                        
                    similar_indices_tf = [i]
                    for j in remaining_indices:
                        if j > i and j not in processed_indices and cosine_sim[i, j] >= similarity_threshold:
                            similar_indices_tf.append(j)
                            
                    if len(similar_indices_tf) > 1:
                        title_clean = str(group_df.loc[i, 'title_clean'])
                        group_name = f"Duplicated {title_clean[:50]}"
                        canonical_job_id = int(group_df.loc[i, 'job_id'])
                        
                        cur.execute("""
                            INSERT INTO silver.job_duplicate_groups (canonical_job_id, group_name)
                            VALUES (%s, %s) RETURNING group_id
                        """, (canonical_job_id, group_name))
                        group_id = cur.fetchone()[0]
                        new_groups_created += 1
                        
                        for idx in similar_indices_tf:
                            job_id = int(group_df.loc[idx, 'job_id'])
                            score = float(cosine_sim[i, idx]) if idx != i else 1.0
                            new_members.append((group_id, job_id, score, 'tfidf_cosine'))
                            updates_to_jobs.append((group_id, job_id))
                            processed_indices.add(idx)
                            new_members_added += 1

            # Execute bulk operations
            if new_members:
                execute_values(cur, """
                    INSERT INTO silver.job_duplicate_group_members (group_id, job_id, similarity_score, match_method)
                    VALUES %s ON CONFLICT DO NOTHING
                """, new_members)
                
            if updates_to_jobs:
                execute_values(cur, """
                    UPDATE silver.jobs AS j 
                    SET duplicate_group_id = v.group_id 
                    FROM (VALUES %s) AS v(group_id, job_id)
                    WHERE j.job_id = v.job_id
                """, updates_to_jobs)

            self.pg_conn.commit()
            logger.info(f"Deduplication complete. Created {new_groups_created} new groups, added {new_members_added} members.")


class JobDedupEngine:
    def __init__(self):
        self.pg_conn = None

    def connect(self):
        import psycopg2
        from src.config import DBConfig
        self.pg_conn = psycopg2.connect(DBConfig.dsn())

    def close(self):
        if self.pg_conn:
            self.pg_conn.close()

    def run_dedup_pipeline(self, session_id: int):
        engine = CrossSourceDedupEngine(self.pg_conn)
        engine.run_deduplication()

