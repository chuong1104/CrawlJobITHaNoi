{{ config(
    materialized='incremental',
    unique_key='report_date'
) }}

-- =============================================================================
-- kpi_daily_summary.sql — KPI Snapshot hàng ngày (v3.0 — DuckDB-native)
-- Tất cả consumer (Power BI, FastAPI) đọc bảng này
-- =============================================================================

WITH active_jobs AS (
    SELECT *
    FROM {{ ref('fct_job_posting') }}
    WHERE is_active = TRUE
),

volume_stats AS (
    SELECT
        COUNT(DISTINCT job_id)      AS total_active_jobs,
        COUNT(DISTINCT company_id)  AS total_hiring_companies,
        COUNT(DISTINCT source_code) AS total_active_sources
    FROM active_jobs
),

salary_stats AS (
    SELECT
        ROUND(AVG(salary_avg), 0)                   AS market_avg_salary,
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY salary_avg), 0)
                                                    AS market_median_salary,
        COUNT(CASE WHEN has_salary THEN 1 END)      AS jobs_with_salary,
        ROUND(
            COUNT(CASE WHEN has_salary THEN 1 END) * 100.0
            / NULLIF(COUNT(*), 0), 2
        )                                           AS salary_disclosure_rate_pct
    FROM active_jobs
),

segment_stats AS (
    SELECT
        COUNT(CASE WHEN is_fresher = TRUE THEN 1 END)       AS total_fresher_jobs,
        COUNT(CASE WHEN is_intern  = TRUE THEN 1 END)       AS total_intern_jobs,
        COUNT(CASE WHEN work_mode IN ('REMOTE', 'HYBRID') THEN 1 END)
                                                            AS total_remote_hybrid_jobs,
        ROUND(
            COUNT(CASE WHEN is_fresher = TRUE THEN 1 END) * 100.0
            / NULLIF(COUNT(*), 0), 2
        )                                                   AS fresher_ratio_pct
    FROM active_jobs
),

family_stats AS (
    SELECT
        COUNT(CASE WHEN job_family = 'DATA_ENGINEER'  THEN 1 END) AS jobs_data_engineer,
        COUNT(CASE WHEN job_family = 'DATA_ANALYST'   THEN 1 END) AS jobs_data_analyst,
        COUNT(CASE WHEN job_family = 'DATA_SCIENTIST' THEN 1 END) AS jobs_data_scientist,
        COUNT(CASE WHEN job_family = 'ML_ENGINEER'    THEN 1 END) AS jobs_ml_engineer,
        COUNT(CASE WHEN job_family = 'BACKEND'        THEN 1 END) AS jobs_backend,
        COUNT(CASE WHEN job_family = 'FRONTEND'       THEN 1 END) AS jobs_frontend,
        COUNT(CASE WHEN job_family = 'FULLSTACK'      THEN 1 END) AS jobs_fullstack,
        COUNT(CASE WHEN job_family = 'DEVOPS'         THEN 1 END) AS jobs_devops,
        COUNT(CASE WHEN job_family = 'MOBILE'         THEN 1 END) AS jobs_mobile
    FROM active_jobs
),

daily_delta AS (
    SELECT
        COUNT(CASE WHEN job_status = 'NEW'     THEN 1 END) AS new_jobs_today,
        COUNT(CASE WHEN job_status = 'UPDATED' THEN 1 END) AS updated_jobs_today,
        COUNT(CASE WHEN job_status = 'CLOSED'  THEN 1 END) AS closed_jobs_today
    FROM {{ ref('fct_job_posting') }}
    WHERE last_seen_date_key = CAST(strftime(CURRENT_DATE, '%Y%m%d') AS INT)
)

SELECT
    CURRENT_DATE                    AS report_date,

    -- Volume
    v.total_active_jobs,
    v.total_hiring_companies,
    v.total_active_sources,

    -- Salary
    s.market_avg_salary             AS market_avg_salary_vnd,
    s.market_median_salary          AS market_median_salary_vnd,
    s.jobs_with_salary,
    s.salary_disclosure_rate_pct,

    -- Segments
    sg.total_fresher_jobs,
    sg.total_intern_jobs,
    sg.total_remote_hybrid_jobs,
    sg.fresher_ratio_pct,

    -- Job Family Breakdown
    f.jobs_data_engineer,
    f.jobs_data_analyst,
    f.jobs_data_scientist,
    f.jobs_ml_engineer,
    f.jobs_backend,
    f.jobs_frontend,
    f.jobs_fullstack,
    f.jobs_devops,
    f.jobs_mobile,

    -- Daily Delta
    d.new_jobs_today,
    d.updated_jobs_today,
    d.closed_jobs_today,

    NOW()                           AS generated_at

FROM volume_stats v
CROSS JOIN salary_stats s
CROSS JOIN segment_stats sg
CROSS JOIN family_stats f
CROSS JOIN daily_delta d

{% if is_incremental() %}
    WHERE CURRENT_DATE > (SELECT MAX(report_date) FROM {{ this }})
{% endif %}
