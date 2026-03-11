# Company Career Page Job Analysis

## Mục tiêu

- Thu thập toàn bộ danh sách công ty, địa chỉ, website chính thức từ jobsgo.vn.
- Truy cập vào từng website chính thức của công ty, đến mục tuyển dụng/career page, lấy toàn bộ thông tin tuyển dụng trực tiếp từ trang công ty (không qua portal trung gian).
- Chuẩn hóa dữ liệu về schema chung, phục vụ phân tích, tích hợp pipeline ETL.

---

## 1. Lý do & Giá trị
- Nhiều công ty đăng tuyển trên trang riêng, không xuất hiện trên các portal lớn.
- Dữ liệu "gốc" hơn, có thể có nhiều thông tin chi tiết (phúc lợi, văn hóa, quy trình).
- Giảm trùng lặp, tăng coverage ngành nghề.

---

## 2. Quy trình đề xuất

1. **Thu thập danh sách công ty từ jobsgo.vn**
    - Truy cập https://jobsgo.vn/cong-ty.html
    - Cào các link công ty từ selector: `<a class="grid-item" ... href="/tuyen-dung/...">`
    - Lấy các trường: `company_name` (title/h3), `company_url` (href), `num_jobs` (p.jobs > b), `business_sector` (p.business-sectors)
    - Xử lý phân trang:
        - Dựa vào selector `<ul class="pagination">`, lấy các link trang tiếp theo: `/cong-ty-trang-2.html`, ...
        - Lặp qua từng trang, cào toàn bộ link công ty
    - Lưu danh sách vào file CSV/Excel: `company_name`, `company_url`, `num_jobs`, `business_sector`, `priority`

2. **Cào chi tiết từng công ty từ jobsgo.vn**
    - Truy cập từng link chi tiết, ví dụ: https://jobsgo.vn/tuyen-dung/cong-ty-tnhh-aeon-viet-nam-62164662.html
    - Mapping các trường:
        - Tên công ty: `<div class="company-name">` > h1/h2 hoặc `<h1 class="mb-3 ...">`
        - Địa chỉ: `<li class="d-flex ..."><i class="pb-heroicons-map-pin ..."></i> <span>...</span></li>`, hoặc `<span style="white-space: normal;">...</span>`
        - Website: `<span><a target="_blank" rel="nofollow" href="..."></a></span>`, hoặc `<span class="text-truncate ...">...</span>`
        - Lĩnh vực: `<div class="company-category-list">` > a/span
        - Ghi chú: Xử lý các trường đặc thù, nhiều địa chỉ, nhiều website, format khác nhau
    - Lưu chi tiết vào file hoặc database, mapping về schema chung: `company_name`, `alias`, `address`, `website`, `business_sector`, `detail_url`, `note`

3. **Truy cập website chính thức của từng công ty**
    - Dùng trường `website` đã thu thập được để truy cập vào trang web chính thức của công ty.
    - Tìm mục tuyển dụng/career page (có thể là /career, /jobs, /tuyen-dung, ... hoặc link từ menu).
    - Cào toàn bộ thông tin tuyển dụng trực tiếp từ website công ty:
        - Vị trí, mô tả, yêu cầu, địa điểm, mức lương, phúc lợi, link ứng tuyển, ...
        - Mapping về schema chung: `job_title`, `location`, `salary`, `description`, `requirements`, `apply_url`, ...
    - Lưu dữ liệu vào file hoặc database, chuẩn hóa output.

4. **Quy trình crawl tổng thể**
    - Bước 1: Cào danh sách link công ty (phân trang jobsgo.vn)
    - Bước 2: Truy cập từng link, cào chi tiết, mapping các trường (lấy website chính thức)
    - Bước 3: Truy cập website chính thức, tìm mục tuyển dụng, cào toàn bộ thông tin việc làm
    - Bước 4: Chuẩn hóa output về schema chung
    - Bước 5: Lưu dữ liệu, tích hợp vào pipeline ETL

5. **Lưu ý kỹ thuật**
    - Xử lý phân trang tự động, kiểm tra nút next `<li class="next">`
    - Chống trùng lặp, kiểm tra link đã crawl
    - Xử lý đa dạng format địa chỉ, website, career page
    - Tìm kiếm mục tuyển dụng trên website chính thức (có thể phải crawl menu, sitemap, hoặc dùng từ khóa)
    - Ưu tiên crawl các công ty lớn, tech, startup, FDI
    - Có thể mở rộng sang các ngành khác nếu cần
    - Nếu cần, bổ sung thêm các trường đặc thù (phúc lợi, văn hóa, video, ...)

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
