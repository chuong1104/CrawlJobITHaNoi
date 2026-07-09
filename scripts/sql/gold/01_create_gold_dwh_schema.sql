-- =============================================================================
-- Gold Layer — Data Warehouse & Data Mart API
-- File: 01_create_gold_dwh_schema.sql
-- Description: Tạo Star Schema (Fact & Dimensions) và Materialized View cho API
-- =============================================================================

BEGIN;

-- 1. Tạo Schemas
CREATE SCHEMA IF NOT EXISTS dwh;
CREATE SCHEMA IF NOT EXISTS mart_api;

-- =============================================================================
-- 2. DIMENSION TABLES (dwh)
-- =============================================================================

-- Dim Date: Sinh ngày từ 2020 đến 2030
CREATE TABLE IF NOT EXISTS dwh.dim_date (
    date_key INT PRIMARY KEY, -- Định dạng YYYYMMDD
    full_date DATE NOT NULL UNIQUE,
    year INT NOT NULL,
    quarter INT NOT NULL,
    month INT NOT NULL,
    day_of_month INT NOT NULL,
    day_of_week INT NOT NULL, -- 1 = Monday, 7 = Sunday
    is_weekend BOOLEAN NOT NULL,
    is_holiday BOOLEAN DEFAULT FALSE,
    holiday_name VARCHAR
);

-- Dim Company: SCD Type 2
CREATE TABLE IF NOT EXISTS dwh.dim_company (
    company_key SERIAL PRIMARY KEY,
    silver_company_id INT NOT NULL,
    company_name VARCHAR NOT NULL,
    industry VARCHAR,
    company_size_category VARCHAR, -- Startup, Small, Medium, Enterprise
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    is_current BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX idx_dim_company_silver_id ON dwh.dim_company(silver_company_id);

-- Dim Skill: SCD Type 1 (Overwrite)
CREATE TABLE IF NOT EXISTS dwh.dim_skill (
    skill_key SERIAL PRIMARY KEY,
    silver_skill_id INT NOT NULL UNIQUE,
    skill_name VARCHAR NOT NULL,
    skill_category VARCHAR, -- Language, Framework, Database, Tool, Cloud
    is_tech_skill BOOLEAN DEFAULT TRUE
);

-- Dim Location: SCD Type 1
CREATE TABLE IF NOT EXISTS dwh.dim_location (
    location_key SERIAL PRIMARY KEY,
    silver_location_id INT NOT NULL UNIQUE,
    location_name VARCHAR NOT NULL,
    region VARCHAR -- North, Central, South
);

-- Dim Source
CREATE TABLE IF NOT EXISTS dwh.dim_source (
    source_key SERIAL PRIMARY KEY,
    silver_source_id SMALLINT NOT NULL UNIQUE,
    source_name VARCHAR NOT NULL,
    base_url VARCHAR
);

-- Dim Job Type / Level / Work Mode
CREATE TABLE IF NOT EXISTS dwh.dim_job_attributes (
    attribute_key SERIAL PRIMARY KEY,
    job_level VARCHAR,
    job_type VARCHAR,
    work_mode VARCHAR,
    CONSTRAINT unq_dim_attributes UNIQUE (job_level, job_type, work_mode)
);


-- =============================================================================
-- 3. FACT TABLES (dwh)
-- =============================================================================

CREATE TABLE IF NOT EXISTS dwh.fct_job_posting (
    job_posting_fact_id BIGSERIAL PRIMARY KEY,
    
    -- Business Keys
    silver_job_id BIGINT NOT NULL,
    silver_snapshot_id BIGINT NOT NULL,
    
    -- Dimension Keys
    posted_date_key INT NOT NULL REFERENCES dwh.dim_date(date_key),
    company_key INT NOT NULL REFERENCES dwh.dim_company(company_key),
    source_key INT NOT NULL REFERENCES dwh.dim_source(source_key),
    attribute_key INT NOT NULL REFERENCES dwh.dim_job_attributes(attribute_key),
    
    -- Measures
    salary_min_vnd NUMERIC,
    salary_max_vnd NUMERIC,
    salary_midpoint_vnd NUMERIC,
    experience_min_years SMALLINT,
    experience_max_years SMALLINT,
    skill_count INT DEFAULT 0,
    
    -- Flags
    is_active BOOLEAN NOT NULL,
    is_intern BOOLEAN DEFAULT FALSE,
    is_fresher BOOLEAN DEFAULT FALSE,
    has_salary BOOLEAN DEFAULT FALSE,
    
    loaded_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unq_fct_job_snapshot UNIQUE (silver_snapshot_id)
);

CREATE INDEX idx_fct_job_posting_company ON dwh.fct_job_posting(company_key);
CREATE INDEX idx_fct_job_posting_date ON dwh.fct_job_posting(posted_date_key);

-- Bridge Table for M:N relationships
CREATE TABLE IF NOT EXISTS dwh.bridge_job_skill (
    bridge_id BIGSERIAL PRIMARY KEY,
    job_posting_fact_id BIGINT NOT NULL REFERENCES dwh.fct_job_posting(job_posting_fact_id) ON DELETE CASCADE,
    skill_key INT NOT NULL REFERENCES dwh.dim_skill(skill_key),
    CONSTRAINT unq_bridge_job_skill UNIQUE (job_posting_fact_id, skill_key)
);

CREATE TABLE IF NOT EXISTS dwh.bridge_job_location (
    bridge_id BIGSERIAL PRIMARY KEY,
    job_posting_fact_id BIGINT NOT NULL REFERENCES dwh.fct_job_posting(job_posting_fact_id) ON DELETE CASCADE,
    location_key INT NOT NULL REFERENCES dwh.dim_location(location_key),
    CONSTRAINT unq_bridge_job_location UNIQUE (job_posting_fact_id, location_key)
);


-- =============================================================================
-- 4. DATA MART API (mart_api)
-- =============================================================================

-- Tái tạo Materialized View cho Backend API (Flat Table)
-- Drop trước nếu cần tạo lại
DROP MATERIALIZED VIEW IF EXISTS mart_api.latest_jobs_flat;

CREATE MATERIALIZED VIEW mart_api.latest_jobs_flat AS
SELECT 
    f.silver_job_id AS id,
    j.title_clean AS job_title,
    c.company_name,
    c.industry,
    so.source_name,
    a.job_level,
    a.job_type,
    a.work_mode,
    j.salary_raw AS salary_display,
    f.salary_min_vnd,
    f.salary_max_vnd,
    f.experience_min_years,
    f.experience_max_years,
    j.deadline_date,
    j.canonical_url,
    j.is_current,
    
    -- Aggregate Skills thành Array (rất nhanh cho Postgres GIN index)
    ARRAY(
        SELECT s.skill_name 
        FROM dwh.bridge_job_skill bjs
        JOIN dwh.dim_skill s ON s.skill_key = bjs.skill_key
        WHERE bjs.job_posting_fact_id = f.job_posting_fact_id
    ) AS skills,
    
    -- Aggregate Locations
    ARRAY(
        SELECT l.location_name 
        FROM dwh.bridge_job_location bjl
        JOIN dwh.dim_location l ON l.location_key = bjl.location_key
        WHERE bjl.job_posting_fact_id = f.job_posting_fact_id
    ) AS locations

FROM dwh.fct_job_posting f
JOIN silver.job_snapshots j ON f.silver_snapshot_id = j.snapshot_id -- Lấy các text descriptions từ Silver cho tiết kiệm
JOIN dwh.dim_company c ON f.company_key = c.company_key
JOIN dwh.dim_source so ON f.source_key = so.source_key
JOIN dwh.dim_job_attributes a ON f.attribute_key = a.attribute_key
WHERE f.is_active = TRUE AND j.is_current = TRUE;

-- Indexes cho Mart API để Search tốc độ ánh sáng
CREATE UNIQUE INDEX idx_mart_api_jobs_id ON mart_api.latest_jobs_flat (id);
CREATE INDEX idx_mart_api_jobs_title ON mart_api.latest_jobs_flat USING gin (to_tsvector('simple', job_title));
CREATE INDEX idx_mart_api_jobs_skills ON mart_api.latest_jobs_flat USING gin (skills);

COMMIT;

SELECT 'Gold Schema Created Successfully' AS status;
