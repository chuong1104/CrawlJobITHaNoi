-- =============================================================================
-- Silver Layer — Index Strategy
-- File: 02_create_indexes.sql
-- Description: Tạo các index tối ưu hóa cho truy vấn và Stored Procedures.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Index cho bảng jobs (Lookup & Filter)
-- ---------------------------------------------------------------------------

-- Index tối ưu cho upsert: tìm job theo source_id và source_job_id
-- (Đã có UNIQUE constraint tạo index tự động, nhưng tạo thêm nếu cần)
-- CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_source_job_id ON silver.jobs (source_id, source_job_id);

-- Index tìm kiếm theo URL chuẩn hóa
-- (Đã có UNIQUE constraint)
-- CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_canonical_url ON silver.jobs (canonical_url);

-- Index tìm kiếm theo identity hash (dedup)
CREATE INDEX IF NOT EXISTS idx_jobs_identity_hash
    ON silver.jobs (identity_hash);

-- Partial index siêu tốc độ để lọc ra các tin đang hoạt động
CREATE INDEX IF NOT EXISTS idx_jobs_active
    ON silver.jobs (job_status)
    WHERE is_active = TRUE;

-- Index lọc theo công ty
CREATE INDEX IF NOT EXISTS idx_jobs_company_id
    ON silver.jobs (company_id);

-- Index lọc theo trạng thái và active status
CREATE INDEX IF NOT EXISTS idx_jobs_status_active
    ON silver.jobs (job_status, is_active);

-- Index lọc theo latest content hash
CREATE INDEX IF NOT EXISTS idx_jobs_latest_content
    ON silver.jobs (latest_content_hash);

-- Index lọc theo duplicate group
CREATE INDEX IF NOT EXISTS idx_jobs_duplicate_group
    ON silver.jobs (duplicate_group_id);

-- ---------------------------------------------------------------------------
-- 2. Index cho bảng job_snapshots (SCD Type 2)
-- ---------------------------------------------------------------------------

-- Partial index siêu tốc độ để lấy snapshot hiện tại của một job
CREATE INDEX IF NOT EXISTS idx_job_snapshots_current
    ON silver.job_snapshots (job_id)
    WHERE is_current = TRUE;

-- Index để check CDC pseudo (content hash)
CREATE INDEX IF NOT EXISTS idx_job_snapshots_content_hash
    ON silver.job_snapshots (content_hash);

-- Index lọc theo valid_to (chỉ lấy các bản ghi đang hiệu lực)
CREATE INDEX IF NOT EXISTS idx_snapshots_valid_to
    ON silver.job_snapshots (valid_to)
    WHERE valid_to IS NULL;

-- Partial index siêu tốc độ lọc theo deadline của các active snapshots
-- Tối ưu hóa cho tiến trình sp_auto_expire_deadline() hàng ngày
CREATE INDEX IF NOT EXISTS idx_snapshots_current_deadline
    ON silver.job_snapshots (deadline_date)
    WHERE is_current = TRUE;

-- ---------------------------------------------------------------------------
-- 3. Index cho các bảng N:N (Bridge Tables)
-- ---------------------------------------------------------------------------

-- Index để tìm snapshot theo skill (cho chiều ngược)
CREATE INDEX IF NOT EXISTS idx_snapshot_skills_skill_id
    ON silver.job_snapshot_skills (skill_id);

-- Index để tìm snapshot theo location (cho chiều ngược)
CREATE INDEX IF NOT EXISTS idx_snapshot_locations_location_id
    ON silver.job_snapshot_locations (location_id);

-- ---------------------------------------------------------------------------
-- 4. Index cho Audit Log (job_events)
-- ---------------------------------------------------------------------------

-- Index để xem lịch sử sự kiện của một job (composite index tối ưu sắp xếp)
CREATE INDEX IF NOT EXISTS idx_job_events_job_id
    ON silver.job_events (job_id, created_at DESC);

-- Index để thống kê theo loại sự kiện và thời gian
CREATE INDEX IF NOT EXISTS idx_job_events_type_time
    ON silver.job_events (event_type, created_at);

-- ---------------------------------------------------------------------------
-- 5. Index cho Deduplication
-- ---------------------------------------------------------------------------

-- Index tìm member của duplicate group
CREATE INDEX IF NOT EXISTS idx_dup_members_group_id
    ON silver.job_duplicate_group_members (group_id);

-- Index tìm duplicate group theo job
CREATE INDEX IF NOT EXISTS idx_dup_members_job_id
    ON silver.job_duplicate_group_members (job_id);

COMMIT;

SELECT 'Indexes created successfully.' AS status;
