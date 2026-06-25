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
    identity_hash,
    content_hash

FROM unioned
