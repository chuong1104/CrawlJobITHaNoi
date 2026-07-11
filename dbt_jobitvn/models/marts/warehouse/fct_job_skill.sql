{{ config(
    materialized='table'
) }}

-- ============================================================
-- fct_job_skill.sql — Bridge table: job  skill
-- Source: int_job_skills_exploded (keyword-matched skills)
-- ============================================================

SELECT
    MD5(j.source_code || '::' || j.source_job_id)  AS job_id,
    MD5(s.normalized_skill)                         AS skill_id,
    s.normalized_skill,
    s.skill_category,
    s.skill_subcategory,
    -- Đánh dấu primary skill: là skill category = language hoặc framework
    CASE
        WHEN s.skill_category IN ('language', 'framework') THEN TRUE
        ELSE FALSE
    END AS is_primary,
    -- Thứ tự skill (theo alphabet trong mỗi category)
    ROW_NUMBER() OVER (
        PARTITION BY j.source_code, j.source_job_id, s.skill_category
        ORDER BY s.normalized_skill
    ) AS skill_position

FROM {{ ref('int_job_skills_exploded') }} s
JOIN {{ ref('int_deduped_jobs') }} j
  ON s.source_code = j.source_code
 AND s.source_job_id = j.source_job_id

-- Chỉ include jobs có trong fct_job_posting
WHERE MD5(j.source_code || '::' || j.source_job_id) IN (
    SELECT job_id FROM {{ ref('fct_job_posting') }}
)
