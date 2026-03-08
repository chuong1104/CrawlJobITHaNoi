# load_to_dw - Logic đẩy dữ liệu vào Data Warehouse:
# - Upsert (INSERT ... ON CONFLICT DO UPDATE) vào bảng jobs
# - Batch insert để tối ưu performance
# - Ghi log số bản ghi inserted / updated / skipped
# - Handle lỗi kết nối và retry
