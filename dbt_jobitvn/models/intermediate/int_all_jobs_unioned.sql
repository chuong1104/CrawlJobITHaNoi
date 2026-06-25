{{ config(
    materialized='ephemeral'
) }}

-- Gom tất cả các staging models thành một dòng chảy dữ liệu duy nhất.
-- Ephemeral model không tạo table/view trong DB, chỉ được inject như CTE vào model sau.

WITH unioned AS (
    SELECT * FROM {{ ref('stg_topcv') }}
    UNION ALL
    SELECT * FROM {{ ref('stg_itviec') }}
    UNION ALL
    SELECT * FROM {{ ref('stg_vietnamworks') }}
    UNION ALL
    SELECT * FROM {{ ref('stg_jobsgo') }}
)

SELECT
    source_code,
    source_job_id,
    canonical_url,
    title_raw,
    title_clean,
    company_raw,
    description,
    location_raw,
    location_normalized,
    salary_raw,
    salary_min,
    salary_max,
    salary_is_negotiable,
    salary_currency,
    experience_raw,
    experience_min_years,
    experience_max_years,
    skills_raw,
    deadline_raw,
    posted_date_raw,
    scraped_at,
    batch_date,
    
    -- Generate hashes at this layer to ensure consistency across sources
    {{ generate_identity_hash('source_code', 'company_raw', 'location_normalized', "'UNKNOWN'", "'UNKNOWN'", 'skills_raw') }} AS identity_hash,
    {{ generate_content_hash('title_clean', 'description', "''", 'salary_min', 'salary_max', 'experience_min_years', 'deadline_raw') }} AS content_hash

FROM unioned
