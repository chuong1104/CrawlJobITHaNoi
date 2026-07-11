{{ config(
    materialized='table'
) }}

-- ============================================================
-- dim_company.sql — Danh sách công ty tuyển dụng (deduplicated)
-- Source: int_deduped_jobs (DuckDB-native, không cần PostgreSQL)
-- SCD Type 1: giữ tên mới nhất
-- ============================================================

WITH company_raw AS (
    SELECT
        company_raw,
        -- Chuẩn hóa tên: trim, uppercase đầu từ, loại bỏ ký tự thừa
        TRIM(REGEXP_REPLACE(UPPER(TRIM(company_raw)), '\s+', ' ', 'g')) AS company_name_normalized,
        -- Industry từ industry_raw (lấy phần đầu trước dấu > hoặc ,)
        TRIM(SPLIT_PART(COALESCE(industry_raw, ''), '>', 1))            AS industry_hint,
        -- Lấy scraped_at mới nhất để SCD1
        MAX(scraped_at)                                                  AS last_seen_at,
        COUNT(*)                                                         AS job_count
    FROM {{ ref('int_deduped_jobs') }}
    WHERE company_raw IS NOT NULL
      AND TRIM(company_raw) != ''
    GROUP BY 1, 2, 3
),

ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY company_name_normalized
            ORDER BY job_count DESC, last_seen_at DESC
        ) AS rn
    FROM company_raw
),

deduped AS (
    SELECT
        -- Surrogate key bằng hash
        MD5(company_name_normalized)    AS company_id,
        company_name_normalized         AS normalized_name,
        -- Display name: dùng bản gốc (trim) 
        TRIM(company_raw)               AS display_name,
        -- Industry: lấy hint nếu có ý nghĩa (> 3 chars)
        CASE
            WHEN LENGTH(industry_hint) > 3
             AND industry_hint NOT ILIKE '%hà nội%'
             AND industry_hint NOT ILIKE '%việc làm%'
            THEN industry_hint
            ELSE NULL
        END                             AS industry,
        NULL::VARCHAR                   AS company_size,
        FALSE                           AS is_anonymous,
        last_seen_at                    AS source_updated_at,
        job_count
    FROM ranked
    WHERE rn = 1
)

SELECT
    company_id,
    normalized_name,
    display_name,
    industry,
    company_size,
    is_anonymous,
    source_updated_at,
    job_count
FROM deduped
ORDER BY job_count DESC
