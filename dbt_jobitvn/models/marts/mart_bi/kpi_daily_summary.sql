{{ config(
    materialized='incremental',
    unique_key='report_date'
) }}

-- Lưu trữ KPI tổng hợp mỗi ngày
-- Lịch sử snapshot hàng ngày về thị trường việc làm

WITH daily_stats AS (
    SELECT 
        CURRENT_DATE AS report_date,
        COUNT(DISTINCT job_id) AS total_active_jobs,
        COUNT(DISTINCT company_id) AS total_hiring_companies,
        COUNT(CASE WHEN job_level = 'FRESHER' OR is_fresher = TRUE THEN 1 END) AS total_fresher_jobs,
        COUNT(CASE WHEN salary_avg IS NOT NULL THEN 1 END) AS jobs_with_salary,
        AVG(salary_avg) AS market_avg_salary
    FROM {{ ref('fct_job_posting') }}
    WHERE is_active = TRUE
)

SELECT * FROM daily_stats
