{{ config(
    materialized='view'
) }}

WITH source_data AS (
    SELECT * 
    FROM read_json_auto('data/bronze/valid/source=itviec/**/*.jsonl', format='newline_delimited', ignore_errors=true)
    WHERE job_id_raw IS NOT NULL
),
parsed AS (
    SELECT
        'itviec' AS source_code,
        CAST(job_id_raw AS VARCHAR) AS source_job_id,
        url AS canonical_url,
        title AS title_raw,
        {{ clean_title('title') }} AS title_clean,
        company_name AS company_raw,
        description,
        location_raw,
        {{ normalize_location('location_raw') }} AS location_normalized,
        salary_raw,
        {{ parse_salary('salary_raw') }},
        experience_raw,
        NULL::SMALLINT AS experience_min_years,
        NULL::SMALLINT AS experience_max_years,
        STRING_TO_ARRAY(skills_raw, ',') AS skills_raw,
        deadline_raw,
        TRY_CAST(posted_date_raw AS DATE) AS posted_date_raw,
        TRY_CAST(_scraped_at AS TIMESTAMPTZ) AS scraped_at,
        CURRENT_DATE AS batch_date
    FROM source_data
)
SELECT 
    *,
    {{ generate_identity_hash('source_code', 'company_raw', 'location_normalized', 'NULL', 'salary_raw', 'skills_raw') }} AS identity_hash,
    {{ generate_content_hash('title_clean', 'description', 'NULL', 'salary_min', 'salary_max', 'experience_min_years', 'deadline_raw') }} AS content_hash
FROM parsed
