-- ============================================================
-- optimize_views.sql
-- Tạo Unique Index bắt buộc để dùng REFRESH CONCURRENTLY
-- trên tất cả Materialized Views trong Gold/DWH schema.
--
-- REFRESH MATERIALIZED VIEW CONCURRENTLY:
--   ✓ Không lock bảng khi refresh
--   ✓ API và PowerBI vẫn đọc được data cũ trong khi refresh
--   ✗ Yêu cầu ít nhất 1 Unique Index trên view
--
-- Chạy script này MỘT LẦN để tạo các unique index.
-- Sau đó, các SP refresh sẽ tự dùng CONCURRENTLY.
-- ============================================================


-- ─────────────────────────────────────────────────────────────
-- Giả sử các Materialized View sau tồn tại trong schema dwh/api:
-- (Thay tên view cho phù hợp với dự án của bạn)
-- ─────────────────────────────────────────────────────────────

-- mv_api_job_list: view phục vụ API lấy danh sách jobs
-- Unique key thường là job_id hoặc (source_id, source_job_id)
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mv_api_job_list_job_id
    ON dwh.mv_api_job_list (job_id);

-- mv_api_skill_stats: thống kê kỹ năng phục vụ dashboard
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mv_api_skill_stats
    ON dwh.mv_api_skill_stats (skill_name);

-- mv_api_company_stats: thống kê công ty
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mv_api_company_stats
    ON dwh.mv_api_company_stats (company_id);

-- mv_api_location_stats: thống kê địa điểm
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mv_api_location_stats
    ON dwh.mv_api_location_stats (location_name);

-- mv_kpi_daily: KPI hàng ngày
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mv_kpi_daily
    ON dwh.mv_kpi_daily (report_date);


-- ─────────────────────────────────────────────────────────────
-- Template SP thay thế: dùng CONCURRENTLY thay vì thông thường
-- Stored Procedure này là phiên bản tối ưu để thay thế
-- sp_refresh_all_materialized_views hiện tại (nếu bạn quản lý SP bằng SQL file)
-- ─────────────────────────────────────────────────────────────

CREATE OR REPLACE PROCEDURE dwh.sp_refresh_all_materialized_views()
LANGUAGE plpgsql AS $$
DECLARE
    v_start TIMESTAMPTZ := clock_timestamp();
    v_view_name TEXT;
    v_view_start TIMESTAMPTZ;
BEGIN
    -- Danh sách Materialized Views cần refresh (thêm/xóa tùy dự án)
    -- Dùng CONCURRENTLY để KHÔNG block đọc trong suốt quá trình refresh
    FOREACH v_view_name IN ARRAY ARRAY[
        'dwh.mv_api_job_list',
        'dwh.mv_api_skill_stats',
        'dwh.mv_api_company_stats',
        'dwh.mv_api_location_stats',
        'dwh.mv_kpi_daily'
    ] LOOP
        BEGIN
            v_view_start := clock_timestamp();
            -- CONCURRENTLY: view vẫn readable trong khi đang refresh
            EXECUTE format('REFRESH MATERIALIZED VIEW CONCURRENTLY %s', v_view_name);
            RAISE NOTICE 'Refreshed % in %ms',
                v_view_name,
                extract(epoch from (clock_timestamp() - v_view_start)) * 1000;
        EXCEPTION WHEN OTHERS THEN
            -- Log lỗi nhưng tiếp tục refresh view tiếp theo
            RAISE WARNING 'Không thể refresh view %: %', v_view_name, SQLERRM;
        END;
    END LOOP;

    RAISE NOTICE 'sp_refresh_all_materialized_views hoàn thành trong %s',
        clock_timestamp() - v_start;
END;
$$;

COMMENT ON PROCEDURE dwh.sp_refresh_all_materialized_views()
IS 'Refresh tất cả Materialized Views dùng CONCURRENTLY để không block đọc. Yêu cầu unique index trên mỗi view.';
