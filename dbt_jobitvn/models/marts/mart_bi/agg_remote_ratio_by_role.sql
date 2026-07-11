{{ config(
    materialized='table'
) }}

-- ============================================================
-- agg_remote_ratio_by_industry.sql
-- Câu hỏi: "Ngành / role nào có tỉ lệ Remote/Hybrid cao nhất?"
-- ============================================================

WITH base AS (
    SELECT
        job_id,
        job_family,
        work_mode,
        location_code,
        source_code
    FROM {{ ref('fct_job_posting') }}
    WHERE is_active = TRUE
),

stats AS (
    SELECT
        job_family,
        COUNT(DISTINCT job_id)                                      AS total_jobs,
        COUNT(DISTINCT CASE WHEN work_mode = 'REMOTE'  THEN job_id END) AS remote_jobs,
        COUNT(DISTINCT CASE WHEN work_mode = 'HYBRID'  THEN job_id END) AS hybrid_jobs,
        COUNT(DISTINCT CASE WHEN work_mode = 'ONSITE'  THEN job_id END) AS onsite_jobs,
        ROUND(
            COUNT(DISTINCT CASE WHEN work_mode IN ('REMOTE','HYBRID') THEN job_id END) * 100.0
            / NULLIF(COUNT(DISTINCT job_id), 0), 1
        )                                                           AS remote_hybrid_pct,
        ROUND(
            COUNT(DISTINCT CASE WHEN work_mode = 'REMOTE' THEN job_id END) * 100.0
            / NULLIF(COUNT(DISTINCT job_id), 0), 1
        )                                                           AS remote_only_pct
    FROM base
    GROUP BY job_family
)

SELECT
    job_family,
    total_jobs,
    remote_jobs,
    hybrid_jobs,
    onsite_jobs,
    remote_hybrid_pct,
    remote_only_pct,
    RANK() OVER (ORDER BY remote_hybrid_pct DESC) AS remote_friendliness_rank
FROM stats
WHERE total_jobs >= 5
ORDER BY remote_hybrid_pct DESC
