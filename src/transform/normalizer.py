# Normalizer - Chuẩn hóa dữ liệu:
# - Mức lương: parse "10-15 triệu" -> {min: 10_000_000, max: 15_000_000, currency: "VND"}
#              quy đổi VND <-> USD theo tỷ giá cố định/realtime
# - Cấp bậc: map "Nhân viên", "Staff", "Junior" -> ENUM (INTERN/FRESHER/JUNIOR/MID/SENIOR/LEAD/MANAGER)
# - Hình thức làm việc: map "Toàn thời gian", "Full-time" -> ENUM (FULL_TIME/PART_TIME/CONTRACT/REMOTE)
# - Địa điểm: chuẩn hóa tên tỉnh/thành phố
