{{ config(
    materialized='table'
) }}

-- Phát hiện thay đổi (Pseudo-CDC)
-- So sánh bản ghi mới nhất với trạng thái hiện tại trong CSDL Silver (đọc từ Postgres nếu chạy cross-db,
-- hoặc dbt snapshot nếu cấu hình snapshot. Ở đây ta chuẩn bị data change_type dựa trên lag).

WITH deduped_jobs AS (
    SELECT * FROM {{ ref('int_deduped_jobs') }}
),

-- Trong môi trường thực tế, bước này sẽ join trực tiếp với bảng `silver.jobs` thông qua 
-- dbt source để lấy latest_content_hash hiện tại trong Postgres.
-- Tuy nhiên, để dbt chỉ chạy trên DuckDB (ELT thuần tuý), phần so sánh hash này 
-- sẽ được thực hiện tại Python Sync Engine. 
-- Do đó mô hình này sẽ chuẩn bị format chuẩn để xuất cho Python script.

final AS (
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
    FROM deduped_jobs
)

SELECT * FROM final
