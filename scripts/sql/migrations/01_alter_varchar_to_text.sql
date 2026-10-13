-- =============================================================================
-- Migration: 01_alter_varchar_to_text.sql
-- Description: Nâng cấp các trường chuỗi thô từ VARCHAR(255) lên TEXT
-- Fix: psycopg2.errors.StringDataRightTruncation: value too long for type character varying(255)
-- =============================================================================

BEGIN;

-- 1. Bảng đệm staging.stg_jobs (Commit riêng biệt để luôn thành công, không bị ảnh hưởng bởi View ở tầng Silver/Gold)
ALTER TABLE staging.stg_jobs 
    ALTER COLUMN canonical_url TYPE TEXT,
    ALTER COLUMN title_raw TYPE TEXT,
    ALTER COLUMN title_clean TYPE TEXT,
    ALTER COLUMN company_raw TYPE TEXT,
    ALTER COLUMN company_normalized TYPE TEXT,
    ALTER COLUMN location_raw TYPE TEXT,
    ALTER COLUMN salary_raw TYPE TEXT,
    ALTER COLUMN experience_raw TYPE TEXT,
    ALTER COLUMN deadline_raw TYPE TEXT,
    ALTER COLUMN description TYPE TEXT,
    ALTER COLUMN source_job_id TYPE TEXT;

COMMIT;

BEGIN;
-- 2. Tầng Silver: companies & company_aliases
ALTER TABLE silver.companies 
    ALTER COLUMN normalized_name TYPE TEXT,
    ALTER COLUMN display_name TYPE TEXT,
    ALTER COLUMN website TYPE TEXT;

ALTER TABLE silver.company_aliases 
    ALTER COLUMN alias_text TYPE TEXT;

COMMIT;

-- 3. Tầng Silver: jobs & job_snapshots (xử lý an toàn nếu đang được Materialized View tham chiếu)
DO $$
BEGIN
    BEGIN
        ALTER TABLE silver.jobs 
            ALTER COLUMN source_job_id TYPE TEXT,
            ALTER COLUMN canonical_url TYPE TEXT;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'Skipping silver.jobs alter (may already be TEXT or bound to view): %', SQLERRM;
    END;

    BEGIN
        ALTER TABLE silver.job_snapshots 
            ALTER COLUMN title_raw TYPE TEXT,
            ALTER COLUMN title_clean TYPE TEXT,
            ALTER COLUMN salary_raw TYPE TEXT,
            ALTER COLUMN experience_raw TYPE TEXT,
            ALTER COLUMN deadline_raw TYPE TEXT,
            ALTER COLUMN description TYPE TEXT,
            ALTER COLUMN requirements TYPE TEXT;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'Skipping silver.job_snapshots alter (may already be TEXT or bound to view): %', SQLERRM;
    END;
END $$;
