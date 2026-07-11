{{ config(
    materialized='view'
) }}

-- ============================================================
-- agg_salary_by_skill.sql — Mức lương theo kỹ năng
-- Câu hỏi: "Học kỹ năng gì để kiếm lương cao?"
-- ============================================================

WITH valid_salary_jobs AS (
    SELECT
        f.job_id,
        f.salary_avg,
        f.salary_min,
        f.salary_max,
        f.job_family,
        -- Display name từ fct_job_skill (có normalized_skill và skill_category)
        COALESCE(ds.display_name, UPPER(SUBSTRING(REPLACE(fs.normalized_skill, '_', ' '), 1, 1)) || LOWER(SUBSTRING(REPLACE(fs.normalized_skill, '_', ' '), 2))) AS skill_name,
        fs.normalized_skill AS skill_code,
        fs.skill_category,
        fs.skill_subcategory
    FROM {{ ref('fct_job_posting') }} f
    JOIN {{ ref('fct_job_skill') }} fs ON f.job_id = fs.job_id
    LEFT JOIN {{ ref('dim_skill') }} ds ON fs.normalized_skill = ds.skill_code
    WHERE f.salary_avg IS NOT NULL
      AND f.salary_currency = 'VND'
      AND f.is_active = TRUE
)

SELECT
    skill_category,
    skill_subcategory,
    skill_code,
    skill_name,
    COUNT(DISTINCT job_id)                              AS jobs_with_salary_info,
    ROUND(AVG(salary_avg), 0)                           AS avg_salary_vnd,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY salary_avg), 0) AS median_salary_vnd,
    ROUND(MIN(salary_min), 0)                           AS lowest_salary_vnd,
    ROUND(MAX(salary_max), 0)                           AS highest_salary_vnd,
    -- Format for display
    ROUND(AVG(salary_avg) / 1000000, 1)                 AS avg_salary_million_vnd,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY salary_avg) / 1000000, 1)
                                                        AS median_salary_million_vnd,
    -- Top job family using this skill
    MODE() WITHIN GROUP (ORDER BY job_family)           AS most_common_role
FROM valid_salary_jobs
GROUP BY 1, 2, 3, 4
HAVING COUNT(DISTINCT job_id) >= 3   -- Bỏ skills quá ít data
ORDER BY median_salary_vnd DESC NULLS LAST
