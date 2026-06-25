-- Lỗi nếu posted_date là ngày trong tương lai (không hợp lý)

SELECT *
FROM {{ ref('int_changed_jobs') }}
WHERE posted_date_raw > CURRENT_DATE
