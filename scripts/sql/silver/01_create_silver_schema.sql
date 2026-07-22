-- =============================================================================
-- Silver Layer — 3NF Operational DB Schema
-- File: 01_create_silver_schema.sql
-- Description: Toàn bộ DDL cho schema silver.
--              Chạy một lần để khởi tạo cấu trúc database.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 0. Khởi tạo schema + extension
-- ---------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS staging;

-- pgcrypto để tính SHA-256 thuần SQL nếu cần
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- pg_trgm để tìm kiếm fuzzy text (dùng cho company alias lookup)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- unaccent để chuẩn hóa Unicode/dấu tiếng Việt trong tìm kiếm
CREATE EXTENSION IF NOT EXISTS unaccent;

-- ---------------------------------------------------------------------------
-- 1. Enum types
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'job_status_enum') THEN
        CREATE TYPE job_status_enum AS ENUM (
            'NEW',
            'ACTIVE',
            'UPDATED',
            'NOT_FOUND',
            'EXPIRED',
            'CLOSED',
            'REPOSTED',
            'REOPENED',
            'DUPLICATE',
            'INVALID'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'event_type_enum') THEN
        CREATE TYPE event_type_enum AS ENUM (
            'JOB_CREATED',
            'CONTENT_UPDATED',
            'TITLE_CHANGED',
            'SALARY_CHANGED',
            'EXPERIENCE_CHANGED',
            'LOCATION_CHANGED',
            'SKILLS_CHANGED',
            'DEADLINE_CHANGED',
            'STATUS_CLOSED',
            'STATUS_EXPIRED',
            'STATUS_REOPENED',
            'STATUS_REPOSTED',
            'DUPLICATE_DETECTED',
            'MARKED_INVALID',
            'URL_CHANGED',
            'ANOMALY_DETECTED',
            'NOT_FOUND_INCREMENT'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'work_mode_enum') THEN
        CREATE TYPE work_mode_enum AS ENUM (
            'ONSITE',
            'REMOTE',
            'HYBRID',
            'UNKNOWN'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'job_level_enum') THEN
        CREATE TYPE job_level_enum AS ENUM (
            'INTERN',
            'FRESHER',
            'JUNIOR',
            'MIDDLE',
            'SENIOR',
            'LEAD',
            'MANAGER',
            'C_LEVEL',
            'UNKNOWN'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'job_type_enum') THEN
        CREATE TYPE job_type_enum AS ENUM (
            'FULL_TIME',
            'PART_TIME',
            'CONTRACT',
            'FREELANCE',
            'INTERNSHIP',
            'UNKNOWN'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'crawl_status_enum') THEN
        CREATE TYPE crawl_status_enum AS ENUM (
            'RUNNING',
            'SUCCESS',
            'PARTIAL',
            'FAILED'
        );
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- 2. silver.sources — Danh mục nguồn tuyển dụng
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.sources (
    source_id       SMALLSERIAL PRIMARY KEY,
    source_code     VARCHAR(50)  NOT NULL UNIQUE,  -- 'topcv', 'itviec', ...
    display_name    VARCHAR(100) NOT NULL,
    base_url        TEXT         NOT NULL,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE silver.sources IS 'Danh mục các nguồn/portal tuyển dụng được theo dõi';
COMMENT ON COLUMN silver.sources.source_code IS 'Mã ngắn dùng trong code, e.g. topcv, itviec';

-- Seed dữ liệu nguồn ban đầu
INSERT INTO silver.sources (source_code, display_name, base_url) VALUES
    ('topcv',         'TopCV',         'https://topcv.vn'),
    ('itviec',        'ITviec',         'https://itviec.com'),
    ('linkedin',      'LinkedIn',       'https://linkedin.com'),
    ('vietnamworks',  'VietnamWorks',   'https://vietnamworks.com'),
    ('jobsgo',        'JobsGo',         'https://jobsgo.vn'),
    ('123job',        '123Job',         'https://123job.vn'),
    ('careerviet',    'CareerViet',     'https://careerviet.vn'),
    ('careerlink',    'CareerLink',     'https://careerlink.vn'),
    ('ybox',          'Ybox',           'https://ybox.vn'),
    ('jobstreet',     'JobStreet',      'https://jobstreet.com.vn'),
    ('joboko',        'JobOko',         'https://joboko.com')
ON CONFLICT (source_code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 3. silver.locations — Danh mục địa điểm chuẩn
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.locations (
    location_id     SMALLSERIAL  PRIMARY KEY,
    location_code   VARCHAR(50)  NOT NULL UNIQUE,  -- 'ha_noi', 'ho_chi_minh'
    display_name    VARCHAR(100) NOT NULL,
    region          VARCHAR(50),                    -- 'north', 'south', 'central'
    is_remote       BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE silver.locations IS 'Danh mục địa điểm làm việc đã được chuẩn hóa';

INSERT INTO silver.locations (location_code, display_name, region) VALUES
    ('ha_noi',       'Hà Nội',         'north'),
    ('ho_chi_minh',  'Hồ Chí Minh',    'south'),
    ('da_nang',      'Đà Nẵng',        'central'),
    ('hai_phong',    'Hải Phòng',      'north'),
    ('can_tho',      'Cần Thơ',        'south'),
    ('binh_duong',   'Bình Dương',     'south'),
    ('dong_nai',     'Đồng Nai',       'south'),
    ('remote',       'Remote',         NULL),
    ('other',        'Khác',           NULL)
ON CONFLICT (location_code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 4. silver.skills — Danh mục kỹ năng kỹ thuật
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.skills (
    skill_id        SMALLSERIAL  PRIMARY KEY,
    skill_code      VARCHAR(100) NOT NULL UNIQUE,  -- 'python', 'apache_spark'
    display_name    VARCHAR(150) NOT NULL,
    skill_category  VARCHAR(50),   -- 'language', 'framework', 'cloud', 'database', 'tool'
    skill_subcategory VARCHAR(50),
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE silver.skills IS 'Danh mục kỹ năng kỹ thuật chuẩn hóa, liên kết với dim_skill ở Gold';

-- ---------------------------------------------------------------------------
-- 5. silver.companies — Thực thể công ty
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.companies (
    company_id      SERIAL       PRIMARY KEY,
    normalized_name VARCHAR(255) NOT NULL UNIQUE,  -- Tên đã loại bỏ suffix pháp lý
    display_name    VARCHAR(255),            -- Tên hiển thị đẹp nhất tìm được
    website         TEXT,
    industry        VARCHAR(100),
    company_size    VARCHAR(50),            -- '1-10', '11-50', '51-200', ...
    is_anonymous    BOOLEAN      NOT NULL DEFAULT FALSE,  -- Ẩn tên công ty
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE silver.companies IS 'Thực thể công ty tuyển dụng, đã chuẩn hóa tên';
COMMENT ON COLUMN silver.companies.normalized_name IS 'Tên sau khi loại bỏ TNHH, Co Ltd, Cổ phần...';

-- Record đặc biệt cho công ty ẩn danh
INSERT INTO silver.companies (company_id, normalized_name, display_name, is_anonymous)
VALUES (1, '__ANONYMOUS__', 'Công ty ẩn danh', TRUE)
ON CONFLICT DO NOTHING;

-- Đảm bảo sequence được đồng bộ sau khi manual insert ID=1
SELECT setval('silver.companies_company_id_seq', COALESCE((SELECT MAX(company_id) FROM silver.companies), 1));


-- ---------------------------------------------------------------------------
-- 6. silver.company_aliases — Bí danh công ty
--    Giải quyết N cách viết tên → 1 company_id duy nhất
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.company_aliases (
    alias_id        SERIAL       PRIMARY KEY,
    company_id      INT          NOT NULL REFERENCES silver.companies(company_id) ON DELETE CASCADE,
    alias_text      VARCHAR(255) NOT NULL,  -- Tên gốc từ website nguồn
    source_id       SMALLINT     REFERENCES silver.sources(source_id),  -- Nguồn phát sinh alias
    confidence      SMALLINT     NOT NULL DEFAULT 100 CHECK (confidence BETWEEN 0 AND 100),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (alias_text)  -- Mỗi alias chỉ map về 1 company
);

COMMENT ON TABLE silver.company_aliases IS 'Map N cách viết tên công ty về 1 company_id';
COMMENT ON COLUMN silver.company_aliases.confidence IS '0-100: độ tin cậy mapping, 100=exact match';

-- ---------------------------------------------------------------------------
-- 7. silver.crawl_sessions — Metadata mỗi phiên crawl
--    Dùng làm guard để bảo vệ logic auto-close/not_found_count
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.crawl_sessions (
    session_id      BIGSERIAL    PRIMARY KEY,
    run_date        DATE         NOT NULL,
    source_id       SMALLINT     REFERENCES silver.sources(source_id),
    crawl_status    crawl_status_enum NOT NULL DEFAULT 'RUNNING',
    total_scraped   INT          NOT NULL DEFAULT 0,
    total_validated INT          NOT NULL DEFAULT 0,
    total_rejected  INT          NOT NULL DEFAULT 0,
    rejection_rate  NUMERIC(5,2) GENERATED ALWAYS AS (
        CASE WHEN total_scraped > 0
             THEN ROUND((total_rejected::NUMERIC / total_scraped) * 100, 2)
             ELSE 0
        END
    ) STORED,
    pages_scraped   INT          NOT NULL DEFAULT 0,
    started_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    duration_seconds INT GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (completed_at - started_at))::INT
    ) STORED
);

COMMENT ON TABLE silver.crawl_sessions IS 'Mỗi phiên crawl 1 source trong 1 ngày. Guard cho logic auto-close.';
COMMENT ON COLUMN silver.crawl_sessions.rejection_rate IS 'Tỷ lệ reject tự động tính. > 15% = cảnh báo';

-- ---------------------------------------------------------------------------
-- 8. silver.jobs — Thực thể tin tuyển dụng (Identity — STATIC)
--    Chỉ lưu thông tin định danh ổn định, KHÔNG lưu nội dung biến động
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.jobs (
    job_id              BIGSERIAL       PRIMARY KEY,
    source_id           SMALLINT        NOT NULL REFERENCES silver.sources(source_id),
    company_id          INT             NOT NULL REFERENCES silver.companies(company_id),

    -- Định danh từ nguồn
    source_job_id       VARCHAR(255),   -- ID nội bộ của website nguồn
    canonical_url       TEXT,           -- URL sau khi loại bỏ UTM params
    identity_hash       CHAR(16)        NOT NULL,  -- SHA-256[:16] trên các trường bất biến
    latest_content_hash CHAR(16),       -- Hash nội dung phiên bản mới nhất

    -- Trạng thái vòng đời
    job_status          job_status_enum NOT NULL DEFAULT 'NEW',
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    not_found_count     SMALLINT        NOT NULL DEFAULT 0 CHECK (not_found_count >= 0),
    inactive_reason     TEXT,           -- Lý do đóng/hết hạn

    -- Nhóm trùng lặp cross-source
    duplicate_group_id  INT,            -- FK sẽ thêm sau (circular ref)

    -- Timestamps lifecycle
    first_seen_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    last_seen_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    closed_at           TIMESTAMPTZ,
    expired_at          TIMESTAMPTZ,
    reopened_at         TIMESTAMPTZ,

    -- Audit
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT uq_jobs_source_job_id UNIQUE (source_id, source_job_id),
    CONSTRAINT uq_jobs_canonical_url UNIQUE (canonical_url),
    CONSTRAINT chk_closed_at CHECK (closed_at IS NULL OR closed_at >= first_seen_at),
    CONSTRAINT chk_expired_at CHECK (expired_at IS NULL OR expired_at >= first_seen_at)
);

COMMENT ON TABLE silver.jobs IS 'Thực thể tin tuyển dụng. Chỉ lưu định danh tĩnh + trạng thái. Nội dung ở job_snapshots.';
COMMENT ON COLUMN silver.jobs.identity_hash IS 'SHA-256[:16] tính từ: source+company+location+job_family+salary_bucket+skills_sorted';
COMMENT ON COLUMN silver.jobs.latest_content_hash IS 'Hash nội dung phiên bản hiện tại. Thay đổi → tạo snapshot mới (SCD Type 2)';
COMMENT ON COLUMN silver.jobs.not_found_count IS 'Số lần quét liên tiếp không thấy tin. >= 3 → CLOSED';

-- ---------------------------------------------------------------------------
-- 9. silver.job_snapshots — Nội dung tin theo phiên bản (SCD Type 2)
--    Mỗi lần nội dung thay đổi: đóng bản ghi cũ, tạo bản ghi mới
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.job_snapshots (
    snapshot_id         BIGSERIAL    PRIMARY KEY,
    job_id              BIGINT       NOT NULL REFERENCES silver.jobs(job_id) ON DELETE CASCADE,

    -- SCD Type 2 metadata
    is_current          BOOLEAN      NOT NULL DEFAULT TRUE,
    valid_from          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    valid_to            TIMESTAMPTZ,   -- NULL = bản ghi đang hiệu lực
    version_number      SMALLINT     NOT NULL DEFAULT 1,

    -- Nội dung tin (ĐỘNG — có thể thay đổi)
    title_raw           TEXT         NOT NULL,
    title_clean         TEXT,          -- Sau khi loại bỏ từ marketing
    description         TEXT,
    requirements        TEXT,

    -- Lương
    salary_raw          VARCHAR(255),
    salary_min          NUMERIC(15,0), -- VND
    salary_max          NUMERIC(15,0), -- VND
    salary_avg          NUMERIC(15,0) GENERATED ALWAYS AS (
        CASE WHEN salary_min IS NOT NULL AND salary_max IS NOT NULL
             THEN (salary_min + salary_max) / 2
             ELSE COALESCE(salary_min, salary_max)
        END
    ) STORED,
    salary_currency     VARCHAR(10)  DEFAULT 'VND',
    salary_is_negotiable BOOLEAN     NOT NULL DEFAULT FALSE,

    -- Kinh nghiệm
    experience_raw      TEXT,
    experience_min_years SMALLINT,
    experience_max_years SMALLINT,

    -- Phân loại
    job_level           job_level_enum DEFAULT 'UNKNOWN',
    job_type            job_type_enum  DEFAULT 'UNKNOWN',
    work_mode           work_mode_enum DEFAULT 'UNKNOWN',
    job_family          VARCHAR(100),   -- 'DATA_ENGINEER', 'DATA_ANALYST', ...

    -- Deadline
    deadline_raw        TEXT,
    deadline_date       DATE,

    -- Flags phân tích nhanh
    is_intern           BOOLEAN      NOT NULL DEFAULT FALSE,
    is_fresher          BOOLEAN      NOT NULL DEFAULT FALSE,
    is_no_experience    BOOLEAN      NOT NULL DEFAULT FALSE,
    is_student_friendly BOOLEAN      NOT NULL DEFAULT FALSE,
    has_conflict_flag   BOOLEAN      NOT NULL DEFAULT FALSE,  -- Title vs experience mâu thuẫn

    -- Fingerprint
    content_hash        CHAR(16)     NOT NULL,

    -- Audit
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT chk_snapshot_salary  CHECK (salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max),
    CONSTRAINT chk_snapshot_exp     CHECK (experience_min_years IS NULL OR experience_max_years IS NULL OR experience_min_years <= experience_max_years),
    CONSTRAINT chk_snapshot_valid   CHECK (valid_to IS NULL OR valid_to > valid_from),
    -- Chỉ có 1 bản ghi is_current=TRUE cho mỗi job_id
    CONSTRAINT uq_snapshot_current  UNIQUE NULLS NOT DISTINCT (job_id, is_current)
        DEFERRABLE INITIALLY DEFERRED
);

COMMENT ON TABLE silver.job_snapshots IS 'SCD Type 2: lịch sử nội dung tin tuyển dụng. Tạo bản ghi mới khi content_hash thay đổi.';
COMMENT ON COLUMN silver.job_snapshots.is_current IS 'TRUE = phiên bản đang có hiệu lực. Luôn chỉ có 1 bản TRUE / job_id';
COMMENT ON COLUMN silver.job_snapshots.valid_to IS 'NULL = đang hiệu lực. Timestamp khi bị đóng bởi bản ghi mới hơn.';

-- ---------------------------------------------------------------------------
-- 10. silver.job_snapshot_skills — N:N bridge: snapshot  skill
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.job_snapshot_skills (
    id              BIGSERIAL    PRIMARY KEY,
    snapshot_id     BIGINT       NOT NULL REFERENCES silver.job_snapshots(snapshot_id) ON DELETE CASCADE,
    skill_id        SMALLINT     NOT NULL REFERENCES silver.skills(skill_id),
    skill_position  SMALLINT     NOT NULL DEFAULT 0,  -- Vị trí trong danh sách skills
    is_primary      BOOLEAN      NOT NULL DEFAULT FALSE,  -- Top-3 skills
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (snapshot_id, skill_id)
);

COMMENT ON TABLE silver.job_snapshot_skills IS 'Liên kết N:N giữa snapshot và danh mục kỹ năng';

-- ---------------------------------------------------------------------------
-- 11. silver.job_snapshot_locations — N:N bridge: snapshot  location
--     Xử lý tình huống 5: tin có nhiều địa điểm làm việc
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.job_snapshot_locations (
    id              BIGSERIAL    PRIMARY KEY,
    snapshot_id     BIGINT       NOT NULL REFERENCES silver.job_snapshots(snapshot_id) ON DELETE CASCADE,
    location_id     SMALLINT     NOT NULL REFERENCES silver.locations(location_id),
    is_primary      BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (snapshot_id, location_id)
);

COMMENT ON TABLE silver.job_snapshot_locations IS 'Liên kết N:N: snapshot  địa điểm. 1 tin có thể có nhiều địa điểm.';

-- ---------------------------------------------------------------------------
-- 12. silver.job_events — Event Log (Audit Trail)
--     Mọi thay đổi trạng thái/nội dung đều được ghi lại
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.job_events (
    event_id        BIGSERIAL,
    job_id          BIGINT          NOT NULL REFERENCES silver.jobs(job_id) ON DELETE CASCADE,
    event_type      event_type_enum NOT NULL,
    source_id       SMALLINT        REFERENCES silver.sources(source_id),
    crawl_session_id BIGINT         REFERENCES silver.crawl_sessions(session_id),
    old_values      JSONB,           -- Giá trị trước khi thay đổi
    new_values      JSONB,           -- Giá trị sau khi thay đổi
    reason          TEXT,            -- Lý do hệ thống đưa ra quyết định
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (event_id, created_at)
)
-- Partition theo tháng để tránh bảng phình to
PARTITION BY RANGE (created_at);


-- Tạo partitions ban đầu (6 tháng)
CREATE TABLE IF NOT EXISTS silver.job_events_2026_06
    PARTITION OF silver.job_events FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
CREATE TABLE IF NOT EXISTS silver.job_events_2026_07
    PARTITION OF silver.job_events FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
CREATE TABLE IF NOT EXISTS silver.job_events_2026_08
    PARTITION OF silver.job_events FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
CREATE TABLE IF NOT EXISTS silver.job_events_2026_09
    PARTITION OF silver.job_events FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
CREATE TABLE IF NOT EXISTS silver.job_events_2026_10
    PARTITION OF silver.job_events FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');
CREATE TABLE IF NOT EXISTS silver.job_events_2026_11
    PARTITION OF silver.job_events FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
CREATE TABLE IF NOT EXISTS silver.job_events_2026_12
    PARTITION OF silver.job_events FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');

COMMENT ON TABLE silver.job_events IS 'Event sourcing log: mọi biến động trạng thái/nội dung. Partitioned theo tháng.';

-- ---------------------------------------------------------------------------
-- 13. silver.job_duplicate_groups — Nhóm tin trùng lặp cross-source
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.job_duplicate_groups (
    group_id            SERIAL       PRIMARY KEY,
    canonical_job_id    BIGINT       NOT NULL REFERENCES silver.jobs(job_id),  -- Tin đại diện
    group_name          TEXT,         -- Mô tả nhóm (optional, debug)
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE silver.job_duplicate_groups IS 'Nhóm các tin tuyển dụng giống nhau từ nhiều nguồn khác nhau';
COMMENT ON COLUMN silver.job_duplicate_groups.canonical_job_id IS 'Tin đại diện (canonical) của nhóm - thường là tin từ nguồn uy tín nhất';

-- ---------------------------------------------------------------------------
-- 14. silver.job_duplicate_group_members — Thành viên nhóm trùng lặp
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.job_duplicate_group_members (
    id              SERIAL       PRIMARY KEY,
    group_id        INT          NOT NULL REFERENCES silver.job_duplicate_groups(group_id) ON DELETE CASCADE,
    job_id          BIGINT       NOT NULL REFERENCES silver.jobs(job_id) ON DELETE CASCADE,
    similarity_score NUMERIC(5,4) CHECK (similarity_score BETWEEN 0 AND 1),  -- 0.0 - 1.0
    match_method    VARCHAR(50),  -- 'identity_hash', 'tfidf_cosine', 'rule_based'
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (group_id, job_id)
);

COMMENT ON TABLE silver.job_duplicate_group_members IS 'Thành viên của nhóm trùng lặp. similarity_score = điểm tương đồng.';

-- ---------------------------------------------------------------------------
-- FK đệ quy: jobs.duplicate_group_id → job_duplicate_groups.group_id
-- ---------------------------------------------------------------------------
ALTER TABLE silver.jobs
    ADD CONSTRAINT fk_jobs_duplicate_group
    FOREIGN KEY (duplicate_group_id)
    REFERENCES silver.job_duplicate_groups(group_id)
    DEFERRABLE INITIALLY DEFERRED;

-- ---------------------------------------------------------------------------
-- 15. staging schema — Bảng đệm để dbt ghi kết quả transform
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS staging.stg_jobs (
    -- Raw identity
    stg_id              BIGSERIAL    PRIMARY KEY,
    source_code         VARCHAR(50)  NOT NULL,
    source_job_id       VARCHAR(255),
    canonical_url       TEXT,

    -- Raw fields
    title_raw           TEXT         NOT NULL,
    company_raw         VARCHAR(255) NOT NULL,
    location_raw        TEXT,
    salary_raw          VARCHAR(255),
    experience_raw      TEXT,
    skills_raw          TEXT[],       -- Array của skills sau khi split
    job_type_raw        VARCHAR(100),
    description         TEXT,
    deadline_raw        TEXT,
    posted_date_raw     DATE,

    -- Parsed/normalized fields (dbt macros output)
    title_clean         TEXT,
    company_normalized  VARCHAR(255),
    salary_min          NUMERIC(15,0),
    salary_max          NUMERIC(15,0),
    salary_currency     VARCHAR(10),
    salary_is_negotiable BOOLEAN      DEFAULT FALSE,
    experience_min_years SMALLINT,
    experience_max_years SMALLINT,
    job_level           job_level_enum DEFAULT 'UNKNOWN',
    job_type            job_type_enum  DEFAULT 'UNKNOWN',
    work_mode           work_mode_enum DEFAULT 'UNKNOWN',
    location_normalized VARCHAR(50),   -- location_code
    job_family          VARCHAR(100),
    deadline_date       DATE,
    is_intern           BOOLEAN      DEFAULT FALSE,
    is_fresher          BOOLEAN      DEFAULT FALSE,

    -- Hashes
    identity_hash       CHAR(16)     NOT NULL,
    content_hash        CHAR(16)     NOT NULL,

    -- Classification
    change_type         VARCHAR(20),  -- 'NEW', 'UPDATED', 'UNCHANGED', 'REOPENED'

    -- System
    scraped_at          TIMESTAMPTZ  NOT NULL,
    processed_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    pipeline_version    VARCHAR(20)  NOT NULL DEFAULT '2.0',
    batch_date          DATE         NOT NULL DEFAULT CURRENT_DATE
);

CREATE INDEX IF NOT EXISTS idx_stg_jobs_source_job
    ON staging.stg_jobs (source_code, source_job_id);
CREATE INDEX IF NOT EXISTS idx_stg_jobs_identity_hash
    ON staging.stg_jobs (identity_hash);
CREATE INDEX IF NOT EXISTS idx_stg_jobs_batch_date
    ON staging.stg_jobs (batch_date);

COMMENT ON TABLE staging.stg_jobs IS 'Bảng đệm: kết quả từ dbt intermediate models. Input cho Python silver sync engine.';

-- ---------------------------------------------------------------------------
-- Trigger: auto-update updated_at
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION silver.fn_update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_jobs_updated_at
    BEFORE UPDATE ON silver.jobs
    FOR EACH ROW EXECUTE FUNCTION silver.fn_update_updated_at();

CREATE TRIGGER trg_companies_updated_at
    BEFORE UPDATE ON silver.companies
    FOR EACH ROW EXECUTE FUNCTION silver.fn_update_updated_at();

CREATE TRIGGER trg_sources_updated_at
    BEFORE UPDATE ON silver.sources
    FOR EACH ROW EXECUTE FUNCTION silver.fn_update_updated_at();

COMMIT;

-- Kiểm tra kết quả
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size
FROM pg_tables
WHERE schemaname IN ('silver', 'staging')
ORDER BY schemaname, tablename;
