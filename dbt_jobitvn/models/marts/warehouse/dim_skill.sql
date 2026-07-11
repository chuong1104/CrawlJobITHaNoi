{{ config(
    materialized='table'
) }}

-- ============================================================
-- dim_skill.sql — Danh sách kỹ năng IT (từ seed mapping)
-- Source: dim_skill_mapping seed — bộ kỹ năng đã chuẩn hóa
-- ============================================================

SELECT DISTINCT
    MD5(normalized_skill)   AS skill_id,
    normalized_skill        AS skill_code,
    -- Display name: format đẹp hơn
    CASE normalized_skill
        WHEN 'reactjs'          THEN 'React.js'
        WHEN 'vuejs'            THEN 'Vue.js'
        WHEN 'nodejs'           THEN 'Node.js'
        WHEN 'python'           THEN 'Python'
        WHEN 'javascript'       THEN 'JavaScript'
        WHEN 'typescript'       THEN 'TypeScript'
        WHEN 'html_css'         THEN 'HTML/CSS'
        WHEN 'sql'              THEN 'SQL'
        WHEN 'postgresql'       THEN 'PostgreSQL'
        WHEN 'mongodb'          THEN 'MongoDB'
        WHEN 'sql_server'       THEN 'SQL Server'
        WHEN 'aws'              THEN 'AWS'
        WHEN 'gcp'              THEN 'GCP'
        WHEN 'azure'            THEN 'Azure'
        WHEN 'docker'           THEN 'Docker'
        WHEN 'kubernetes'       THEN 'Kubernetes'
        WHEN 'apache_spark'     THEN 'Apache Spark'
        WHEN 'power_bi'         THEN 'Power BI'
        WHEN 'machine_learning' THEN 'Machine Learning'
        WHEN 'deep_learning'    THEN 'Deep Learning'
        WHEN 'cicd'             THEN 'CI/CD'
        WHEN 'git'              THEN 'Git'
        WHEN 'english'          THEN 'English'
        WHEN 'agile'            THEN 'Agile/Scrum'
        ELSE UPPER(SUBSTRING(REPLACE(normalized_skill, '_', ' '), 1, 1)) || LOWER(SUBSTRING(REPLACE(normalized_skill, '_', ' '), 2))
    END                     AS display_name,
    skill_category,
    skill_subcategory,
    TRUE                    AS is_active
FROM {{ ref('dim_skill_mapping') }}
ORDER BY skill_category, display_name
