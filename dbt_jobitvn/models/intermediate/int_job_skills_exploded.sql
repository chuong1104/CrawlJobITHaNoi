{{ config(
    materialized='table'
) }}

-- Explode array skills thành từng dòng để dễ dàng xử lý và map với seed.
-- Dùng hàm UNNEST của DuckDB.

WITH deduped_jobs AS (
    SELECT 
        source_code,
        source_job_id,
        skills_raw
    FROM {{ ref('int_deduped_jobs') }}
    WHERE skills_raw IS NOT NULL
)

SELECT 
    source_code,
    source_job_id,
    UNNEST(skills_raw) AS skill_raw_item
FROM deduped_jobs
