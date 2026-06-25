{{ config(
    materialized='view'
) }}

WITH source_data AS (
    SELECT * 
    FROM read_json_auto('data/bronze/itviec/**/*.jsonl', format='newline_delimited', ignore_errors=true)
)

SELECT
    'itviec' AS source_code,
    CAST(job_id_raw AS VARCHAR) AS source_job_id,
    url AS canonical_url,

    -- Text fields
    title AS title_raw,
    {{ clean_title('title') }} AS title_clean,
    company_name AS company_raw,
    description,
    
    -- Location
    location_raw,
    {{ normalize_location('location_raw') }} AS location_normalized,
    
    -- Salary
    salary_raw,
    {{ parse_salary('salary_raw') }},

    -- Experience
    experience_raw,
    NULL::SMALLINT AS experience_min_years,
    NULL::SMALLINT AS experience_max_years,

    -- Array fields
    STRING_TO_ARRAY(skills_raw, ',') AS skills_raw,
    
    -- Dates
    deadline_raw,
    TRY_CAST(posted_date_raw AS DATE) AS posted_date_raw,

    -- System fields
    TRY_CAST(_scraped_at AS TIMESTAMPTZ) AS scraped_at,
    CURRENT_DATE AS batch_date

FROM source_data
WHERE job_id_raw IS NOT NULL
