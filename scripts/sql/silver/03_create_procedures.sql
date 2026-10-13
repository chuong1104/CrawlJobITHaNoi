-- =============================================================================
-- Silver Layer — PL/pgSQL Stored Procedures
-- File: 03_create_procedures.sql
-- Description: Chứa logic nghiệp vụ xử lý dữ liệu từ Staging vào Silver.
-- =============================================================================

BEGIN;

-- =============================================================================
-- 1. SP: Chuẩn hóa và mapping Tên Công Ty (sp_resolve_company)
-- =============================================================================
-- Input: Tên công ty gốc từ nguồn.
-- Output: company_id (Đã có hoặc mới tạo).
CREATE OR REPLACE FUNCTION silver.sp_resolve_company(
    p_company_raw VARCHAR,
    p_source_id SMALLINT
) RETURNS INT AS $$
DECLARE
    v_company_id INT;
    v_normalized VARCHAR;
    v_alias_id INT;
BEGIN
    -- 1. Chuẩn hóa cơ bản (Bỏ TNHH, JSC, Co. Ltd...)
    -- Đơn giản hóa trong SQL, có thể viết logic phức tạp hơn ở dbt/Python
    v_normalized := TRIM(REGEXP_REPLACE(
        UPPER(p_company_raw),
        '\s*(CO\.\s*LTD|COMPANY LIMITED|TNHH|CỔ PHẦN|JSC|CORPORATION|CORP)\.?\s*$',
        '',
        'i'
    ));

    -- 2. Tìm trong company_aliases
    SELECT company_id INTO v_company_id
    FROM silver.company_aliases
    WHERE alias_text = p_company_raw;

    IF v_company_id IS NOT NULL THEN
        RETURN v_company_id;
    END IF;

    -- 3. Tìm trực tiếp trong companies theo normalized_name
    SELECT company_id INTO v_company_id
    FROM silver.companies
    WHERE normalized_name = v_normalized
    LIMIT 1;

    -- 4. Nếu chưa có, tạo company mới
    IF v_company_id IS NULL THEN
        INSERT INTO silver.companies (normalized_name, display_name)
        VALUES (v_normalized, p_company_raw)
        RETURNING company_id INTO v_company_id;
    END IF;

    -- 5. Lưu lại alias mới để lần sau lookup nhanh hơn
    INSERT INTO silver.company_aliases (company_id, alias_text, source_id, confidence)
    VALUES (v_company_id, p_company_raw, p_source_id, 100)
    ON CONFLICT (alias_text) DO NOTHING;

    RETURN v_company_id;
END;
$$ LANGUAGE plpgsql;


-- =============================================================================
-- 2. SP: Upsert Job & SCD Type 2 Snapshot (sp_upsert_job)
-- =============================================================================
-- Input: Dữ liệu của 1 job từ staging.
-- Logic: Khớp identity. Nếu NEW -> INSERT. Nếu UPDATED -> Đóng snapshot cũ, tạo mới.
-- Output: Action taken ('NEW', 'UPDATED', 'UNCHANGED', 'REOPENED').
CREATE OR REPLACE FUNCTION silver.sp_upsert_job(
    -- Định danh tĩnh
    p_source_id SMALLINT,
    p_company_id INT,
    p_source_job_id VARCHAR,
    p_canonical_url TEXT,
    p_identity_hash CHAR(16),
    p_content_hash CHAR(16),
    -- Nội dung động (Snapshot)
    p_title_raw TEXT,
    p_title_clean TEXT,
    p_description TEXT,
    p_salary_raw VARCHAR,
    p_salary_min NUMERIC,
    p_salary_max NUMERIC,
    p_experience_raw VARCHAR,
    p_experience_min SMALLINT,
    p_experience_max SMALLINT,
    p_job_level job_level_enum,
    p_job_type job_type_enum,
    p_work_mode work_mode_enum,
    p_job_family VARCHAR,
    p_deadline_raw VARCHAR,
    p_deadline_date DATE,
    p_is_intern BOOLEAN,
    p_is_fresher BOOLEAN,
    p_skills_raw TEXT[],
    -- Audit
    p_scraped_at TIMESTAMPTZ,
    p_session_id BIGINT
) RETURNS VARCHAR AS $$
DECLARE
    v_job_id BIGINT;
    v_current_content_hash CHAR(16);
    v_current_status job_status_enum;
    v_action VARCHAR;
    v_snapshot_id BIGINT;
    v_old_version SMALLINT;
    v_skill_name TEXT;
    v_skill_id INT;
BEGIN
    -- 1. Tìm job hiện tại (Khớp theo source_id + source_job_id HOẶC canonical_url)
    SELECT job_id, latest_content_hash, job_status
    INTO v_job_id, v_current_content_hash, v_current_status
    FROM silver.jobs
    WHERE (source_id = p_source_id AND source_job_id = p_source_job_id)
       OR (canonical_url = p_canonical_url)
    LIMIT 1;

    -- ==========================================
    -- CASE A: NEW JOB (Chưa từng tồn tại)
    -- ==========================================
    IF v_job_id IS NULL THEN
        -- A1. Insert vào jobs
        INSERT INTO silver.jobs (
            source_id, company_id, source_job_id, canonical_url,
            identity_hash, latest_content_hash, job_status, is_active, first_seen_at, last_seen_at
        ) VALUES (
            p_source_id, p_company_id, p_source_job_id, p_canonical_url,
            p_identity_hash, p_content_hash, 'ACTIVE', TRUE, p_scraped_at, p_scraped_at
        ) RETURNING job_id INTO v_job_id;

        -- A2. Insert vào job_snapshots (Version 1)
        INSERT INTO silver.job_snapshots (
            job_id, is_current, valid_from, version_number,
            title_raw, title_clean, description,
            salary_raw, salary_min, salary_max,
            experience_raw, experience_min_years, experience_max_years,
            job_level, job_type, work_mode, job_family,
            deadline_raw, deadline_date, is_intern, is_fresher, content_hash
        ) VALUES (
            v_job_id, TRUE, p_scraped_at, 1,
            p_title_raw, p_title_clean, p_description,
            p_salary_raw, 
            CASE WHEN p_salary_min IS NOT NULL AND p_salary_max IS NOT NULL AND p_salary_min > p_salary_max THEN p_salary_max ELSE p_salary_min END,
            CASE WHEN p_salary_min IS NOT NULL AND p_salary_max IS NOT NULL AND p_salary_min > p_salary_max THEN p_salary_min ELSE p_salary_max END,
            p_experience_raw, 
            CASE WHEN p_experience_min IS NOT NULL AND p_experience_max IS NOT NULL AND p_experience_min > p_experience_max THEN p_experience_max ELSE p_experience_min END,
            CASE WHEN p_experience_min IS NOT NULL AND p_experience_max IS NOT NULL AND p_experience_min > p_experience_max THEN p_experience_min ELSE p_experience_max END,
            p_job_level, p_job_type, p_work_mode, p_job_family,
            p_deadline_raw, p_deadline_date, p_is_intern, p_is_fresher, p_content_hash
        ) RETURNING snapshot_id INTO v_snapshot_id;

        -- A3. Insert Skills (Tối ưu hóa bằng Set-Based Bulk Insert với UNNEST)
        IF p_skills_raw IS NOT NULL AND array_length(p_skills_raw, 1) > 0 THEN
            WITH target_skills AS (
                SELECT DISTINCT TRIM(s) AS skill_name, LOWER(TRIM(s)) AS skill_code
                FROM unnest(p_skills_raw) s
                WHERE TRIM(s) != ''
            ),
            inserted_skills AS (
                INSERT INTO silver.skills (skill_code, display_name)
                SELECT skill_code, skill_name FROM target_skills
                ON CONFLICT (skill_code) DO UPDATE SET display_name = EXCLUDED.display_name
                RETURNING skill_id, skill_code
            )
            INSERT INTO silver.job_snapshot_skills (snapshot_id, skill_id)
            SELECT v_snapshot_id, COALESCE(ins.skill_id, s.skill_id)
            FROM target_skills ts
            LEFT JOIN inserted_skills ins ON ts.skill_code = ins.skill_code
            LEFT JOIN silver.skills s ON ts.skill_code = s.skill_code
            ON CONFLICT DO NOTHING;
        END IF;

        -- A4. Log event
        INSERT INTO silver.job_events (job_id, event_type, source_id, crawl_session_id, created_at)
        VALUES (v_job_id, 'JOB_CREATED', p_source_id, p_session_id, p_scraped_at);

        RETURN 'NEW';
    END IF;

    -- ==========================================
    -- Tồn tại Job. Cập nhật last_seen_at trước.
    -- ==========================================
    UPDATE silver.jobs
    SET last_seen_at = p_scraped_at,
        not_found_count = 0 -- Reset not found
    WHERE job_id = v_job_id;

    -- Xử lý REOPENED nếu job đang đóng/hết hạn
    IF v_current_status IN ('CLOSED', 'EXPIRED', 'NOT_FOUND') THEN
        UPDATE silver.jobs
        SET job_status = 'ACTIVE',
            is_active = TRUE,
            inactive_reason = NULL,
            reopened_at = p_scraped_at
        WHERE job_id = v_job_id;

        INSERT INTO silver.job_events (job_id, event_type, source_id, crawl_session_id, reason, created_at)
        VALUES (v_job_id, 'STATUS_REOPENED', p_source_id, p_session_id, 'Scraped again after being closed/expired', p_scraped_at);

        v_action := 'REOPENED';
    ELSE
        v_action := 'UNCHANGED';
    END IF;

    -- ==========================================
    -- CASE B: CONTENT UPDATED (SCD Type 2)
    -- ==========================================
    IF v_current_content_hash != p_content_hash THEN

        -- Lấy version hiện tại
        SELECT version_number INTO v_old_version
        FROM silver.job_snapshots
        WHERE job_id = v_job_id AND is_current = TRUE;

        -- B1. Đóng bản ghi snapshot cũ
        UPDATE silver.job_snapshots
        SET is_current = FALSE,
            valid_to = p_scraped_at
        WHERE job_id = v_job_id AND is_current = TRUE;

        -- B2. Insert snapshot mới
        INSERT INTO silver.job_snapshots (
            job_id, is_current, valid_from, version_number,
            title_raw, title_clean, description,
            salary_raw, salary_min, salary_max,
            experience_raw, experience_min_years, experience_max_years,
            job_level, job_type, work_mode, job_family,
            deadline_raw, deadline_date, is_intern, is_fresher, content_hash
        ) VALUES (
            v_job_id, TRUE, p_scraped_at, COALESCE(v_old_version, 0) + 1,
            p_title_raw, p_title_clean, p_description,
            p_salary_raw, 
            CASE WHEN p_salary_min IS NOT NULL AND p_salary_max IS NOT NULL AND p_salary_min > p_salary_max THEN p_salary_max ELSE p_salary_min END,
            CASE WHEN p_salary_min IS NOT NULL AND p_salary_max IS NOT NULL AND p_salary_min > p_salary_max THEN p_salary_min ELSE p_salary_max END,
            p_experience_raw, 
            CASE WHEN p_experience_min IS NOT NULL AND p_experience_max IS NOT NULL AND p_experience_min > p_experience_max THEN p_experience_max ELSE p_experience_min END,
            CASE WHEN p_experience_min IS NOT NULL AND p_experience_max IS NOT NULL AND p_experience_min > p_experience_max THEN p_experience_min ELSE p_experience_max END,
            p_job_level, p_job_type, p_work_mode, p_job_family,
            p_deadline_raw, p_deadline_date, p_is_intern, p_is_fresher, p_content_hash
        ) RETURNING snapshot_id INTO v_snapshot_id;

        -- B3. Insert Skills cho Snapshot mới (Tối ưu hóa bằng Set-Based Bulk Insert với UNNEST)
        IF p_skills_raw IS NOT NULL AND array_length(p_skills_raw, 1) > 0 THEN
            WITH target_skills AS (
                SELECT DISTINCT TRIM(s) AS skill_name, LOWER(TRIM(s)) AS skill_code
                FROM unnest(p_skills_raw) s
                WHERE TRIM(s) != ''
            ),
            inserted_skills AS (
                INSERT INTO silver.skills (skill_code, display_name)
                SELECT skill_code, skill_name FROM target_skills
                ON CONFLICT (skill_code) DO UPDATE SET display_name = EXCLUDED.display_name
                RETURNING skill_id, skill_code
            )
            INSERT INTO silver.job_snapshot_skills (snapshot_id, skill_id)
            SELECT v_snapshot_id, COALESCE(ins.skill_id, s.skill_id)
            FROM target_skills ts
            LEFT JOIN inserted_skills ins ON ts.skill_code = ins.skill_code
            LEFT JOIN silver.skills s ON ts.skill_code = s.skill_code
            ON CONFLICT DO NOTHING;
        END IF;

        -- B4. Cập nhật latest hash vào jobs
        UPDATE silver.jobs
        SET latest_content_hash = p_content_hash,
            job_status = 'UPDATED'
        WHERE job_id = v_job_id;

        -- B5. Log event
        INSERT INTO silver.job_events (job_id, event_type, source_id, crawl_session_id, reason, created_at)
        VALUES (v_job_id, 'CONTENT_UPDATED', p_source_id, p_session_id, 'Content hash changed', p_scraped_at);

        v_action := 'UPDATED';
    END IF;

    RETURN v_action;
END;
$$ LANGUAGE plpgsql;


-- =============================================================================
-- 3. SP: Đóng các job không tìm thấy (sp_auto_close_missing_jobs)
-- =============================================================================
-- Logic: Chạy sau khi crawl xong 1 source. Tìm các jobs của source đó
-- đang ACTIVE nhưng last_seen_at < thời điểm bắt đầu session.
-- Tăng not_found_count. Nếu >= 3 -> CLOSED.
CREATE OR REPLACE FUNCTION silver.sp_auto_close_missing_jobs(
    p_source_id SMALLINT,
    p_session_id BIGINT,
    p_session_start_time TIMESTAMPTZ
) RETURNS INT AS $$
DECLARE
    v_closed_count INT := 0;
BEGIN
    -- Chỉ thực hiện nếu session này thành công (có data)
    -- Để tránh lỗi scraper bị block làm đóng hết job
    IF NOT EXISTS (
        SELECT 1 FROM silver.crawl_sessions
        WHERE session_id = p_session_id AND total_validated > 10
    ) THEN
        RETURN 0;
    END IF;

    -- 1. Tăng not_found_count cho các job không thấy trong session này
    UPDATE silver.jobs
    SET not_found_count = not_found_count + 1
    WHERE source_id = p_source_id
      AND is_active = TRUE
      AND last_seen_at < p_session_start_time;

    -- 2. Đóng các job có not_found_count >= 3
    -- (Tối ưu: dùng CTE Returning để log event)
    WITH closed_jobs AS (
        UPDATE silver.jobs
        SET job_status = 'CLOSED',
            is_active = FALSE,
            closed_at = NOW(),
            inactive_reason = 'Not found 3 consecutive times'
        WHERE source_id = p_source_id
          AND is_active = TRUE
          AND not_found_count >= 3
        RETURNING job_id
    )
    INSERT INTO silver.job_events (job_id, event_type, source_id, crawl_session_id, reason, created_at)
    SELECT job_id, 'STATUS_CLOSED', p_source_id, p_session_id, 'Auto closed: Not found 3 times', NOW()
    FROM closed_jobs;

    GET DIAGNOSTICS v_closed_count = ROW_COUNT;

    RETURN v_closed_count;
END;
$$ LANGUAGE plpgsql;


-- =============================================================================
-- 4. SP: Hết hạn job theo deadline (sp_auto_expire_deadline)
-- =============================================================================
-- Logic: Chạy mỗi ngày 1 lần. Tìm snapshot hiện tại có deadline_date < TODAY
CREATE OR REPLACE FUNCTION silver.sp_auto_expire_deadline()
RETURNS INT AS $$
DECLARE
    v_expired_count INT := 0;
BEGIN
    WITH expired_jobs AS (
        SELECT j.job_id
        FROM silver.jobs j
        JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = TRUE
        WHERE j.is_active = TRUE
          AND s.deadline_date < CURRENT_DATE
    ),
    update_jobs AS (
        UPDATE silver.jobs j
        SET job_status = 'EXPIRED',
            is_active = FALSE,
            expired_at = NOW(),
            inactive_reason = 'Auto expired based on deadline'
        FROM expired_jobs e
        WHERE j.job_id = e.job_id
        RETURNING j.job_id
    )
    INSERT INTO silver.job_events (job_id, event_type, reason, created_at)
    SELECT job_id, 'STATUS_EXPIRED', 'Auto expired: past deadline date', NOW()
    FROM update_jobs;

    GET DIAGNOSTICS v_expired_count = ROW_COUNT;

    RETURN v_expired_count;
END;
$$ LANGUAGE plpgsql;

COMMIT;

SELECT 'Stored Procedures created successfully.' AS status;
