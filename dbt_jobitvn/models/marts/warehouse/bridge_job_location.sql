{{ config(
    materialized='table'
) }}

-- ============================================================
-- bridge_job_location.sql — Bridge table: job  location
-- Source: int_deduped_jobs + dim_location_mapping
-- ============================================================

WITH job_locs AS (
    SELECT
        MD5(j.source_code || '::' || j.source_job_id)  AS job_id,
        LOWER(TRIM(j.location_normalized))              AS location_code_raw
    FROM {{ ref('int_deduped_jobs') }} j
    WHERE j.location_normalized IS NOT NULL
),

location_lookup AS (
    SELECT DISTINCT
        LOWER(TRIM(normalized_location))    AS location_code_raw,
        MD5(normalized_location)            AS location_id,
        normalized_location
    FROM {{ ref('dim_location_mapping') }}
)

SELECT
    j.job_id,
    COALESCE(l.location_id, MD5('other'))   AS location_id,
    COALESCE(l.normalized_location, 'other') AS location_code
FROM job_locs j
LEFT JOIN location_lookup l ON j.location_code_raw = l.location_code_raw

-- Chỉ include jobs có trong fct_job_posting
WHERE j.job_id IN (SELECT job_id FROM {{ ref('fct_job_posting') }})
