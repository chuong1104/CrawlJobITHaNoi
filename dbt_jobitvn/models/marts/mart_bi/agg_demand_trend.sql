-- depends_on: {{ ref('fct_job_posting') }}
{{ config(
    materialized='view'
) }}

-- Báo cáo xu hướng nhu cầu tuyển dụng theo tháng và kỹ năng

WITH job_skills AS (
    SELECT 
        f.job_id,
        f.first_seen_date_key,
        s.skill_category,
        s.display_name AS skill_name
    FROM {{ ref('fct_job_posting') }} f
    JOIN {{ ref('fct_job_skill') }} fs ON f.job_id = fs.job_id
    JOIN {{ ref('dim_skill') }} s ON fs.skill_id = s.skill_id
),
monthly_trend AS (
    SELECT 
        d.year,
        d.month,
        js.skill_category,
        js.skill_name,
        COUNT(DISTINCT js.job_id) AS total_jobs
    FROM job_skills js
    JOIN {{ ref('dim_date') }} d ON js.first_seen_date_key = d.date_key
    GROUP BY 1, 2, 3, 4
)
SELECT * FROM monthly_trend
ORDER BY year DESC, month DESC, total_jobs DESC
