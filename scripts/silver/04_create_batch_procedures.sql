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
    v_record RECORD;
    v_source_id SMALLINT;
    v_company_id INT;
    v_action VARCHAR;
    v_processed_count INT := 0;
    v_new_count INT := 0;
    v_updated_count INT := 0;
BEGIN
    RAISE INFO 'Starting batch processing for session_id: %, batch_date: %', p_session_id, p_batch_date;

    FOR v_record IN (
        SELECT * FROM staging.stg_jobs 
        WHERE batch_date = p_batch_date
    )
    LOOP
        -- 1. Lấy source_id từ danh mục (nếu không có thì báo lỗi nhưng ở đây đảm bảo có sẵn)
        SELECT source_id INTO v_source_id FROM silver.sources WHERE source_code = v_record.source_code;
        
        IF v_source_id IS NULL THEN
            RAISE WARNING 'Source code % not found. Skipping record.', v_record.source_code;
            CONTINUE;
        END IF;

        -- 2. Resolve company (Gọi SP resolve company)
        v_company_id := silver.sp_resolve_company(v_record.company_normalized, v_source_id);

        -- 3. Gọi Upsert Job
        v_action := silver.sp_upsert_job(
            p_source_id := v_source_id,
            p_company_id := v_company_id,
            p_source_job_id := v_record.source_job_id,
            p_canonical_url := v_record.canonical_url,
            p_identity_hash := v_record.identity_hash,
            p_content_hash := v_record.content_hash,
            p_title_raw := v_record.title_raw,
            p_title_clean := v_record.title_clean,
            p_description := v_record.description,
            p_salary_raw := v_record.salary_raw,
            p_salary_min := v_record.salary_min,
            p_salary_max := v_record.salary_max,
            p_experience_raw := v_record.experience_raw,
            p_experience_min := v_record.experience_min_years,
            p_experience_max := v_record.experience_max_years,
            p_job_level := v_record.job_level,
            p_job_type := v_record.job_type,
            p_work_mode := v_record.work_mode,
            p_job_family := v_record.job_family,
            p_deadline_raw := v_record.deadline_raw,
            p_deadline_date := v_record.deadline_date,
            p_is_intern := v_record.is_intern,
            p_is_fresher := v_record.is_fresher,
            p_skills_raw := v_record.skills_raw,
            p_scraped_at := v_record.scraped_at,
            p_session_id := p_session_id
        );

        v_processed_count := v_processed_count + 1;
        IF v_action = 'NEW' THEN
            v_new_count := v_new_count + 1;
        ELSIF v_action = 'UPDATED' THEN
            v_updated_count := v_updated_count + 1;
        END IF;
    END LOOP;

    -- Update session statistics
    UPDATE silver.crawl_sessions
    SET total_validated = v_processed_count
    WHERE session_id = p_session_id;

    RAISE INFO 'Batch processing complete. Processed: %, New: %, Updated: %', v_processed_count, v_new_count, v_updated_count;
END;
$$;

COMMIT;
