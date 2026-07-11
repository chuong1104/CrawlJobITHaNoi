{{ config(
    materialized='table'
) }}

-- ============================================================
-- agg_top_skills_by_role.sql
-- Câu hỏi: "Kỹ năng gì được yêu cầu nhiều nhất cho từng role?"
-- Phân tích: Top skills theo job_family và skill_category
-- ============================================================

WITH skill_job_base AS (
    SELECT
        f.job_id,
        f.job_family,
        f.is_active,
        fs.normalized_skill,
        fs.skill_category,
        fs.skill_subcategory,
        -- Display name từ dim_skill
        COALESCE(ds.display_name, UPPER(SUBSTRING(REPLACE(fs.normalized_skill, '_', ' '), 1, 1)) || LOWER(SUBSTRING(REPLACE(fs.normalized_skill, '_', ' '), 2))) AS skill_name
    FROM {{ ref('fct_job_posting') }} f
    JOIN {{ ref('fct_job_skill') }}   fs ON f.job_id = fs.job_id
    LEFT JOIN {{ ref('dim_skill') }}  ds ON fs.normalized_skill = ds.skill_code
    WHERE f.is_active = TRUE
      AND f.job_family != 'OTHER_IT'
),

skill_stats AS (
    SELECT
        job_family,
        skill_category,
        skill_subcategory,
        normalized_skill,
        skill_name,
        COUNT(DISTINCT job_id)                      AS job_count,
        -- Tổng số job trong role này để tính tỉ lệ
        SUM(COUNT(DISTINCT job_id)) OVER (
            PARTITION BY job_family
        )                                           AS total_jobs_in_role
    FROM skill_job_base
    GROUP BY 1, 2, 3, 4, 5
),

ranked AS (
    SELECT
        *,
        ROUND(job_count * 100.0 / NULLIF(total_jobs_in_role, 0), 1) AS demand_pct,
        RANK() OVER (
            PARTITION BY job_family, skill_category
            ORDER BY job_count DESC
        ) AS rank_in_category,
        RANK() OVER (
            PARTITION BY job_family
            ORDER BY job_count DESC
        ) AS rank_overall
    FROM skill_stats
)

SELECT
    job_family,
    skill_category,
    skill_subcategory,
    normalized_skill,
    skill_name,
    job_count,
    demand_pct,
    rank_in_category,
    rank_overall,
    total_jobs_in_role
FROM ranked
WHERE rank_overall <= 30  -- top 30 skills per role
ORDER BY job_family, rank_overall
