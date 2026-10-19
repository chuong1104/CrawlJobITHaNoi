{{ config(
    materialized='table'
) }}

-- ============================================================
-- agg_salary_by_experience.sql
-- Câu hỏi: "Lương tăng như thế nào theo kinh nghiệm?"
-- Phân tích: Mức lương trung bình theo khoảng năm kinh nghiệm và role
-- ============================================================

WITH base AS (
    SELECT
        job_id,
        job_family,
        experience_min_years,
        experience_max_years,
        salary_avg,
        salary_min,
        salary_max,
        salary_currency,
        has_salary,
        -- Xếp nhóm kinh nghiệm (dùng min_years là cơ sở, lọc outlier > 10 năm do dính năm thành lập cty)
        CASE
            WHEN experience_min_years IS NULL OR experience_min_years > 10 THEN 'Không xác định'
            WHEN experience_min_years = 0                       THEN '0. Fresher (0 năm)'
            WHEN experience_min_years <= 1                      THEN '1. Junior (≤1 năm)'
            WHEN experience_min_years <= 3                      THEN '2. Mid (1-3 năm)'
            WHEN experience_min_years <= 5                      THEN '3. Senior (3-5 năm)'
            ELSE                                                     '4. Lead / Expert (>5 năm)'
        END AS experience_band,
        experience_min_years AS exp_sort_key
    FROM {{ ref('fct_job_posting') }}
    WHERE is_active = TRUE
      AND salary_currency = 'VND'  -- Chỉ lấy VND để so sánh hợp lý
),

stats AS (
    SELECT
        experience_band,
        exp_sort_key,
        job_family,
        COUNT(DISTINCT job_id)                          AS total_jobs,
        COUNT(DISTINCT CASE WHEN has_salary THEN job_id END)
                                                        AS jobs_with_salary,
        -- Salary stats (chỉ dùng jobs có salary)
        ROUND(AVG(CASE WHEN has_salary THEN salary_avg END), 0)         AS avg_salary_vnd,
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY salary_avg), 0)
                                                        AS median_salary_vnd,
        ROUND(MIN(CASE WHEN has_salary THEN salary_min END), 0)         AS min_salary_vnd,
        ROUND(MAX(CASE WHEN has_salary THEN salary_max END), 0)         AS max_salary_vnd,
        -- Tỉ lệ công bố lương
        ROUND(
            COUNT(DISTINCT CASE WHEN has_salary THEN job_id END) * 100.0
            / NULLIF(COUNT(DISTINCT job_id), 0), 1
        )                                               AS salary_disclosure_pct
    FROM base
    GROUP BY 1, 2, 3
)

SELECT
    experience_band,
    job_family,
    total_jobs,
    jobs_with_salary,
    avg_salary_vnd,
    median_salary_vnd,
    min_salary_vnd,
    max_salary_vnd,
    salary_disclosure_pct,
    -- Format lương hiển thị (triệu VND)
    ROUND(avg_salary_vnd / 1000000, 1)      AS avg_salary_million_vnd,
    ROUND(median_salary_vnd / 1000000, 1)   AS median_salary_million_vnd
FROM stats
WHERE total_jobs >= 3  -- Bỏ các band quá ít data
ORDER BY exp_sort_key NULLS LAST, job_family
