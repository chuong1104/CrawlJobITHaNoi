{{ config(
    materialized='table'
) }}

-- ============================================================
-- int_job_skills_extracted.sql
-- Trích xuất skills THỰC TẾ từ text (requirements + description)
-- bằng keyword matching với seed dim_skill_mapping
--
-- Logic:
--   1. Gom text = LOWER(requirements + ' ' + description)
--   2. Với mỗi skill trong seed mapping, kiểm tra xem keyword có xuất hiện không
--   3. Output: 1 dòng / 1 skill cho mỗi job
-- ============================================================

WITH deduped_jobs AS (
    SELECT
        source_code,
        source_job_id,
        LOWER(
            COALESCE(requirements_text, '') || ' ' || COALESCE(description, '')
        ) AS combined_text
    FROM {{ ref('int_deduped_jobs') }}
    WHERE requirements_text IS NOT NULL OR description IS NOT NULL
),

-- Load skill mapping từ seed
skill_map AS (
    SELECT DISTINCT
        LOWER(raw_skill)        AS raw_skill_lower,
        normalized_skill,
        skill_category,
        skill_subcategory
    FROM {{ ref('dim_skill_mapping') }}
),

-- Cross join + filter: kiểm tra từng keyword có trong text không
matched AS (
    SELECT
        j.source_code,
        j.source_job_id,
        s.normalized_skill,
        s.skill_category,
        s.skill_subcategory,
        s.raw_skill_lower       AS matched_keyword
    FROM deduped_jobs j
    CROSS JOIN skill_map s
    -- Dùng LIKE với word boundary đơn giản (space, punctuation, start/end)
    WHERE j.combined_text LIKE ('% ' || s.raw_skill_lower || ' %')
       OR j.combined_text LIKE (s.raw_skill_lower || ' %')
       OR j.combined_text LIKE ('% ' || s.raw_skill_lower)
       OR j.combined_text = s.raw_skill_lower
       OR j.combined_text LIKE ('% ' || s.raw_skill_lower || ',%')
       OR j.combined_text LIKE ('% ' || s.raw_skill_lower || '.')
       OR j.combined_text LIKE ('% ' || s.raw_skill_lower || ':')
       OR j.combined_text LIKE ('% ' || s.raw_skill_lower || '/')
       OR j.combined_text LIKE ('% ' || s.raw_skill_lower || '\n%')
),

-- Dedupe: mỗi job chỉ có 1 dòng / 1 normalized_skill (tránh trùng do nhiều keyword map cùng skill)
final AS (
    SELECT DISTINCT
        source_code,
        source_job_id,
        normalized_skill,
        skill_category,
        skill_subcategory
    FROM matched
)

SELECT *
FROM final
ORDER BY source_code, source_job_id, skill_category, normalized_skill
