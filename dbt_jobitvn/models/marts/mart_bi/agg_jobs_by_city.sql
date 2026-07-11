{{ config(
    materialized='view'
) }}

-- ============================================================
-- agg_jobs_by_city.sql — Phân bổ việc làm theo thành phố
-- Câu hỏi: "Việc làm IT tập trung ở đâu?"
-- ============================================================

WITH job_locs AS (
    SELECT
        f.job_id,
        f.job_family,
        f.has_salary,
        f.salary_avg,
        -- Location từ location_code trong fct_job_posting
        COALESCE(l.display_name, 'Khác / Toàn quốc')   AS city_name,
        COALESCE(l.region, 'unknown')                    AS region,
        COALESCE(l.is_remote, FALSE)                     AS is_remote
    FROM {{ ref('fct_job_posting') }} f
    LEFT JOIN {{ ref('dim_location') }} l
        ON LOWER(TRIM(f.location_code)) = LOWER(TRIM(l.location_code))
    WHERE f.is_active = TRUE
)

SELECT
    region,
    city_name,
    is_remote,
    COUNT(DISTINCT job_id)                              AS active_job_count,
    COUNT(DISTINCT CASE WHEN has_salary THEN job_id END) AS jobs_with_salary,
    ROUND(AVG(CASE WHEN has_salary THEN salary_avg END), 0) AS avg_salary_vnd,
    -- Top role by city
    MODE() WITHIN GROUP (ORDER BY job_family)           AS top_job_family,
    RANK() OVER (ORDER BY COUNT(DISTINCT job_id) DESC)  AS city_rank
FROM job_locs
GROUP BY 1, 2, 3
ORDER BY active_job_count DESC
