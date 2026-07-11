{{ config(
    materialized='table'
) }}

-- ============================================================
-- agg_company_hiring.sql
-- Câu hỏi: "Công ty nào đang tuyển nhiều nhất?"
-- Phân tích theo ngành, loại hình công việc
-- ============================================================

WITH job_base AS (
    SELECT
        f.job_id,
        f.company_id,
        c.display_name          AS company_name,
        c.industry,
        f.job_family,
        f.work_mode,
        f.has_salary,
        f.salary_avg,
        f.is_fresher,
        f.is_intern,
        f.first_seen_date_key
    FROM {{ ref('fct_job_posting') }} f
    LEFT JOIN {{ ref('dim_company') }} c ON f.company_id = c.company_id
    WHERE f.is_active = TRUE
),

skill_counts AS (
    SELECT
        job_id,
        COUNT(*) AS skill_count
    FROM {{ ref('fct_job_skill') }}
    GROUP BY job_id
),

company_stats AS (
    SELECT
        j.company_id,
        j.company_name,
        j.industry,

        -- Volume
        COUNT(DISTINCT j.job_id)                    AS total_active_jobs,
        COUNT(DISTINCT j.job_family)                AS unique_roles_count,

        -- Job mix
        COUNT(CASE WHEN j.job_family = 'DATA_ENGINEER'  THEN 1 END) AS data_engineer_jobs,
        COUNT(CASE WHEN j.job_family = 'DATA_ANALYST'   THEN 1 END) AS data_analyst_jobs,
        COUNT(CASE WHEN j.job_family = 'BACKEND'        THEN 1 END) AS backend_jobs,
        COUNT(CASE WHEN j.job_family = 'FRONTEND'       THEN 1 END) AS frontend_jobs,
        COUNT(CASE WHEN j.job_family = 'FULLSTACK'      THEN 1 END) AS fullstack_jobs,
        COUNT(CASE WHEN j.job_family = 'DEVOPS'         THEN 1 END) AS devops_jobs,
        COUNT(CASE WHEN j.job_family = 'ML_ENGINEER'    THEN 1 END) AS ml_jobs,

        -- Salary
        ROUND(AVG(j.salary_avg), 0)                 AS avg_salary_vnd,
        ROUND(AVG(CASE WHEN j.has_salary THEN j.salary_avg END), 0) AS avg_disclosed_salary_vnd,
        COUNT(CASE WHEN j.has_salary THEN 1 END) * 100.0
            / NULLIF(COUNT(j.job_id), 0)            AS salary_disclosure_pct,

        -- Work mode
        COUNT(CASE WHEN j.work_mode = 'REMOTE' THEN 1 END)  AS remote_jobs,
        COUNT(CASE WHEN j.work_mode = 'HYBRID' THEN 1 END)  AS hybrid_jobs,

        -- Level
        COUNT(CASE WHEN j.is_fresher THEN 1 END)    AS fresher_jobs,
        COUNT(CASE WHEN j.is_intern  THEN 1 END)    AS intern_jobs,

        -- Avg skills required
        ROUND(AVG(sc.skill_count), 1)               AS avg_skills_required

    FROM job_base j
    LEFT JOIN skill_counts sc ON j.job_id = sc.job_id
    GROUP BY j.company_id, j.company_name, j.industry
)

SELECT
    *,
    RANK() OVER (ORDER BY total_active_jobs DESC)   AS hiring_rank
FROM company_stats
WHERE total_active_jobs >= 1
ORDER BY total_active_jobs DESC
