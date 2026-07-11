{{ config(
    materialized='view'
) }}

-- ============================================================
-- agg_demand_trend.sql — Xu hướng tuyển dụng theo tháng và role
-- Câu hỏi: "Nhu cầu tuyển dụng IT thay đổi như thế nào?"
-- ============================================================

WITH job_base AS (
    SELECT
        f.job_id,
        f.job_family,
        f.source_code,
        f.has_salary,
        f.salary_avg,
        -- Lấy năm/tháng từ first_seen_date_key (YYYYMMDD integer)
        CAST(SUBSTR(CAST(f.first_seen_date_key AS VARCHAR), 1, 4) AS INT) AS year,
        CAST(SUBSTR(CAST(f.first_seen_date_key AS VARCHAR), 5, 2) AS INT) AS month,
        CAST(SUBSTR(CAST(f.first_seen_date_key AS VARCHAR), 1, 4) AS VARCHAR) || '-' ||
        SUBSTR(CAST(f.first_seen_date_key AS VARCHAR), 5, 2)               AS year_month
    FROM {{ ref('fct_job_posting') }} f
    WHERE f.first_seen_date_key IS NOT NULL
),

monthly_trend AS (
    SELECT
        year,
        month,
        year_month,
        job_family,
        source_code,
        COUNT(DISTINCT job_id)                          AS total_jobs,
        COUNT(DISTINCT CASE WHEN has_salary THEN job_id END) AS jobs_with_salary,
        ROUND(AVG(CASE WHEN has_salary THEN salary_avg END), 0) AS avg_salary_vnd
    FROM job_base
    GROUP BY 1, 2, 3, 4, 5
)

SELECT
    year,
    month,
    year_month,
    job_family,
    source_code,
    total_jobs,
    jobs_with_salary,
    avg_salary_vnd,
    -- MoM growth
    LAG(total_jobs) OVER (
        PARTITION BY job_family, source_code
        ORDER BY year, month
    ) AS prev_month_jobs,
    ROUND(
        (total_jobs - LAG(total_jobs) OVER (
            PARTITION BY job_family, source_code ORDER BY year, month
        )) * 100.0
        / NULLIF(LAG(total_jobs) OVER (
            PARTITION BY job_family, source_code ORDER BY year, month
        ), 0), 1
    ) AS mom_growth_pct
FROM monthly_trend
ORDER BY year DESC, month DESC, total_jobs DESC
