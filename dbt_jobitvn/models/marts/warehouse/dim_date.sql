{{ config(
    materialized='table'
) }}

WITH date_spine AS (
    -- Tạo danh sách các ngày từ 2024 đến 2030 (ví dụ)
    SELECT 
        (DATE '2024-01-01' + (n || ' days')::INTERVAL)::DATE AS date_day
    FROM generate_series(0, 3650) n
)

SELECT
    date_day,
    TO_CHAR(date_day, 'YYYYMMDD')::INT AS date_key,
    EXTRACT(YEAR FROM date_day)::INT AS year,
    EXTRACT(MONTH FROM date_day)::INT AS month,
    EXTRACT(DAY FROM date_day)::INT AS day,
    EXTRACT(QUARTER FROM date_day)::INT AS quarter,
    EXTRACT(DOW FROM date_day)::INT AS day_of_week,
    EXTRACT(WEEK FROM date_day)::INT AS week_of_year,
    TO_CHAR(date_day, 'Day') AS day_name,
    TO_CHAR(date_day, 'Month') AS month_name,
    CASE 
        WHEN EXTRACT(DOW FROM date_day) IN (0, 6) THEN TRUE 
        ELSE FALSE 
    END AS is_weekend
FROM date_spine
