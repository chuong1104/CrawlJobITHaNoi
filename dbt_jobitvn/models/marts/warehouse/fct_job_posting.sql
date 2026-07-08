{{ config(
    materialized='incremental',
    unique_key='job_id',
    incremental_strategy='merge'
) }}

-- Bảng Fact chính lưu trữ thông tin các tin tuyển dụng.
-- Join giữa silver.jobs và silver.job_snapshots (lấy snapshot is_current = TRUE)

WITH current_jobs AS (
    SELECT
        j.job_id,
        j.source_id,
        j.company_id,
        j.source_job_id,
        j.canonical_url,
        j.job_status,
        j.is_active,
        TO_CHAR(j.first_seen_at, 'YYYYMMDD')::INT AS first_seen_date_key,
        TO_CHAR(j.last_seen_at, 'YYYYMMDD')::INT AS last_seen_date_key,
        TO_CHAR(j.closed_at, 'YYYYMMDD')::INT AS closed_date_key,
        
        -- Snapshot data
        s.snapshot_id,
        s.title_clean,
        s.salary_min,
        s.salary_max,
        s.salary_avg,
        s.salary_currency,
        s.experience_min_years,
        s.experience_max_years,
        s.job_level,
        s.job_type,
        s.work_mode,
        s.job_family,
        TO_CHAR(s.deadline_date, 'YYYYMMDD')::INT AS deadline_date_key,
        s.is_intern,
        s.is_fresher,
        
        -- Dùng updated_at của job để xử lý incremental
        j.updated_at
        
    FROM {{ source('silver', 'jobs') }} j
    JOIN {{ source('silver', 'job_snapshots') }} s 
      ON j.job_id = s.job_id AND s.is_current = TRUE

    {% if is_incremental() %}
      -- Lọc những bản ghi có thay đổi kể từ lần run dbt trước
      WHERE j.updated_at > (SELECT MAX(updated_at) FROM {{ this }})
    {% endif %}
)

SELECT * FROM current_jobs
