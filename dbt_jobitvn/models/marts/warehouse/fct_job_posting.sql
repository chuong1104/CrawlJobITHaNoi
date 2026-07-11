{{ config(
    materialized='incremental',
    unique_key='job_id',
    incremental_strategy='delete+insert'
) }}

-- ============================================================
-- fct_job_posting.sql — Bảng Fact chính: Tin tuyển dụng hiện tại
-- Source: int_deduped_jobs (DuckDB-native)
-- Mỗi job_id = 1 dòng, trạng thái mới nhất (no SCD2)
-- ============================================================

WITH base AS (
    SELECT
        -- Surrogate key
        MD5(source_code || '::' || source_job_id)   AS job_id,

        -- Foreign keys → Dim tables
        MD5(UPPER(TRIM(company_raw)))                AS company_id,
        source_code,

        -- Business keys
        source_job_id,
        canonical_url,

        -- Job descriptors (degenerate dimensions — stay in fact)
        title_clean,
        job_position_raw                             AS job_level,
        job_type_raw                                 AS job_type,
        location_normalized                          AS location_code,

        -- Salary measures
        salary_raw,
        salary_min,
        salary_max,
        salary_avg,
        salary_currency,
        salary_is_negotiable,
        CASE WHEN salary_avg IS NOT NULL THEN TRUE ELSE FALSE END AS has_salary,

        -- Experience measures
        experience_raw,
        experience_min_years,
        experience_max_years,

        -- Job classification flags
        CASE
            WHEN LOWER(COALESCE(job_position_raw,'')) LIKE '%intern%'
              OR LOWER(COALESCE(title_clean,'')) LIKE '%intern%'
              OR LOWER(COALESCE(title_clean,'')) LIKE '%thực tập%'
            THEN TRUE ELSE FALSE
        END AS is_intern,
        CASE
            WHEN LOWER(COALESCE(job_position_raw,'')) LIKE '%fresher%'
              OR LOWER(COALESCE(experience_raw,'')) LIKE '%không yêu cầu%'
              OR experience_max_years <= 1
            THEN TRUE ELSE FALSE
        END AS is_fresher,
        CASE
            WHEN LOWER(COALESCE(location_normalized,'')) LIKE '%remote%'
            THEN 'REMOTE'
            WHEN LOWER(COALESCE(job_type_raw,'')) LIKE '%hybrid%'
              OR LOWER(COALESCE(job_type_raw,'')) LIKE '%kết hợp%'
            THEN 'HYBRID'
            ELSE 'ONSITE'
        END AS work_mode,

        -- Job family classification từ title
        CASE
            WHEN LOWER(title_clean) ~ 'data engineer|kỹ sư dữ liệu'                          THEN 'DATA_ENGINEER'
            WHEN LOWER(title_clean) ~ 'data analyst|phân tích dữ liệu'                       THEN 'DATA_ANALYST'
            WHEN LOWER(title_clean) ~ 'data scientist|khoa học dữ liệu'                      THEN 'DATA_SCIENTIST'
            WHEN LOWER(title_clean) ~ 'ml engineer|machine learning engineer|ai engineer'    THEN 'ML_ENGINEER'
            WHEN LOWER(title_clean) ~ 'frontend|front-end|react|angular|vue|ui developer'    THEN 'FRONTEND'
            WHEN LOWER(title_clean) ~ 'backend|back-end|java dev|python dev|php dev|nodejs'  THEN 'BACKEND'
            WHEN LOWER(title_clean) ~ 'fullstack|full-stack|full stack'                       THEN 'FULLSTACK'
            WHEN LOWER(title_clean) ~ 'devops|sre|platform engineer|infrastructure'          THEN 'DEVOPS'
            WHEN LOWER(title_clean) ~ 'mobile|android|ios|flutter|react native'              THEN 'MOBILE'
            WHEN LOWER(title_clean) ~ 'qa|qc|tester|kiểm thử'                               THEN 'QA_QC'
            WHEN LOWER(title_clean) ~ 'security|an ninh mạng|cybersecurity'                  THEN 'SECURITY'
            WHEN LOWER(title_clean) ~ 'product manager|product owner|ba |business analyst'   THEN 'PRODUCT_BA'
            WHEN LOWER(title_clean) ~ 'scrum master|agile coach|project manager'             THEN 'MANAGEMENT'
            ELSE 'OTHER_IT'
        END AS job_family,

        -- Dates (integer keys for dim_date join)
        CAST(strftime(scraped_at::DATE, '%Y%m%d') AS INT) AS first_seen_date_key,
        CAST(strftime(CURRENT_DATE, '%Y%m%d') AS INT) AS last_seen_date_key,
        CASE
            WHEN deadline_raw ~ '^\d{2}/\d{2}/\d{4}$'
            THEN CAST(
                strftime(STRPTIME(deadline_raw, '%d/%m/%Y'), '%Y%m%d')
                AS INT
            )
            ELSE NULL
        END AS deadline_date_key,

        -- Status
        'ACTIVE'    AS job_status,
        TRUE        AS is_active,

        -- Metadata
        scraped_at  AS updated_at,
        CURRENT_TIMESTAMP AS loaded_at

    FROM {{ ref('int_deduped_jobs') }}
    WHERE title_clean IS NOT NULL

    {% if is_incremental() %}
    AND scraped_at > (SELECT MAX(updated_at) FROM {{ this }})
    {% endif %}
)

SELECT * FROM base
