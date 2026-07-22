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

-- Load skill mapping từ seed và chuẩn bị regex pattern tương ứng với từng keyword
skill_map AS (
    SELECT DISTINCT
        LOWER(raw_skill)        AS raw_skill_lower,
        normalized_skill,
        skill_category,
        skill_subcategory,
        -- Thiết lập Regex pattern thông minh để hỗ trợ các từ khóa đặc biệt (C++, C#, .NET, v.v.)
        CASE 
            -- Nếu bắt đầu và kết thúc đều bằng ký tự word: \bkeyword\b
            WHEN LOWER(raw_skill) ~ '^[a-zA-Z0-9_].*[a-zA-Z0-9_]$' THEN '\b' || regexp_escape(LOWER(raw_skill)) || '\b'
            -- Nếu chỉ bắt đầu bằng ký tự word: \bkeyword
            WHEN LOWER(raw_skill) ~ '^[a-zA-Z0-9_]' THEN '\b' || regexp_escape(LOWER(raw_skill))
            -- Nếu chỉ kết thúc bằng ký tự word: keyword\b
            WHEN LOWER(raw_skill) ~ '[a-zA-Z0-9_]$' THEN regexp_escape(LOWER(raw_skill)) || '\b'
            -- Trường hợp khác: dùng regex escape thông thường
            ELSE regexp_escape(LOWER(raw_skill))
        END AS regex_pattern
    FROM {{ ref('dim_skill_mapping') }}
),

-- Inner Join thông qua regexp_matches: loại bỏ hoàn toàn CROSS JOIN chậm chạp
matched AS (
    SELECT
        j.source_code,
        j.source_job_id,
        s.normalized_skill,
        s.skill_category,
        s.skill_subcategory,
        s.raw_skill_lower       AS matched_keyword
    FROM deduped_jobs j
    INNER JOIN skill_map s ON regexp_matches(j.combined_text, s.regex_pattern)
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
