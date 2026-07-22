{{ config(
    materialized='view'
) }}

WITH source_data AS (
    SELECT * 
    FROM read_json_auto('/opt/airflow/data/bronze/topcv/**/*_valid.jsonl', format='newline_delimited', ignore_errors=true)
    WHERE job_id IS NOT NULL
),
parsed AS (
    SELECT
        'topcv'                             AS source_code,
        CAST(job_id AS VARCHAR)             AS source_job_id,
        CAST(job_url AS VARCHAR)                             AS canonical_url,
        CAST(title AS VARCHAR)              AS title_raw,
        {{ clean_title('title') }}           AS title_clean,
        CAST(company AS VARCHAR)                             AS company_raw,
        CAST(job_description AS VARCHAR)                     AS description,
        CAST(requirements AS VARCHAR)                        AS requirements_text,
        CAST(location AS VARCHAR)                            AS location_raw,
        {{ normalize_location('location') }} AS location_normalized,
        -- Industry category (SEO tags từ nguồn — KHÔNG phải skills)
        CAST(job_industry AS VARCHAR)                         AS industry_raw,
        -- Job attributes
        CAST(job_type AS VARCHAR)                             AS job_type_raw,
        CAST(job_position AS VARCHAR)                         AS job_position_raw,
        -- Salary
        CAST(salary AS VARCHAR)                               AS salary_raw,
        {{ parse_salary('salary') }},
        -- Experience — parse từ text thực tế
        CAST(experience_level AS VARCHAR)                     AS experience_raw,
        {{ parse_experience('experience_level', "COALESCE(requirements, '') || ' ' || COALESCE(job_description, '')") }},
        -- Skills: NULL tại staging — sẽ được extract tại int_job_skills_extracted
        NULL::VARCHAR[]                      AS skills_raw,
        -- Dates
        CAST(job_deadline AS VARCHAR)                         AS deadline_raw,
        NULL::DATE                           AS posted_date_raw,
        TRY_CAST(scraped_at AS TIMESTAMPTZ) AS scraped_at,
        CURRENT_DATE                         AS batch_date
    FROM source_data
)
SELECT 
    *,
    {{ generate_identity_hash('source_code', 'company_raw', 'location_normalized', 'NULL', 'salary_raw', 'skills_raw') }} AS identity_hash,
    {{ generate_content_hash('title_clean', 'description', 'NULL', 'salary_min', 'salary_max', 'experience_min_years', 'deadline_raw') }} AS content_hash
FROM parsed
