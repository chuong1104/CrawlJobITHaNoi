{{ config(
    materialized='table'
) }}

-- ============================================================
-- dim_source.sql — Danh sách các nguồn dữ liệu tuyển dụng
-- Hardcoded vì ít thay đổi — thêm nguồn mới thì update tại đây
-- ============================================================

SELECT *
FROM (
    VALUES
        (1, 'topcv',        'TopCV',         'https://www.topcv.vn'),
        (2, 'itviec',       'ITviec',         'https://itviec.com'),
        (3, 'vietnamworks', 'VietnamWorks',   'https://www.vietnamworks.com'),
        (4, 'jobsgo',       'JobsGo',         'https://jobsgo.vn'),
        (5, 'linkedin',     'LinkedIn',       'https://www.linkedin.com'),
        (6, '123job',       '123Job',         'https://www.123job.vn'),
        (8, 'careerviet',   'CareerViet',     'https://careerviet.vn'),
        (9, 'joboko',       'JobOko',         'https://joboko.com')
) AS t(source_id, source_code, source_name, base_url)
