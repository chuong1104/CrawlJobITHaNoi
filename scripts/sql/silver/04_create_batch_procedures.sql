-- =============================================================================
-- Silver Layer — Batch Processing Stored Procedures
-- File: 04_create_batch_procedures.sql
-- Description: Xử lý hàng loạt dữ liệu từ staging.stg_jobs để nạp vào silver.
-- =============================================================================

BEGIN;

CREATE OR REPLACE PROCEDURE silver.sp_process_staging_batch(
    p_session_id BIGINT,
    p_batch_date DATE DEFAULT CURRENT_DATE
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_processed_count INT;
BEGIN
    RAISE INFO 'Starting optimized batch processing for session_id: %, batch_date: %', p_session_id, p_batch_date;

    -- 1. Bulk insert các company mới từ staging (không trùng lặp normalized_name)
    INSERT INTO silver.companies (normalized_name, display_name)
    SELECT DISTINCT company_normalized, company_raw
    FROM staging.stg_jobs
    WHERE batch_date = p_batch_date
      AND company_normalized IS NOT NULL
    ON CONFLICT (normalized_name) DO NOTHING;

    -- 2. Bulk insert company aliases
    INSERT INTO silver.company_aliases (company_id, alias_text, source_id, confidence)
    SELECT DISTINCT c.company_id, stg.company_raw, src.source_id, 100
    FROM staging.stg_jobs stg
    JOIN silver.sources src ON stg.source_code = src.source_code
    JOIN silver.companies c ON stg.company_normalized = c.normalized_name
    WHERE stg.batch_date = p_batch_date
    ON CONFLICT (alias_text) DO NOTHING;

    -- 3. Bulk Upsert vào silver.jobs sử dụng CTE
    WITH upserted_jobs AS (
        INSERT INTO silver.jobs (
            source_id, company_id, source_job_id, canonical_url,
            identity_hash, latest_content_hash, job_status, is_active, first_seen_at, last_seen_at
        )
        SELECT 
            src.source_id,
            c.company_id,
            stg.source_job_id,
            stg.canonical_url,
            stg.identity_hash,
            stg.content_hash,
            'ACTIVE'::job_status_enum,
            TRUE,
            stg.scraped_at,
            stg.scraped_at
        FROM staging.stg_jobs stg
        JOIN silver.sources src ON stg.source_code = src.source_code
        JOIN silver.companies c ON stg.company_normalized = c.normalized_name
        WHERE stg.batch_date = p_batch_date
        ON CONFLICT (source_id, source_job_id) 
        DO UPDATE SET 
            last_seen_at = EXCLUDED.last_seen_at,
            not_found_count = 0,
            -- Nếu content hash thay đổi, cập nhật status để trigger SCD type 2 ở bước sau
            job_status = CASE WHEN silver.jobs.latest_content_hash != EXCLUDED.latest_content_hash THEN 'UPDATED'::job_status_enum ELSE silver.jobs.job_status END,
            latest_content_hash = EXCLUDED.latest_content_hash,
            updated_at = NOW()
        RETURNING job_id, source_job_id, latest_content_hash, (created_at = updated_at) AS is_new
    )
    SELECT COUNT(*) INTO v_processed_count FROM upserted_jobs;

    -- 4. Bulk xử lý SCD Type 2 Snapshots:
    -- Đóng các snapshot cũ nếu có cập nhật content hash
    UPDATE silver.job_snapshots js
    SET is_current = FALSE,
        valid_to = stg.scraped_at
    FROM staging.stg_jobs stg
    JOIN silver.sources src ON stg.source_code = src.source_code
    JOIN silver.jobs j ON j.source_id = src.source_id AND j.source_job_id = stg.source_job_id
    WHERE stg.batch_date = p_batch_date
      AND js.job_id = j.job_id
      AND js.is_current = TRUE
      AND j.latest_content_hash != js.content_hash;

    -- Insert các snapshot mới
    INSERT INTO silver.job_snapshots (
        job_id, is_current, valid_from, version_number,
        title_raw, title_clean, description,
        salary_raw, salary_min, salary_max,
        experience_raw, experience_min_years, experience_max_years,
        job_level, job_type, work_mode, job_family,
        deadline_raw, deadline_date, is_intern, is_fresher, content_hash
    )
    SELECT 
        j.job_id,
        TRUE,
        stg.scraped_at,
        COALESCE(prev.version_number, 0) + 1,
        stg.title_raw, stg.title_clean, stg.description,
        stg.salary_raw, stg.salary_min, stg.salary_max,
        stg.experience_raw, stg.experience_min_years, stg.experience_max_years,
        stg.job_level, stg.job_type, stg.work_mode, stg.job_family,
        stg.deadline_raw, stg.deadline_date, stg.is_intern, stg.is_fresher, stg.content_hash
    FROM staging.stg_jobs stg
    JOIN silver.sources src ON stg.source_code = src.source_code
    JOIN silver.jobs j ON j.source_id = src.source_id AND j.source_job_id = stg.source_job_id
    LEFT JOIN silver.job_snapshots prev ON prev.job_id = j.job_id AND prev.valid_to = stg.scraped_at
    WHERE stg.batch_date = p_batch_date
      AND NOT EXISTS (
          SELECT 1 FROM silver.job_snapshots active 
          WHERE active.job_id = j.job_id AND active.is_current = TRUE AND active.content_hash = stg.content_hash
      );

    -- 5. Cập nhật crawl session stats
    UPDATE silver.crawl_sessions
    SET total_validated = v_processed_count
    WHERE session_id = p_session_id;

    RAISE INFO 'Batch processing complete. Processed % jobs.', v_processed_count;
END;
$$;

COMMIT;
