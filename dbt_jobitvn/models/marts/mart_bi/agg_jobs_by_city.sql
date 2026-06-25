{{ config(
    materialized='view'
) }}

-- Thống kê số lượng việc làm hiện tại theo thành phố

WITH active_jobs AS (
    SELECT 
        j.job_id,
        l.display_name AS city_name,
        l.region
    FROM {{ ref('fct_job_posting') }} j
    JOIN {{ source('silver', 'job_snapshot_locations') }} sl 
      ON j.snapshot_id = sl.snapshot_id
    JOIN {{ ref('dim_location') }} l 
      ON sl.location_id = l.location_id
    WHERE j.is_active = TRUE
)

SELECT 
    region,
    city_name,
    COUNT(DISTINCT job_id) AS active_job_count
FROM active_jobs
GROUP BY 1, 2
ORDER BY active_job_count DESC
