{{ config(
    materialized='view'
) }}

WITH source_data AS (
    SELECT * 
    FROM read_json_auto('data/bronze/jobsgo/**/*_valid.jsonl', format='newline_delimited', ignore_errors=true)
    WHERE job_id IS NOT NULL
),
parsed AS (
    SELECT
        'jobsgo' AS source_code,
        CAST(job_id AS VARCHAR) AS source_job_id,
        job_url AS canonical_url,
        title AS title_raw,
        {{ clean_title('title') }} AS title_clean,
        company AS company_raw,
        job_description AS description,
        location AS location_raw,
        {{ normalize_location('location') }} AS location_normalized,
        salary AS salary_raw,
        {{ parse_salary('salary') }},
        experience_level AS experience_raw,
        NULL::SMALLINT AS experience_min_years,
        NULL::SMALLINT AS experience_max_years,
        STRING_TO_ARRAY(job_industry, ',') AS skills_raw,
        job_deadline AS deadline_raw,
        NULL::DATE AS posted_date_raw,
        TRY_CAST(scraped_at AS TIMESTAMPTZ) AS scraped_at,
        CURRENT_DATE AS batch_date
    FROM source_data
)
SELECT 
    *,
    {{ generate_identity_hash('source_code', 'company_raw', 'location_normalized', 'NULL', 'salary_raw', 'skills_raw') }} AS identity_hash,
    {{ generate_content_hash('title_clean', 'description', 'NULL', 'salary_min', 'salary_max', 'experience_min_years', 'deadline_raw') }} AS content_hash
FROM parsed

