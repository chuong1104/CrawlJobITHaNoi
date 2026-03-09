# Company Career Page Job Analysis

## Mục tiêu

Phân tích việc làm trực tiếp từ trang tuyển dụng của các công ty (không qua portal trung gian).

---

## 1. Lý do & Giá trị
- Nhiều công ty đăng tuyển trên trang riêng, không xuất hiện trên các portal lớn.
- Dữ liệu "gốc" hơn, có thể có nhiều thông tin chi tiết (phúc lợi, văn hóa, quy trình).
- Giảm trùng lặp, tăng coverage ngành nghề.

---

## 2. Quy trình đề xuất

1. **Lập danh sách công ty**
    - Tạo file CSV/Excel: `company_name`, `domain`, `career_url`, `country`, `priority`
2. **Phân tích cấu trúc trang tuyển dụng**
    - Xác định selector, endpoint, pagination, anti-bot, format job detail
3. **Viết adapter/crawler riêng cho từng loại trang**
    - Ưu tiên các ATS phổ biến (Workable, Greenhouse, Jobvite, v.v.)
    - Nếu trang custom, phân tích HTML và API
4. **Chuẩn hóa output về schema chung**
    - Mapping các trường: title, location, salary, description, requirements, apply_url, ...
5. **Tích hợp vào pipeline ETL**
    - Đưa vào Extract layer, transform, load như các portal

---

## 3. Checklist phân tích từng trang

| Trường | Nội dung |
|---|---|
| Company | |
| Domain | |
| Career URL | |
| Endpoint list/detail | |
| Selector job card | |
| Selector job detail | |
| Pagination | |
| Anti-bot | |
| Format | HTML/API |
| Ghi chú kỹ thuật | |

---

## 4. Mẫu phân tích

### Example: VinGroup

| Trường | Nội dung |
|---|---|
| Company | VinGroup |
| Domain | vingroup.net |
| Career URL | https://hr.vingroup.net/jobs |
| Endpoint list/detail | List: /jobs; Detail: /jobs/<id> |
| Selector job card | div.job-listing |
| Selector job detail | div.job-detail |
| Pagination | ?page=<num> |
| Anti-bot | Thấp |
| Format | HTML |
| Ghi chú kỹ thuật | Có API nội bộ, có thể parse HTML hoặc call API |

---

## 5. Tổng hợp các ATS phổ biến
- Workable
- Greenhouse
- Jobvite
- BambooHR
- Lever
- SmartRecruiters

---

## 6. Ghi chú
- Ưu tiên crawl các công ty lớn, tech, startup, FDI.
- Có thể mở rộng sang các ngành khác nếu cần.
- Nếu cần, bổ sung thêm các trường đặc thù (phúc lợi, văn hóa, video, ...).

---

## 7. Lịch sử cập nhật
- [2026-03-09] Khởi tạo file, đề xuất quy trình, checklist.
