{{ config(
    materialized='table'
) }}

-- ============================================================
-- dim_location.sql — Danh sách địa điểm (từ seed mapping)
-- ============================================================

SELECT DISTINCT
    MD5(normalized_location)   AS location_id,
    normalized_location        AS location_code,
    CASE normalized_location
        WHEN 'ha_noi'       THEN 'Hà Nội'
        WHEN 'ho_chi_minh'  THEN 'Hồ Chí Minh'
        WHEN 'da_nang'      THEN 'Đà Nẵng'
        WHEN 'hai_phong'    THEN 'Hải Phòng'
        WHEN 'can_tho'      THEN 'Cần Thơ'
        WHEN 'binh_duong'   THEN 'Bình Dương'
        WHEN 'dong_nai'     THEN 'Đồng Nai'
        WHEN 'remote'       THEN 'Remote'
        WHEN 'other'        THEN 'Khác / Toàn quốc'
        ELSE UPPER(SUBSTRING(REPLACE(normalized_location, '_', ' '), 1, 1)) || LOWER(SUBSTRING(REPLACE(normalized_location, '_', ' '), 2))
    END                        AS display_name,
    region,
    CAST(is_remote AS BOOLEAN) AS is_remote
FROM {{ ref('dim_location_mapping') }}
ORDER BY region NULLS LAST, display_name
