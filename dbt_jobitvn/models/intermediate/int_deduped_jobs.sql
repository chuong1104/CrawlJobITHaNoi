{{ config(
    materialized='table'
) }}

-- Loại bỏ trùng lặp trong cùng một batch (cùng source_code và source_job_id)
-- Giữ lại bản ghi được quét muộn nhất (scraped_at DESC)

WITH unioned_jobs AS (
    SELECT * FROM {{ ref('int_all_jobs_unioned') }}
),

ranked_jobs AS (
    SELECT 
        *,
        ROW_NUMBER() OVER (
            PARTITION BY source_code, source_job_id 
            ORDER BY scraped_at DESC
        ) as rn
    FROM unioned_jobs
)

SELECT * EXCLUDE(rn)
FROM ranked_jobs
WHERE rn = 1
