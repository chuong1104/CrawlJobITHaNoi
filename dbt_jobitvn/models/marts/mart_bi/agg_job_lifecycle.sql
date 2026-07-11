{{ config(
    materialized='table'
) }}

-- ============================================================
-- agg_job_lifecycle.sql
-- Câu hỏi: "Tin tuyển dụng sống bao lâu? Source nào cập nhật nhanh?"
-- Phân tích thời gian từ first_seen đến deadline
-- ============================================================

WITH base AS (
    SELECT
        job_id,
        job_family,
        source_code,
        first_seen_date_key,
        deadline_date_key,
        has_salary,
        salary_avg,
        -- Tính số ngày từ first_seen đến deadline
        CASE
            WHEN deadline_date_key IS NOT NULL AND first_seen_date_key IS NOT NULL THEN
                strptime(CAST(deadline_date_key AS VARCHAR), '%Y%m%d')::DATE
                - strptime(CAST(first_seen_date_key AS VARCHAR), '%Y%m%d')::DATE
            ELSE NULL
        END AS days_active
    FROM {{ ref('fct_job_posting') }}
    WHERE is_active = TRUE
),

-- Tính ngày từ integer key
with_dates AS (
    SELECT
        *,
        CAST(
            SUBSTR(CAST(first_seen_date_key AS VARCHAR), 1, 4) || '-' ||
            SUBSTR(CAST(first_seen_date_key AS VARCHAR), 5, 2) || '-' ||
            SUBSTR(CAST(first_seen_date_key AS VARCHAR), 7, 2)
        AS DATE) AS first_seen_date
    FROM base
    WHERE first_seen_date_key IS NOT NULL
),

by_source AS (
    SELECT
        source_code,
        COUNT(DISTINCT job_id)                      AS total_jobs,
        ROUND(AVG(days_active), 1)                  AS avg_days_active,
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_active), 0)
                                                    AS median_days_active,
        MIN(days_active)                            AS min_days,
        MAX(days_active)                            AS max_days,
        COUNT(CASE WHEN days_active IS NOT NULL THEN 1 END) AS jobs_with_deadline,
        -- Jobs posted this week
        COUNT(CASE WHEN first_seen_date >= CURRENT_DATE - INTERVAL '7 days' THEN 1 END)
                                                    AS new_jobs_last_7d,
        -- Freshness: % jobs posted in last 7 days
        ROUND(
            COUNT(CASE WHEN first_seen_date >= CURRENT_DATE - INTERVAL '7 days' THEN 1 END)
            * 100.0 / NULLIF(COUNT(DISTINCT job_id), 0), 1
        )                                           AS freshness_pct
    FROM with_dates
    GROUP BY source_code
)

SELECT
    source_code,
    total_jobs,
    avg_days_active,
    median_days_active,
    min_days,
    max_days,
    jobs_with_deadline,
    new_jobs_last_7d,
    freshness_pct,
    RANK() OVER (ORDER BY new_jobs_last_7d DESC) AS freshness_rank
FROM by_source
ORDER BY total_jobs DESC
