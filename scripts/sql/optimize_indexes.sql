-- ============================================================
-- optimize_indexes.sql
-- Tối ưu PostgreSQL bằng B-Tree Index trên các cột hay dùng
-- để JOIN, WHERE, và ORDER BY trong Silver + Gold schema.
--
-- Chạy: psql -U <user> -d <db> -f scripts/sql/optimize_indexes.sql
-- Lưu ý: CREATE INDEX CONCURRENTLY không block reads, nhưng
--         KHÔNG thể chạy bên trong transaction block.
--         Script này dùng CONCURRENTLY để an toàn trên production.
-- ============================================================


-- ─────────────────────────────────────────────────────────────
-- SILVER SCHEMA
-- ─────────────────────────────────────────────────────────────

-- jobs: FK lookups (company_id, source_id) + filter thường gặp
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jobs_company_id
    ON silver.jobs (company_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jobs_source_id
    ON silver.jobs (source_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jobs_is_active
    ON silver.jobs (is_active)
    WHERE is_active = TRUE;  -- Partial index — chỉ index những job đang ACTIVE

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jobs_duplicate_group_id
    ON silver.jobs (duplicate_group_id)
    WHERE duplicate_group_id IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jobs_created_at
    ON silver.jobs (created_at DESC);

-- job_snapshots: current version lookups
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_snapshots_job_id_current
    ON silver.job_snapshots (job_id)
    WHERE is_current = TRUE;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jobs_identity_hash
    ON silver.jobs (identity_hash);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_snapshots_content_hash
    ON silver.job_snapshots (content_hash);

-- Full-Text Search trên title (GIN index cho tìm kiếm từ khóa nhanh)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_snapshots_title_fts
    ON silver.job_snapshots USING GIN (to_tsvector('english', COALESCE(title_clean, '')));

-- job_snapshot_skills: FK lookups
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_snapshot_skills_snapshot_id
    ON silver.job_snapshot_skills (snapshot_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_snapshot_skills_skill_id
    ON silver.job_snapshot_skills (skill_id);

-- crawl_sessions: date lookup
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_crawl_sessions_run_date
    ON silver.crawl_sessions (run_date DESC);

-- ─────────────────────────────────────────────────────────────
-- DWH (GOLD) SCHEMA
-- ─────────────────────────────────────────────────────────────

-- fact_job_posting: cột JOIN + filter quan trọng nhất
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fact_job_company_id
    ON dwh.fact_job_posting (company_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fact_job_source_id
    ON dwh.fact_job_posting (source_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fact_job_posted_date
    ON dwh.fact_job_posting (posted_date DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fact_job_is_active
    ON dwh.fact_job_posting (is_active)
    WHERE is_active = TRUE;

-- Composite index cho query phổ biến: lọc theo company + ngày
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fact_job_company_date
    ON dwh.fact_job_posting (company_id, posted_date DESC);

-- dim_company: tên công ty
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_dim_company_name
    ON dwh.dim_company (company_name);

-- dim_company: Full-Text Search
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_dim_company_fts
    ON dwh.dim_company USING GIN (to_tsvector('simple', COALESCE(company_name, '')));

-- ─────────────────────────────────────────────────────────────
-- STAGING SCHEMA
-- ─────────────────────────────────────────────────────────────

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_stg_jobs_batch_date
    ON staging.stg_jobs (batch_date DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_stg_jobs_identity_hash
    ON staging.stg_jobs (identity_hash);

-- ─────────────────────────────────────────────────────────────
-- Verify: xem danh sách index đã tạo
-- ─────────────────────────────────────────────────────────────
-- SELECT schemaname, tablename, indexname, indexdef
-- FROM pg_indexes
-- WHERE schemaname IN ('silver', 'dwh', 'staging')
-- ORDER BY schemaname, tablename;
