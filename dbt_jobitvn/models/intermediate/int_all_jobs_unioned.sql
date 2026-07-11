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
    UNION ALL
    SELECT * FROM {{ ref('stg_linkedin') }}
    UNION ALL
    SELECT * FROM {{ ref('stg_123job') }}
    UNION ALL
    SELECT * FROM {{ ref('stg_careerviet') }}
    UNION ALL
    SELECT * FROM {{ ref('stg_joboko') }}
)

SELECT
    source_code,
    source_job_id,
    canonical_url,
    title_raw,
    title_clean,
    company_raw,
    description,
    requirements_text,
    location_raw,
    location_normalized,
    industry_raw,
    job_type_raw,
    job_position_raw,
    salary_raw,
    salary_min,
    salary_max,
    salary_avg,
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
