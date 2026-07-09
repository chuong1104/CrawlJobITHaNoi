{{ config(
    materialized='incremental',
    unique_key=['skill_code', 'week_start_date'],
    incremental_strategy='merge'
) }}

-- =============================================================================
-- agg_skill_trend_weekly.sql — Xu hướng nhu cầu kỹ năng theo tuần
--
-- Tính tốc độ tăng trưởng (growth_rate) của từng kỹ năng so với tuần trước.
-- Phục vụ cho Power BI chart "Rising Skills" và "Declining Skills".
--
-- Aligned với Semantic Layer metrics: data_jobs_count, backend_jobs_count
-- =============================================================================

WITH weekly_skill_demand AS (
    -- Số lần kỹ năng xuất hiện trong tuần, theo rolling window
    SELECT
        sk.skill_code,
        sk.display_name                         AS skill_name,
        sk.skill_category,
        -- Tuần bắt đầu (Monday)
        DATE_TRUNC('week', CAST(
            SUBSTR(CAST(f.first_seen_date_key AS VARCHAR), 1, 4) || '-' ||
            SUBSTR(CAST(f.first_seen_date_key AS VARCHAR), 5, 2) || '-' ||
            SUBSTR(CAST(f.first_seen_date_key AS VARCHAR), 7, 2)
        AS DATE))                               AS week_start_date,
        COUNT(DISTINCT fjs.job_id)              AS job_count
    FROM {{ ref('fct_job_skill') }}             fjs
    JOIN {{ ref('fct_job_posting') }}           f   ON fjs.job_id = f.job_id
    JOIN {{ source('silver', 'skills') }}       sk  ON fjs.skill_id = sk.skill_id
    WHERE f.is_active = TRUE
    GROUP BY 1, 2, 3, 4
),

-- Tính growth rate so với tuần trước (LAG)
with_growth AS (
    SELECT
        skill_code,
        skill_name,
        skill_category,
        week_start_date,
        job_count,
        -- Tuần trước
        LAG(job_count) OVER (
            PARTITION BY skill_code ORDER BY week_start_date
        )                                       AS prev_week_count,
        -- Growth rate (%)
        ROUND(
            (job_count - LAG(job_count) OVER (PARTITION BY skill_code ORDER BY week_start_date))
            * 100.0
            / NULLIF(LAG(job_count) OVER (PARTITION BY skill_code ORDER BY week_start_date), 0),
            2
        )                                       AS week_over_week_growth_pct,
        -- 4-week rolling average (smoothing)
        ROUND(AVG(job_count) OVER (
            PARTITION BY skill_code
            ORDER BY week_start_date
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ), 1)                                   AS rolling_4w_avg,
        -- Rank trong tuần (top skills)
        RANK() OVER (
            PARTITION BY week_start_date
            ORDER BY job_count DESC
        )                                       AS weekly_rank
    FROM weekly_skill_demand
),

-- Phân loại xu hướng
final AS (
    SELECT
        skill_code,
        skill_name,
        skill_category,
        week_start_date,
        job_count,
        prev_week_count,
        COALESCE(week_over_week_growth_pct, 0)  AS growth_rate_pct,
        rolling_4w_avg,
        weekly_rank,
        -- Phân loại trend
        CASE
            WHEN week_over_week_growth_pct > 20  THEN 'RISING_FAST'
            WHEN week_over_week_growth_pct > 5   THEN 'RISING'
            WHEN week_over_week_growth_pct < -20 THEN 'DECLINING_FAST'
            WHEN week_over_week_growth_pct < -5  THEN 'DECLINING'
            ELSE                                      'STABLE'
        END                                     AS trend_label,
        -- Momentum (rolling trend direction)
        CASE
            WHEN rolling_4w_avg > LAG(rolling_4w_avg, 2) OVER (
                PARTITION BY skill_code ORDER BY week_start_date
            ) THEN 'UPWARD'
            WHEN rolling_4w_avg < LAG(rolling_4w_avg, 2) OVER (
                PARTITION BY skill_code ORDER BY week_start_date
            ) THEN 'DOWNWARD'
            ELSE 'SIDEWAYS'
        END                                     AS momentum
    FROM with_growth
)

SELECT *
FROM final

{% if is_incremental() %}
WHERE week_start_date >= (SELECT MAX(week_start_date) FROM {{ this }}) - INTERVAL '4 weeks'
-- Reload 4 tuần gần nhất để đảm bảo rolling avg chính xác
{% endif %}
