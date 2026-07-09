{{ config(
    materialized='incremental',
    unique_key='report_date'
) }}

-- =============================================================================
-- kpi_daily_summary.sql — KPI Snapshot hàng ngày (nâng cấp v2.0)
-- 
-- Thay vì viết SQL inline, các KPI core được gọi từ fct_job_posting
-- và align với definitions trong sem_job_market.yml (Semantic Layer).
--
-- Tất cả consumer (Power BI, FastAPI) đều đọc bảng này — KHÔNG viết
-- SQL tùy tiện trên fct_job_posting nữa.
-- =============================================================================

-- depends_on: {{ ref('fct_job_posting') }}
-- depends_on: {{ ref('fct_job_skill') }}

WITH active_jobs AS (
    SELECT *
    FROM {{ ref('fct_job_posting') }}
    WHERE is_active = TRUE
),

-- Thống kê cơ bản (aligned với metrics: total_active_jobs, market_avg_salary...)
volume_stats AS (
    SELECT
        COUNT(DISTINCT job_id)      AS total_active_jobs,
        COUNT(DISTINCT company_id)  AS total_hiring_companies
    FROM active_jobs
),

-- Lương (aligned với metrics: market_avg_salary, salary_disclosure_rate)
salary_stats AS (
    SELECT
        AVG(salary_avg)             AS market_avg_salary,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY salary_avg)
                                    AS market_median_salary,
        COUNT(CASE WHEN salary_avg IS NOT NULL THEN 1 END) AS jobs_with_salary,
        ROUND(
            COUNT(CASE WHEN salary_avg IS NOT NULL THEN 1 END) * 100.0
            / NULLIF(COUNT(*), 0), 2
        )                           AS salary_disclosure_rate_pct
    FROM active_jobs
),

-- Phân khúc ứng viên (aligned với metrics: fresher_job_ratio, remote_job_count)
segment_stats AS (
    SELECT
        COUNT(CASE WHEN is_fresher = TRUE OR job_level = 'FRESHER' THEN 1 END)
                                    AS total_fresher_jobs,
        COUNT(CASE WHEN is_intern  = TRUE OR job_level = 'INTERN'  THEN 1 END)
                                    AS total_intern_jobs,
        COUNT(CASE WHEN work_mode IN ('REMOTE', 'HYBRID') THEN 1 END)
                                    AS total_remote_hybrid_jobs,
        ROUND(
            COUNT(CASE WHEN is_fresher = TRUE OR job_level = 'FRESHER' THEN 1 END) * 100.0
            / NULLIF(COUNT(*), 0), 2
        )                           AS fresher_ratio_pct
    FROM active_jobs
),

-- Job Family breakdown (aligned với metrics: data_jobs_count, backend_jobs_count)
family_stats AS (
    SELECT
        COUNT(CASE WHEN job_family = 'DATA_ENGINEER' THEN 1 END)  AS jobs_data_engineer,
        COUNT(CASE WHEN job_family = 'DATA_ANALYST'  THEN 1 END)  AS jobs_data_analyst,
        COUNT(CASE WHEN job_family = 'DATA_SCIENTIST' THEN 1 END) AS jobs_data_scientist,
        COUNT(CASE WHEN job_family = 'ML_ENGINEER'   THEN 1 END)  AS jobs_ml_engineer,
        COUNT(CASE WHEN job_family = 'BACKEND'       THEN 1 END)  AS jobs_backend,
        COUNT(CASE WHEN job_family = 'FRONTEND'      THEN 1 END)  AS jobs_frontend,
        COUNT(CASE WHEN job_family = 'FULLSTACK'     THEN 1 END)  AS jobs_fullstack
    FROM active_jobs
),

-- Mới hôm nay (aligned với metrics: new_jobs_today)
daily_delta AS (
    SELECT
        COUNT(CASE WHEN job_status = 'NEW'     THEN 1 END) AS new_jobs_today,
        COUNT(CASE WHEN job_status = 'UPDATED' THEN 1 END) AS updated_jobs_today,
        COUNT(CASE WHEN job_status = 'CLOSED'  THEN 1 END) AS closed_jobs_today
    FROM {{ ref('fct_job_posting') }}
    WHERE last_seen_date_key = CAST(TO_CHAR(CURRENT_DATE, 'YYYYMMDD') AS INT)
)

SELECT
    CURRENT_DATE                AS report_date,

    -- Volume (sem: total_active_jobs, total_hiring_companies)
    v.total_active_jobs,
    v.total_hiring_companies,

    -- Salary (sem: market_avg_salary, salary_disclosure_rate)
    ROUND(s.market_avg_salary)  AS market_avg_salary_vnd,
    ROUND(s.market_median_salary) AS market_median_salary_vnd,
    s.jobs_with_salary,
    s.salary_disclosure_rate_pct,

    -- Segments (sem: fresher_job_ratio, remote_job_count, intern_job_count)
    sg.total_fresher_jobs,
    sg.total_intern_jobs,
    sg.total_remote_hybrid_jobs,
    sg.fresher_ratio_pct,

    -- Job Family Breakdown (sem: data_jobs_count, backend_jobs_count)
    f.jobs_data_engineer,
    f.jobs_data_analyst,
    f.jobs_data_scientist,
    f.jobs_ml_engineer,
    f.jobs_backend,
    f.jobs_frontend,
    f.jobs_fullstack,

    -- Daily Delta (sem: new_jobs_today)
    d.new_jobs_today,
    d.updated_jobs_today,
    d.closed_jobs_today,

    -- Metadata
    NOW()                       AS generated_at

FROM volume_stats v
CROSS JOIN salary_stats s
CROSS JOIN segment_stats sg
CROSS JOIN family_stats f
CROSS JOIN daily_delta d

{% if is_incremental() %}
    WHERE CURRENT_DATE > (SELECT MAX(report_date) FROM {{ this }})
{% endif %}
