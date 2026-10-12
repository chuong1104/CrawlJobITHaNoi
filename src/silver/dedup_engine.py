"""
dedup_engine.py — Gom cụm tin tuyển dụng trùng lặp cross-source.

Cải tiến v2.0 (Memory Management):
  - Thay vì load toàn bộ bảng jobs lên RAM bằng pd.read_sql(), giờ
    chỉ kéo DANH SÁCH company_id cần xử lý trước, sau đó lặp qua từng
    company (hoặc từng batch công ty) — chỉ load dữ liệu của nhóm đó lên RAM.
  - Giảm mức sử dụng RAM từ O(n_all_jobs) xuống O(n_jobs_per_company).
  - Dùng cursor-based fetch thay vì pd.read_sql() toàn bảng.
  - Thêm batch commit sau mỗi BATCH_SIZE công ty để tránh transaction quá lớn.
"""
import logging
import pandas as pd
import warnings
from typing import Optional

logger = logging.getLogger(__name__)

# Số công ty xử lý mỗi vòng lặp (điều chỉnh theo RAM máy chủ)
_COMPANY_BATCH_SIZE = 50


class CrossSourceDedupEngine:
    """
    Thực hiện gom cụm các tin tuyển dụng giống nhau giữa các nguồn.
    Phase 1: Gom cụm chính xác (Exact match) dựa trên identity_hash và content_hash.
    Phase 2: Sử dụng TF-IDF và Cosine Similarity trên title và description.
    """

    def __init__(self, pg_conn):
        self.pg_conn = pg_conn

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _get_company_ids(self) -> list[int]:
        """
        Lấy danh sách company_id có ít nhất 2 job active chưa được gom nhóm.
        Trả về list để lặp theo từng batch nhỏ, không load toàn bộ jobs.
        """
        query = """
            SELECT j.company_id
            FROM silver.jobs j
            JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = TRUE
            WHERE j.is_active = TRUE AND j.duplicate_group_id IS NULL
            GROUP BY j.company_id
            HAVING COUNT(*) >= 2
            ORDER BY COUNT(*) DESC
        """
        with self.pg_conn.cursor() as cur:
            cur.execute(query)
            return [row[0] for row in cur.fetchall()]

    def _fetch_jobs_for_companies(self, company_ids: list[int]) -> pd.DataFrame:
        """
        Lấy dữ liệu jobs của một batch company_ids cụ thể.
        Dùng IN clause với placeholders để tránh SQL injection.
        """
        if not company_ids:
            return pd.DataFrame()

        placeholders = ",".join(["%s"] * len(company_ids))
        query = f"""
            SELECT j.job_id, j.company_id, j.source_id, j.identity_hash,
                   s.content_hash, s.title_clean, s.description
            FROM silver.jobs j
            JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = TRUE
            WHERE j.is_active = TRUE
              AND j.duplicate_group_id IS NULL
              AND j.company_id IN ({placeholders})
        """
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                with self.pg_conn.cursor() as cur:
                    cur.execute(query, company_ids)
                    cols = [desc[0] for desc in cur.description]
                    rows = cur.fetchall()
                    return pd.DataFrame(rows, columns=cols)
            except Exception as e:
                logger.error(f"Lỗi khi fetch jobs cho companies {company_ids[:5]}...: {e}")
                return pd.DataFrame()

    def _process_company_group(
        self,
        company_id: int,
        group_df: pd.DataFrame,
        cur,
        vectorizer,
        similarity_threshold: float,
    ) -> tuple[int, int]:
        """
        Xử lý dedup cho một công ty cụ thể.
        Trả về (new_groups_created, new_members_added).
        """
        from psycopg2.extras import execute_values

        if len(group_df) < 2:
            return 0, 0

        group_df = group_df.reset_index(drop=True)
        processed_indices: set[int] = set()
        new_groups_created = 0
        new_members_added = 0

        new_groups: list = []
        new_members: list = []
        updates_to_jobs: list = []

        # --- PHASE 1: HASH MATCHING ---
        for i in range(len(group_df)):
            if i in processed_indices:
                continue

            similar_indices = [i]
            id_hash_i = group_df.loc[i, "identity_hash"]
            content_hash_i = group_df.loc[i, "content_hash"]

            for j in range(i + 1, len(group_df)):
                if j not in processed_indices:
                    id_hash_j = group_df.loc[j, "identity_hash"]
                    content_hash_j = group_df.loc[j, "content_hash"]
                    if (id_hash_i == id_hash_j) or (content_hash_i == content_hash_j):
                        similar_indices.append(j)

            if len(similar_indices) > 1:
                title_clean = str(group_df.loc[i, "title_clean"])
                group_name = f"Exact Hash Match {title_clean[:40]}"
                canonical_job_id = int(group_df.loc[i, "job_id"])

                cur.execute(
                    """
                    INSERT INTO silver.job_duplicate_groups (canonical_job_id, group_name)
                    VALUES (%s, %s) RETURNING group_id
                    """,
                    (canonical_job_id, group_name),
                )
                group_id = cur.fetchone()[0]
                new_groups_created += 1

                for idx in similar_indices:
                    job_id = int(group_df.loc[idx, "job_id"])
                    new_members.append((group_id, job_id, 1.0, "hash_exact"))
                    updates_to_jobs.append((group_id, job_id))
                    processed_indices.add(idx)
                    new_members_added += 1

        # --- PHASE 2: TF-IDF COSINE SIMILARITY ---
        try:
            from sklearn.metrics.pairwise import cosine_similarity
        except ImportError:
            logger.warning("scikit-learn không tìm thấy — bỏ qua Phase 2 TF-IDF.")
            self._flush_batch(cur, new_members, updates_to_jobs)
            return new_groups_created, new_members_added

        remaining_indices = [idx for idx in range(len(group_df)) if idx not in processed_indices]
        if len(remaining_indices) >= 2:
            texts = (
                group_df["title_clean"].fillna("") + " " + group_df["description"].fillna("")
            ).tolist()
            try:
                tfidf_matrix = vectorizer.fit_transform(
                    [texts[i] for i in remaining_indices]
                )
                cosine_sim = cosine_similarity(tfidf_matrix)

                for ri, i in enumerate(remaining_indices):
                    if i in processed_indices:
                        continue
                    similar_indices_tf = [i]
                    for rj, j in enumerate(remaining_indices):
                        if j > i and j not in processed_indices:
                            if cosine_sim[ri, rj] >= similarity_threshold:
                                similar_indices_tf.append(j)

                    if len(similar_indices_tf) > 1:
                        title_clean = str(group_df.loc[i, "title_clean"])
                        group_name = f"Duplicated {title_clean[:50]}"
                        canonical_job_id = int(group_df.loc[i, "job_id"])

                        cur.execute(
                            """
                            INSERT INTO silver.job_duplicate_groups (canonical_job_id, group_name)
                            VALUES (%s, %s) RETURNING group_id
                            """,
                            (canonical_job_id, group_name),
                        )
                        group_id = cur.fetchone()[0]
                        new_groups_created += 1

                        for idx in similar_indices_tf:
                            job_id = int(group_df.loc[idx, "job_id"])
                            ri_idx = remaining_indices.index(i)
                            rj_idx = remaining_indices.index(idx) if idx in remaining_indices else ri_idx
                            score = float(cosine_sim[ri_idx, rj_idx]) if idx != i else 1.0
                            new_members.append((group_id, job_id, score, "tfidf_cosine"))
                            updates_to_jobs.append((group_id, job_id))
                            processed_indices.add(idx)
                            new_members_added += 1

            except ValueError:
                pass  # Không đủ văn bản để vectorize

        # Flush batch inserts/updates cho công ty này
        self._flush_batch(cur, new_members, updates_to_jobs)
        return new_groups_created, new_members_added

    @staticmethod
    def _flush_batch(cur, new_members: list, updates_to_jobs: list) -> None:
        """Thực thi bulk INSERT/UPDATE đã tích lũy trong vòng lặp."""
        from psycopg2.extras import execute_values

        if new_members:
            execute_values(
                cur,
                """
                INSERT INTO silver.job_duplicate_group_members
                    (group_id, job_id, similarity_score, match_method)
                VALUES %s ON CONFLICT DO NOTHING
                """,
                new_members,
            )

        if updates_to_jobs:
            execute_values(
                cur,
                """
                UPDATE silver.jobs AS j
                SET duplicate_group_id = v.group_id
                FROM (VALUES %s) AS v(group_id, job_id)
                WHERE j.job_id = v.job_id
                """,
                updates_to_jobs,
            )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def run_deduplication(self, similarity_threshold: float = 0.85) -> None:
        """
        Chạy toàn bộ pipeline dedup theo cơ chế chunked company batches.

        Thay vì load toàn bộ jobs lên RAM:
          1. Lấy danh sách company_id có nhiều jobs active.
          2. Chia thành batch nhỏ (COMPANY_BATCH_SIZE công ty/batch).
          3. Mỗi batch: fetch data, xử lý dedup, commit, giải phóng RAM.
        """
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
        except ImportError:
            logger.error("scikit-learn chưa được cài. Bỏ qua deduplication.")
            return

        logger.info("Bắt đầu cross-source deduplication (chunked by company)...")

        company_ids = self._get_company_ids()
        if not company_ids:
            logger.info("Không có công ty nào cần dedup.")
            return

        logger.info(f"Tìm thấy {len(company_ids)} công ty cần xử lý dedup.")

        total_groups = 0
        total_members = 0
        vectorizer = TfidfVectorizer(stop_words="english", max_features=1000)

        # Xử lý theo batch để kiểm soát RAM
        for batch_start in range(0, len(company_ids), _COMPANY_BATCH_SIZE):
            batch_ids = company_ids[batch_start: batch_start + _COMPANY_BATCH_SIZE]
            batch_num = batch_start // _COMPANY_BATCH_SIZE + 1
            total_batches = (len(company_ids) + _COMPANY_BATCH_SIZE - 1) // _COMPANY_BATCH_SIZE

            logger.info(
                f"Xử lý batch {batch_num}/{total_batches} "
                f"({len(batch_ids)} công ty, IDs: {batch_ids[:3]}...)"
            )

            # Fetch chỉ data của batch này
            batch_df = self._fetch_jobs_for_companies(batch_ids)
            if batch_df.empty:
                continue

            batch_groups = 0
            batch_members = 0

            with self.pg_conn.cursor() as cur:
                for company_id in batch_ids:
                    group_df = batch_df[batch_df["company_id"] == company_id].copy()
                    if len(group_df) < 2:
                        continue

                    g, m = self._process_company_group(
                        company_id=company_id,
                        group_df=group_df,
                        cur=cur,
                        vectorizer=vectorizer,
                        similarity_threshold=similarity_threshold,
                    )
                    batch_groups += g
                    batch_members += m

            # Commit sau mỗi batch để tránh transaction quá lớn
            self.pg_conn.commit()
            total_groups += batch_groups
            total_members += batch_members

            logger.info(
                f"  Batch {batch_num} xong: +{batch_groups} groups, +{batch_members} members"
            )

            # Giải phóng RAM của batch này trước khi xử lý batch tiếp theo
            del batch_df

        logger.info(
            f"Deduplication hoàn thành. "
            f"Tổng: {total_groups} groups mới, {total_members} members mới."
        )


# ---------------------------------------------------------------------------
# Public wrapper (entry point từ Airflow task)
# ---------------------------------------------------------------------------
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
