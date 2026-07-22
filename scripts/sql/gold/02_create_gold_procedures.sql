-- =============================================================================
-- Gold Layer — Data Warehouse Procedures
-- File: 02_create_gold_procedures.sql
-- Description: ETL từ schema silver sang schema dwh (Star Schema).
--              Tối ưu hóa Giai đoạn 3 (Incremental Load & Structured Joins).
-- =============================================================================

BEGIN;

-- 1. Sync Dim Company (SCD Type 2)
CREATE OR REPLACE PROCEDURE dwh.sp_sync_dim_company()
LANGUAGE plpgsql
AS $$
BEGIN
    -- Insert công ty mới (Chưa có trong dwh)
    INSERT INTO dwh.dim_company (silver_company_id, company_name, industry, company_size_category, valid_from, is_current)
    SELECT 
        c.company_id, 
        c.display_name, 
        NULL, -- Tạm thời trống, có thể enrich sau
        'Unknown', 
        CURRENT_TIMESTAMP, 
        TRUE
    FROM silver.companies c
    LEFT JOIN dwh.dim_company d ON c.company_id = d.silver_company_id
    WHERE d.silver_company_id IS NULL;
END;
$$;


-- 2. Sync Dim Source
CREATE OR REPLACE PROCEDURE dwh.sp_sync_dim_source()
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO dwh.dim_source (silver_source_id, source_name, base_url)
    SELECT source_id, display_name, base_url 
    FROM silver.sources s
    ON CONFLICT (silver_source_id) DO NOTHING;
END;
$$;


-- 3. Sync Fact Job Posting (Incremental CDC)
CREATE OR REPLACE PROCEDURE dwh.sp_sync_fact_job_posting()
LANGUAGE plpgsql
AS $$
DECLARE
    v_last_load TIMESTAMPTZ;
BEGIN
    -- Tìm thời điểm đồng bộ gần nhất
    SELECT COALESCE(MAX(loaded_at), '1970-01-01'::TIMESTAMPTZ) 
    INTO v_last_load 
    FROM dwh.fct_job_posting;

    -- Upsert Fact mới từ Silver Jobs & Snapshots (Incremental)
    INSERT INTO dwh.fct_job_posting (
        silver_job_id, silver_snapshot_id, posted_date_key, 
        company_key, source_key, attribute_key,
        salary_min_vnd, salary_max_vnd, salary_midpoint_vnd,
        experience_min_years, experience_max_years,
        is_active, is_intern, is_fresher, has_salary, loaded_at
    )
    SELECT 
        j.job_id,
        s.snapshot_id,
        CAST(TO_CHAR(COALESCE(s.valid_from, j.first_seen_at), 'YYYYMMDD') AS INT) AS posted_date_key,
        dc.company_key,
        ds.source_key,
        1, -- Tạm gán 1 cho attribute_key
        s.salary_min,
        s.salary_max,
        (s.salary_min + s.salary_max) / 2 AS salary_midpoint_vnd,
        s.experience_min_years,
        s.experience_max_years,
        j.is_active,
        s.is_intern,
        s.is_fresher,
        CASE WHEN s.salary_min IS NOT NULL OR s.salary_max IS NOT NULL THEN TRUE ELSE FALSE END,
        NOW()
    FROM silver.jobs j
    JOIN silver.job_snapshots s ON j.job_id = s.job_id
    JOIN dwh.dim_company dc ON j.company_id = dc.silver_company_id AND dc.is_current = TRUE
    JOIN dwh.dim_source ds ON j.source_id = ds.silver_source_id
    -- Chỉ lấy các bản ghi thay đổi từ lần chạy cuối
    WHERE s.created_at >= v_last_load OR j.updated_at >= v_last_load
    ON CONFLICT (silver_snapshot_id) DO UPDATE SET
        is_active = EXCLUDED.is_active,
        salary_min_vnd = EXCLUDED.salary_min_vnd,
        salary_max_vnd = EXCLUDED.salary_max_vnd,
        salary_midpoint_vnd = EXCLUDED.salary_midpoint_vnd,
        loaded_at = NOW();
END;
$$;


-- 4. Sync Skills and Locations (Tái cấu trúc)
CREATE OR REPLACE PROCEDURE dwh.sp_sync_skills_and_locations()
LANGUAGE plpgsql
AS $$
BEGIN
    -- 4.1 Sync dim_skill
    INSERT INTO dwh.dim_skill (silver_skill_id, skill_name, skill_category)
    SELECT skill_id, display_name, 'IT'
    FROM silver.skills
    ON CONFLICT (silver_skill_id) DO NOTHING;

    -- 4.2 Sync bridge_job_skill
    INSERT INTO dwh.bridge_job_skill (job_posting_fact_id, skill_key)
    SELECT DISTINCT f.job_posting_fact_id, dk.skill_key
    FROM dwh.fct_job_posting f
    JOIN silver.job_snapshot_skills jss ON f.silver_snapshot_id = jss.snapshot_id
    JOIN dwh.dim_skill dk ON jss.skill_id = dk.silver_skill_id
    ON CONFLICT (job_posting_fact_id, skill_key) DO NOTHING;

    -- 4.3 Sync dim_location (Đồng bộ trực tiếp toàn bộ danh mục từ Silver)
    INSERT INTO dwh.dim_location (silver_location_id, location_name, region)
    SELECT location_id, display_name, COALESCE(region, 'Khác')
    FROM silver.locations
    ON CONFLICT (silver_location_id) 
    DO UPDATE SET 
        location_name = EXCLUDED.location_name,
        region = EXCLUDED.region;

    -- 4.4 Sync bridge_job_location (Structured Joins)
    INSERT INTO dwh.bridge_job_location (job_posting_fact_id, location_key)
    SELECT DISTINCT f.job_posting_fact_id, dl.location_key
    FROM dwh.fct_job_posting f
    JOIN silver.job_snapshot_locations jsl ON f.silver_snapshot_id = jsl.snapshot_id
    JOIN dwh.dim_location dl ON jsl.location_id = dl.silver_location_id
    ON CONFLICT (job_posting_fact_id, location_key) DO NOTHING;
END;
$$;


-- 5. Refresh Materialized View cho API
CREATE OR REPLACE PROCEDURE dwh.sp_refresh_mart_api()
LANGUAGE plpgsql
AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart_api.latest_jobs_flat;
END;
$$;


COMMIT;

SELECT 'Gold Procedures Created Successfully' AS status;
