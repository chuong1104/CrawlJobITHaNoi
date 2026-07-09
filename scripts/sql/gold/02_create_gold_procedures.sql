-- =============================================================================
-- Gold Layer — Data Warehouse Procedures
-- File: 02_create_gold_procedures.sql
-- Description: ETL từ schema silver sang schema dwh (Star Schema).
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
    
    -- Ghi chú: Nếu công ty đổi tên ở Silver, ta sẽ UPDATE valid_to của bản ghi cũ 
    -- và INSERT bản ghi mới (SCD Type 2). Tuy nhiên, vì Silver hiện tại ít update tên công ty 
    -- nên tạm thời bỏ qua bước SCD logic phức tạp cho MVP.
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


-- 3. Sync Fact Job Posting
CREATE OR REPLACE PROCEDURE dwh.sp_sync_fact_job_posting()
LANGUAGE plpgsql
AS $$
BEGIN
    -- Insert Fact mới từ Silver Jobs & Snapshots
    INSERT INTO dwh.fct_job_posting (
        silver_job_id, silver_snapshot_id, posted_date_key, 
        company_key, source_key, attribute_key,
        salary_min_vnd, salary_max_vnd, salary_midpoint_vnd,
        experience_min_years, experience_max_years,
        is_active, is_intern, is_fresher, has_salary
    )
    SELECT 
        j.job_id,
        s.snapshot_id,
        -- Chuyển đổi posted_date thành Date Key (YYYYMMDD)
        CAST(TO_CHAR(COALESCE(s.valid_from, j.first_seen_at), 'YYYYMMDD') AS INT) AS posted_date_key,
        dc.company_key,
        ds.source_key,
        1, -- Tạm gán 1 cho attribute_key (Có thể viết logic lookup sau)
        
        s.salary_min,
        s.salary_max,
        (s.salary_min + s.salary_max) / 2 AS salary_midpoint_vnd,
        s.experience_min_years,
        s.experience_max_years,
        
        j.is_active,
        s.is_intern,
        s.is_fresher,
        CASE WHEN s.salary_min IS NOT NULL OR s.salary_max IS NOT NULL THEN TRUE ELSE FALSE END
        
    FROM silver.jobs j
    JOIN silver.job_snapshots s ON j.job_id = s.job_id
    -- Lookup Company Key
    JOIN dwh.dim_company dc ON j.company_id = dc.silver_company_id AND dc.is_current = TRUE
    -- Lookup Source Key
    JOIN dwh.dim_source ds ON j.source_id = ds.silver_source_id
    
    ON CONFLICT (silver_snapshot_id) DO NOTHING;

    -- Cập nhật trạng thái is_active cho Fact nếu Job ở Silver đã bị đóng
    UPDATE dwh.fct_job_posting f
    SET is_active = j.is_active
    FROM silver.jobs j
    WHERE f.silver_job_id = j.job_id AND f.is_active != j.is_active;

END;
$$;


-- 4. Refresh Materialized View cho API
CREATE OR REPLACE PROCEDURE dwh.sp_refresh_mart_api()
LANGUAGE plpgsql
AS $$
BEGIN
    -- Chạy lệnh Refresh MV
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart_api.latest_jobs_flat;
    -- Nếu chưa có Unique Index để chạy CONCURRENTLY, lệnh trên sẽ báo lỗi.
    -- (Ta đã tạo Unique Index ở file 01).
END;
$$;


-- 5. Sync Skills and Locations
CREATE OR REPLACE PROCEDURE dwh.sp_sync_skills_and_locations()
LANGUAGE plpgsql
AS $$
BEGIN
    -- Sync dim_skill
    INSERT INTO dwh.dim_skill (silver_skill_id, skill_name, skill_category)
    SELECT skill_id, display_name, 'IT'
    FROM silver.skills
    ON CONFLICT (silver_skill_id) DO NOTHING;

    -- Sync bridge_job_skill
    INSERT INTO dwh.bridge_job_skill (job_posting_fact_id, skill_key)
    SELECT DISTINCT f.job_posting_fact_id, dk.skill_key
    FROM dwh.fct_job_posting f
    JOIN silver.job_snapshot_skills jss ON f.silver_snapshot_id = jss.snapshot_id
    JOIN dwh.dim_skill dk ON jss.skill_id = dk.silver_skill_id
    ON CONFLICT (job_posting_fact_id, skill_key) DO NOTHING;

    -- Sync dim_location
    INSERT INTO dwh.dim_location (silver_location_id, location_name, region) VALUES
    (1, 'Hà Nội', 'Miền Bắc'),
    (2, 'Hồ Chí Minh', 'Miền Nam'),
    (3, 'Đà Nẵng', 'Miền Trung')
    ON CONFLICT (silver_location_id) DO NOTHING;

    -- Sync bridge_job_location
    INSERT INTO dwh.bridge_job_location (job_posting_fact_id, location_key)
    SELECT 
        f.job_posting_fact_id,
        CASE 
            WHEN s.title_clean ILIKE '%Hồ Chí Minh%' OR s.title_clean ILIKE '%HCM%' OR s.title_clean ILIKE '%HCMC%' OR s.title_clean ILIKE '%Sài Gòn%' THEN 
                (SELECT location_key FROM dwh.dim_location WHERE location_name = 'Hồ Chí Minh')
            WHEN s.title_clean ILIKE '%Đà Nẵng%' OR s.title_clean ILIKE '%ĐN%' THEN 
                (SELECT location_key FROM dwh.dim_location WHERE location_name = 'Đà Nẵng')
            ELSE 
                (SELECT location_key FROM dwh.dim_location WHERE location_name = 'Hà Nội')
        END as location_key
    FROM dwh.fct_job_posting f
    JOIN silver.job_snapshots s ON f.silver_snapshot_id = s.snapshot_id AND s.is_current = TRUE
    ON CONFLICT (job_posting_fact_id, location_key) DO NOTHING;
END;
$$;

COMMIT;

SELECT 'Gold Procedures Created Successfully' AS status;
