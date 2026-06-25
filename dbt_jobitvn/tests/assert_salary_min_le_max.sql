-- Lỗi nếu salary_min lớn hơn salary_max (nếu cả 2 đều tồn tại)

SELECT *
FROM {{ ref('int_changed_jobs') }}
WHERE salary_min IS NOT NULL 
  AND salary_max IS NOT NULL 
  AND salary_min > salary_max
