{{ config(
    materialized='table'
) }}

-- Bridge table kết nối giữa job_id và skill_id
-- Do fct_job_posting chỉ lấy snapshot hiện tại, ta cũng lấy liên kết skill của snapshot đó.

SELECT
    j.job_id,
    js.skill_id,
    js.is_primary,
    js.skill_position
FROM {{ source('silver', 'jobs') }} j
JOIN {{ source('silver', 'job_snapshots') }} s ON j.job_id = s.job_id AND s.is_current = TRUE
JOIN {{ source('silver', 'job_snapshot_skills') }} js ON s.snapshot_id = js.snapshot_id
