{{ config(
    materialized='table'
) }}

-- Lấy thông tin từ silver.companies
-- Ở Phase 1, ta giả định công ty không thay đổi tên nhiều, nên copy dạng Type 1.

SELECT
    company_id,
    normalized_name,
    display_name,
    website,
    industry,
    company_size,
    is_anonymous,
    created_at AS source_created_at
FROM {{ source('silver', 'companies') }}
