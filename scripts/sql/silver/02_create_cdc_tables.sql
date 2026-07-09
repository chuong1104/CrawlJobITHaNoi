-- =============================================================================
-- 02_create_cdc_tables.sql
-- CDC Watermark Tracking cho Delta-Load thông minh
-- 
-- Mục tiêu:
--   - Thay thế full-batch hàng ngày bằng delta load dựa trên watermark
--   - Giảm 80-90% dữ liệu phải xử lý mỗi lần chạy pipeline
--   - Phát hiện anomaly khi scraper bị block (ít records hơn kỳ vọng)
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. silver.cdc_watermarks — Lưu trữ watermark timestamp cho mỗi source
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.cdc_watermarks (
    source_code         VARCHAR(50)   PRIMARY KEY REFERENCES silver.sources(source_code),
    last_sync_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    last_batch_date     DATE,                         -- Ngày batch cuối đã sync thành công
    last_job_count      INT           NOT NULL DEFAULT 0,
    expected_min_count  INT           NOT NULL DEFAULT 50,  -- Ngưỡng tối thiểu mong đợi
    anomaly_flag        BOOLEAN       NOT NULL DEFAULT FALSE,
    anomaly_reason      TEXT,                         -- Mô tả lý do anomaly (nếu có)
    consecutive_low_runs SMALLINT     NOT NULL DEFAULT 0,  -- Số lần liên tiếp dưới ngưỡng
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE silver.cdc_watermarks IS 
    'Watermark tracking cho CDC delta-load. Giảm lượng dữ liệu phải xử lý 80-90% so với full-batch.';
COMMENT ON COLUMN silver.cdc_watermarks.last_sync_at IS 
    'Timestamp của batch đã được sync thành công gần nhất. Dùng làm filter cho lần chạy tiếp theo.';
COMMENT ON COLUMN silver.cdc_watermarks.anomaly_flag IS 
    'TRUE khi job_count < expected_min_count * 0.5. Cảnh báo scraper có thể bị block.';
COMMENT ON COLUMN silver.cdc_watermarks.consecutive_low_runs IS 
    'Số lần liên tiếp có ít records. >= 3 → cần kiểm tra scraper.';

-- Trigger: auto-update updated_at
DROP TRIGGER IF EXISTS trg_cdc_watermarks_updated_at ON silver.cdc_watermarks;
CREATE TRIGGER trg_cdc_watermarks_updated_at
    BEFORE UPDATE ON silver.cdc_watermarks
    FOR EACH ROW EXECUTE FUNCTION silver.fn_update_updated_at();

-- ---------------------------------------------------------------------------
-- 2. silver.pipeline_run_log — Log chi tiết mỗi lần chạy pipeline
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.pipeline_run_log (
    run_id              BIGSERIAL,
    pipeline_name       VARCHAR(100)  NOT NULL DEFAULT 'daily_job_pipeline',
    run_date            DATE          NOT NULL DEFAULT CURRENT_DATE,
    source_code         VARCHAR(50)   REFERENCES silver.sources(source_code),
    stage               VARCHAR(50)   NOT NULL,  -- 'bronze', 'silver', 'gold', 'dbt'
    
    -- Metrics
    records_extracted   INT           NOT NULL DEFAULT 0,
    records_new         INT           NOT NULL DEFAULT 0,
    records_updated     INT           NOT NULL DEFAULT 0,
    records_unchanged   INT           NOT NULL DEFAULT 0,
    records_rejected    INT           NOT NULL DEFAULT 0,
    
    -- Watermark
    watermark_from      TIMESTAMPTZ,             -- Watermark bắt đầu của run này
    watermark_to        TIMESTAMPTZ,             -- Watermark kết thúc (sẽ dùng cho run sau)
    
    -- Status
    status              VARCHAR(20)   NOT NULL DEFAULT 'RUNNING',  -- RUNNING/SUCCESS/FAILED
    error_message       TEXT,
    
    -- Timing
    started_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    duration_seconds    INT GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (completed_at - started_at))::INT
    ) STORED,

    CONSTRAINT chk_run_status CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED', 'SKIPPED')),
    PRIMARY KEY (run_id, run_date)
)
PARTITION BY RANGE (run_date);

-- Tạo partitions cho 6 tháng tới
CREATE TABLE IF NOT EXISTS silver.pipeline_run_log_2026_07
    PARTITION OF silver.pipeline_run_log FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
CREATE TABLE IF NOT EXISTS silver.pipeline_run_log_2026_08
    PARTITION OF silver.pipeline_run_log FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
CREATE TABLE IF NOT EXISTS silver.pipeline_run_log_2026_09
    PARTITION OF silver.pipeline_run_log FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
CREATE TABLE IF NOT EXISTS silver.pipeline_run_log_2026_10
    PARTITION OF silver.pipeline_run_log FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');
CREATE TABLE IF NOT EXISTS silver.pipeline_run_log_2026_11
    PARTITION OF silver.pipeline_run_log FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
CREATE TABLE IF NOT EXISTS silver.pipeline_run_log_2026_12
    PARTITION OF silver.pipeline_run_log FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');
CREATE TABLE IF NOT EXISTS silver.pipeline_run_log_2027_01
    PARTITION OF silver.pipeline_run_log FOR VALUES FROM ('2027-01-01') TO ('2027-02-01');

COMMENT ON TABLE silver.pipeline_run_log IS
    'Log chi tiết mỗi lần chạy pipeline, partitioned theo ngày. Dùng để debug và monitor performance.';

-- Seed watermarks ban đầu cho các sources đã có trong hệ thống
-- last_sync_at = epoch (1970) → lần đầu chạy sẽ load toàn bộ lịch sử
INSERT INTO silver.cdc_watermarks (source_code, last_sync_at, expected_min_count)
SELECT
    source_code,
    '1970-01-01 00:00:00+00'::TIMESTAMPTZ,
    CASE source_code
        WHEN 'topcv'        THEN 200  -- TopCV nhiều tin
        WHEN 'itviec'       THEN 100
        WHEN 'linkedin'     THEN 150
        WHEN 'vietnamworks' THEN 120
        WHEN 'jobsgo'       THEN 80
        ELSE 50
    END
FROM silver.sources
WHERE is_active = TRUE
ON CONFLICT (source_code) DO NOTHING;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_pipeline_run_log_date ON silver.pipeline_run_log (run_date);
CREATE INDEX IF NOT EXISTS idx_pipeline_run_log_source ON silver.pipeline_run_log (source_code);
CREATE INDEX IF NOT EXISTS idx_pipeline_run_log_status ON silver.pipeline_run_log (status);

COMMIT;

-- Verify
SELECT 
    source_code, 
    last_sync_at, 
    expected_min_count 
FROM silver.cdc_watermarks 
ORDER BY source_code;
