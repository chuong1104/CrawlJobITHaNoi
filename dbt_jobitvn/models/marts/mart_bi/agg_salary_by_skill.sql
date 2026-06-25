{{ config(
    materialized='view'
) }}

-- Thống kê mức lương trung bình, min, max theo từng kỹ năng

WITH valid_salary_jobs AS (
    SELECT
        f.job_id,
        f.salary_avg,
        f.salary_min,
        f.salary_max,
        s.display_name AS skill_name,
        s.skill_category
    FROM {{ ref('fct_job_posting') }} f
    JOIN {{ ref('fct_job_skill') }} fs ON f.job_id = fs.job_id
    JOIN {{ ref('dim_skill') }} s ON fs.skill_id = s.skill_id
    WHERE f.salary_avg IS NOT NULL 
      AND f.salary_currency = 'VND' -- Chỉ lấy tin đăng lương VND để tính toán
)

SELECT
    skill_category,
    skill_name,
    COUNT(DISTINCT job_id) AS jobs_with_salary_info,
    ROUND(AVG(salary_avg), 0) AS avg_salary,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY salary_avg), 0) AS median_salary,
    MIN(salary_min) AS lowest_salary,
    MAX(salary_max) AS highest_salary
FROM valid_salary_jobs
GROUP BY 1, 2
HAVING COUNT(DISTINCT job_id) >= 10 -- Bỏ qua các kỹ năng có quá ít data lương
ORDER BY median_salary DESC
