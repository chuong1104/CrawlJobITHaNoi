-- =============================================================================
-- 02_create_materialized_views.sql
-- Materialized Views cho PostgreSQL DWH — Tối ưu query performance cho Power BI
-- và FastAPI serving layer.
--
-- Các view này được REFRESH CONCURRENTLY mỗi ngày sau khi pipeline hoàn thành.
-- Consumer (Power BI, FastAPI) đọc từ đây thay vì query trực tiếp fct_job_posting.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. mv_active_jobs_summary — Snapshot nhanh tất cả jobs đang tuyển
--    Phục vụ: FastAPI /api/jobs endpoint (< 100ms với index)
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS dwh.mv_active_jobs_summary AS
SELECT
    f.silver_job_id          AS job_id,
    c.silver_company_id      AS company_id,
    ds.silver_source_id      AS source_id,
    jb.canonical_url,
    jb.job_status,
    f.silver_snapshot_id     AS snapshot_id,
    js.title_clean,
    f.salary_min_vnd         AS salary_min,
    f.salary_max_vnd         AS salary_max,
    f.salary_midpoint_vnd    AS salary_avg,
    js.salary_currency,
    f.experience_min_years,
    f.experience_max_years,
    a.job_level,
    a.job_type,
    a.work_mode,
    js.job_family,
    CAST(TO_CHAR(js.deadline_date, 'YYYYMMDD') AS INT) AS deadline_date_key,
    f.is_intern,
    f.is_fresher,
    CAST(TO_CHAR(jb.first_seen_at, 'YYYYMMDD') AS INT) AS first_seen_date_key,
    CAST(TO_CHAR(jb.last_seen_at, 'YYYYMMDD') AS INT) AS last_seen_date_key,
    -- Denormalized company info (tránh JOIN khi query)
    c.company_name          AS company_name,
    c.industry              AS company_industry,
    c.company_name          AS company_normalized_name
FROM dwh.fct_job_posting f
JOIN dwh.dim_company c ON f.company_key = c.company_key
JOIN dwh.dim_source ds ON f.source_key = ds.source_key
JOIN dwh.dim_job_attributes a ON f.attribute_key = a.attribute_key
JOIN silver.jobs jb ON f.silver_job_id = jb.job_id
JOIN silver.job_snapshots js ON f.silver_snapshot_id = js.snapshot_id
WHERE f.is_active = TRUE AND js.is_current = TRUE
WITH DATA;

COMMENT ON MATERIALIZED VIEW dwh.mv_active_jobs_summary IS 
    'Cache tất cả jobs đang tuyển với company info denormalized. Refresh sau mỗi pipeline run.';

-- Index trên mv_active_jobs_summary
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_active_jobs_pk
    ON dwh.mv_active_jobs_summary (job_id);
CREATE INDEX IF NOT EXISTS idx_mv_active_jobs_company
    ON dwh.mv_active_jobs_summary (company_id);
CREATE INDEX IF NOT EXISTS idx_mv_active_jobs_family
    ON dwh.mv_active_jobs_summary (job_family);
CREATE INDEX IF NOT EXISTS idx_mv_active_jobs_level
    ON dwh.mv_active_jobs_summary (job_level);
CREATE INDEX IF NOT EXISTS idx_mv_active_jobs_salary
    ON dwh.mv_active_jobs_summary (salary_avg) WHERE salary_avg IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 2. mv_kpi_realtime — KPI market hiện tại
--    Phục vụ: Power BI Dashboard cards (tổng việc, lương TB, fresher ratio)
--    Tương ứng với các metrics trong sem_job_market.yml
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS dwh.mv_kpi_realtime AS
SELECT
    NOW()                                       AS refreshed_at,
    -- Volume (sem: total_active_jobs, total_hiring_companies)
    COUNT(f.silver_job_id)                      AS total_active_jobs,
    COUNT(DISTINCT f.company_key)               AS total_hiring_companies,
    -- Salary (sem: market_avg_salary, salary_disclosure_rate)
    ROUND(AVG(f.salary_midpoint_vnd))           AS market_avg_salary_vnd,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY f.salary_midpoint_vnd)
                                                AS market_median_salary_vnd,
    ROUND(
        COUNT(CASE WHEN f.salary_midpoint_vnd IS NOT NULL THEN 1 END) * 100.0
        / NULLIF(COUNT(*), 0), 2
    )                                           AS salary_disclosure_rate_pct,
    -- Segments (sem: fresher_job_ratio, remote_job_count)
    COUNT(CASE WHEN f.is_fresher OR a.job_level = 'FRESHER' THEN 1 END)
                                                AS total_fresher_jobs,
    COUNT(CASE WHEN f.is_intern OR a.job_level = 'INTERN' THEN 1 END)
                                                AS total_intern_jobs,
    COUNT(CASE WHEN a.work_mode IN ('REMOTE', 'HYBRID') THEN 1 END)
                                                AS total_remote_hybrid_jobs,
    -- Job Family Breakdown (sem: data_jobs_count, backend_jobs_count)
    COUNT(CASE WHEN js.job_family = 'DATA_ENGINEER'  THEN 1 END) AS jobs_data_engineer,
    COUNT(CASE WHEN js.job_family = 'DATA_ANALYST'   THEN 1 END) AS jobs_data_analyst,
    COUNT(CASE WHEN js.job_family = 'BACKEND'        THEN 1 END) AS jobs_backend,
    COUNT(CASE WHEN js.job_family = 'FRONTEND'       THEN 1 END) AS jobs_frontend,
    COUNT(CASE WHEN js.job_family = 'FULLSTACK'      THEN 1 END) AS jobs_fullstack
FROM dwh.fct_job_posting f
JOIN dwh.dim_job_attributes a ON f.attribute_key = a.attribute_key
JOIN silver.job_snapshots js ON f.silver_snapshot_id = js.snapshot_id
WHERE f.is_active = TRUE
WITH DATA;

COMMENT ON MATERIALIZED VIEW dwh.mv_kpi_realtime IS 
    'KPI thị trường real-time. Aligned với Semantic Layer metrics (sem_job_market.yml). Refresh concurrently.';

-- Index để refresh nhanh
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_kpi_realtime_pk
    ON dwh.mv_kpi_realtime (refreshed_at);

-- ---------------------------------------------------------------------------
-- 3. mv_salary_by_skill — Lương trung bình theo kỹ năng
--    Phục vụ: Power BI "Salary by Skill" chart — thường là query nặng nhất
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS dwh.mv_salary_by_skill AS
WITH skill_salary AS (
    SELECT
        sk.silver_skill_id                  AS skill_id,
        sk.skill_name                       AS skill_code,
        sk.skill_name                       AS skill_name,
        sk.skill_category,
        COUNT(f.silver_job_id)               AS job_count,
        AVG(f.salary_midpoint_vnd)          AS avg_salary,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY f.salary_midpoint_vnd)
                                            AS median_salary,
        MIN(f.salary_min_vnd)               AS min_salary,
        MAX(f.salary_max_vnd)               AS max_salary,
        COUNT(CASE WHEN f.salary_midpoint_vnd IS NOT NULL THEN 1 END)
                                            AS jobs_with_salary
    FROM dwh.bridge_job_skill fjs
    JOIN dwh.fct_job_posting f  ON fjs.job_posting_fact_id  = f.job_posting_fact_id
    JOIN dwh.dim_skill sk       ON fjs.skill_key = sk.skill_key
    WHERE f.is_active = TRUE
    GROUP BY sk.silver_skill_id, sk.skill_name, sk.skill_category
)
SELECT
    *,
    RANK() OVER (ORDER BY avg_salary DESC NULLS LAST)   AS salary_rank,
    RANK() OVER (ORDER BY job_count DESC)               AS demand_rank
FROM skill_salary
WHERE job_count >= 5  -- Chỉ include skills có đủ sample size
WITH DATA;

COMMENT ON MATERIALIZED VIEW dwh.mv_salary_by_skill IS 
    'Lương trung bình + median theo từng kỹ năng. Cache query nặng nhất của Power BI.';

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_salary_skill_pk
    ON dwh.mv_salary_by_skill (skill_id);
CREATE INDEX IF NOT EXISTS idx_mv_salary_skill_category
    ON dwh.mv_salary_by_skill (skill_category);

-- ---------------------------------------------------------------------------
-- 4. mv_jobs_by_location — Phân bổ việc làm theo địa điểm
--    Phục vụ: Power BI Map chart
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS dwh.mv_jobs_by_location AS
SELECT
    l.silver_location_id                    AS location_id,
    l.location_name                         AS location_code,
    l.location_name                         AS location_name,
    l.region,
    FALSE                                   AS is_remote,
    COUNT(f.silver_job_id)                   AS total_jobs,
    ROUND(AVG(f.salary_midpoint_vnd))       AS avg_salary,
    COUNT(DISTINCT f.company_key)           AS total_companies,
    COUNT(CASE WHEN f.is_fresher THEN 1 END)  AS fresher_jobs
FROM dwh.dim_location l
JOIN dwh.bridge_job_location fjl  ON l.location_key = fjl.location_key
JOIN dwh.fct_job_posting f        ON fjl.job_posting_fact_id = f.job_posting_fact_id
WHERE f.is_active = TRUE
GROUP BY l.silver_location_id, l.location_name, l.region
WITH DATA;

COMMENT ON MATERIALIZED VIEW dwh.mv_jobs_by_location IS 
    'Phân bổ job theo địa điểm. Dùng cho Power BI Map visualization.';

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_location_pk
    ON dwh.mv_jobs_by_location (location_id);

-- ---------------------------------------------------------------------------
-- Procedure: Refresh tất cả Materialized Views (gọi từ Airflow DAG)
-- CONCURRENTLY: không lock table, BI tools vẫn đọc được trong lúc refresh
-- ---------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE dwh.sp_refresh_all_materialized_views()
LANGUAGE plpgsql AS $$
BEGIN
    -- Thứ tự quan trọng: refresh mv_active_jobs_summary trước (dependency)
    REFRESH MATERIALIZED VIEW CONCURRENTLY dwh.mv_active_jobs_summary;
    REFRESH MATERIALIZED VIEW CONCURRENTLY dwh.mv_kpi_realtime;
    REFRESH MATERIALIZED VIEW CONCURRENTLY dwh.mv_salary_by_skill;
    REFRESH MATERIALIZED VIEW CONCURRENTLY dwh.mv_jobs_by_location;
    
    RAISE NOTICE 'All materialized views refreshed at %', NOW();
END;
$$;

COMMENT ON PROCEDURE dwh.sp_refresh_all_materialized_views IS 
    'Refresh CONCURRENTLY tất cả materialized views. Gọi từ Airflow task sau khi run_gold_dwh hoàn thành.';

COMMIT;

-- Verify: kiểm tra các views đã được tạo
SELECT 
    schemaname,
    matviewname,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||matviewname)) AS total_size,
    ispopulated
FROM pg_matviews
WHERE schemaname = 'dwh'
ORDER BY matviewname;
