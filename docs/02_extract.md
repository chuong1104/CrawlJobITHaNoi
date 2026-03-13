# 02 — Extract Layer — Thu thập Dữ liệu

> **Cập nhật:** 2026-03-11 | Phiên bản: 2.0  
> Lớp Extract đã được mở rộng từ 11 portal scrapers ban đầu thành hệ thống thu thập hai tầng, bổ sung Company Career Page Crawlers phục vụ thu thập dữ liệu tuyển dụng trực tiếp từ website công ty.

---

## Tổng quan

Lớp Extract chịu trách nhiệm thu thập dữ liệu thô từ hai nguồn song song:

**Tier 1 — Portal Scrapers:** Thu thập tin tuyển dụng từ 11 portal tuyển dụng lớn tại Việt Nam. Đây là nguồn dữ liệu có volume cao nhất và cập nhật nhanh nhất.

**Tier 2 — Company Career Page Crawlers:** Thu thập danh sách công ty từ JobsGO, tìm career page chính thức của từng công ty, và cào tin tuyển dụng trực tiếp. Đây là nguồn dữ liệu "gốc" hơn — nhiều công ty không đăng trên portal trung gian, hoặc có thông tin chi tiết hơn trên trang riêng.

Cả hai nguồn đều đi qua cùng một luồng Transform → Load và đều được chuẩn hóa về `JobSchema` thống nhất.

---

## Cấu trúc Thư mục

```
src/extract/
├── job_online/                  # Tier 1: Portal Scrapers
│   ├── base_scraper.py
│   ├── topcv.py
│   ├── itviec.py
│   ├── vietnamworks.py
│   ├── jobsgo.py
│   ├── joboko.py
│   ├── job_123.py
│   ├── careerviet.py
│   ├── careerlink.py
│   ├── ybox.py
│   └── linkedin.py
│
├── company/                     # Tier 2: Company Crawlers
│   ├── jobsgo_company_crawler.py
│   └── ...
```

---

## Luồng Thu thập Ba Giai đoạn

Mọi scraper (cả Tier 1 lẫn Tier 2) đều tuân theo luồng ba giai đoạn sau:

```
Phase 1: collect_urls()
  └─ Duyệt N trang list / API → lấy toàn bộ job URLs của ngày

Phase 2: deduplicate_urls()
  └─ Loại URL trùng nội bộ (trong batch hiện tại)
  └─ Loại URL đã có trong PostgreSQL (query: SELECT job_url FROM jobs WHERE source = ?)
  └─ Chỉ giữ lại URLs thực sự mới → tiết kiệm bandwidth và tránh spam

Phase 3: fetch_details_batch()
  └─ Chia URLs thành batches (mặc định 10 URLs/batch)
  └─ ThreadPoolExecutor: fetch song song trong batch
  └─ Giữa các batch: random delay 1–3s (anti-detection)
  └─ Tắt tải: image, video, font, stylesheet (giảm 40–70% thời gian)
  └─ parse_job_detail() → dict raw
```

---

## BaseScraper (`base_scraper.py`)

### Vai trò

Lớp trừu tượng định nghĩa contract chung, xử lý các vấn đề kỹ thuật nền tảng (retry, delay, logging, lưu file) để các scraper cụ thể chỉ cần tập trung vào logic parse.

### Thuộc tính Cấu hình

| Thuộc tính | Mặc định | Mô tả |
|---|---|---|
| `source_name` | (bắt buộc) | Tên định danh nguồn dữ liệu |
| `batch_size` | 10 | Số URL fetch song song |
| `max_retries` | 3 | Số lần thử lại khi gặp lỗi |
| `delay_min` | 1.0 | Thời gian delay tối thiểu (giây) |
| `delay_max` | 3.0 | Thời gian delay tối đa (giây) |
| `output_dir` | `data/raw/` | Thư mục lưu JSON thô |
| `use_playwright` | False | Bật Playwright cho portal cần JS |
| `block_resources` | `[image, media, font, stylesheet]` | Tài nguyên bị chặn |

### Các Phương thức Trừu tượng (phải override)

`collect_urls(pages: int) -> list[str]` — Thu thập danh sách job URLs từ trang list.

`parse_job_detail(html: str, url: str) -> dict` — Parse HTML/JSON của trang chi tiết thành raw dict.

### Các Phương thức Kế thừa Sẵn

`fetch(url: str) -> str | None` — Fetch một URL với retry và exponential backoff. Tự động chọn Scrapling HTTP mode hoặc Playwright mode tùy cấu hình.

`fetch_details_batch(urls: list[str]) -> list[dict]` — Gọi `fetch()` song song cho danh sách URLs, gom kết quả, bỏ qua URL thất bại.

`deduplicate_urls(urls: list[str]) -> list[str]` — Truy vấn DB lấy các URL đã tồn tại, loại khỏi danh sách đầu vào.

`run(pages: int) -> list[dict]` — Gọi tuần tự Phase 1 → 2 → 3, trả về list raw dicts.

`save_raw(data: list[dict], date_str: str) -> Path` — Lưu kết quả vào `data/raw/{source_name}/{date_str}.json`.

### Cơ chế Retry

```
Request thất bại (timeout / 429 / 503)
  └─ Lần 1: wait 2^1 = 2s
  └─ Lần 2: wait 2^2 = 4s
  └─ Lần 3: wait 2^3 = 8s
  └─ Lần 4: raise ScrapingException → log + skip URL này
```

---

## Tier 1 — Portal Scrapers

### Bảng Tổng hợp 11 Portal

| Portal | Mode | Batch Size | Đặc điểm Kỹ thuật |
|---|---|---|---|
| TopCV | HTTP | 10 | HTML parsing, ít chống bot, data phong phú |
| ITViec | HTTP + JSON | 15 | Có internal API, tập trung IT |
| VietnamWorks | JSON API | N/A | Token auth, structured JSON, không cần Phase 1–3 |
| JobsGO | HTTP | 15 | Đồng thời là nguồn company list |
| Joboko | HTTP | 15 | Nhiều ngành nghề |
| 123Job | HTTP | 10 | Volume lớn |
| CareerViet | HTTP | 10 | Tập trung mid-senior |
| CareerLink | HTTP | 10 | Ngành FDI, logistics |
| Ybox | HTTP | 15 | Tập trung fresher, sinh viên |
| JobStreet | Playwright | 5 | JavaScript challenge, cần browser |
| LinkedIn | Playwright + session | 3 | Login required, rate limit nghiêm ngặt |

### Ví dụ: TopCVScraper

TopCVScraper kế thừa BaseScraper và override hai phương thức cốt lõi.

`collect_urls()` duyệt N trang list tại `topcv.vn/viec-lam?page={i}`, dùng Scrapling selector `a.job-item-title` để lấy href, trả về list URLs tuyệt đối.

`parse_job_detail()` extract các trường từ trang chi tiết: tiêu đề từ `h1.job-detail__info--title`, công ty từ `div.job-detail__company--name`, lương từ `div.job-detail__info--salary`, kỹ năng từ `span.tag__content`, và nội dung mô tả/yêu cầu/phúc lợi từ các div tương ứng.

Output là raw dict chứa HTML nguyên bản trong các trường `*_html`, chưa qua cleaning — việc làm sạch sẽ do lớp Transform đảm nhiệm.

### Ví dụ: VietnamWorksScraper

VietnamWorks cung cấp API nội bộ trả về JSON structured, cho phép bỏ qua Phase 1–3 thông thường. Scraper gọi thẳng endpoint tìm kiếm với pagination, mỗi response chứa danh sách jobs đầy đủ thông tin. Cần gửi kèm token xác thực trong header.

### Ví dụ: LinkedInScraper

LinkedIn yêu cầu xác thực và giám sát bot nghiêm ngặt nhất. Scraper sử dụng Playwright với stealth plugin để ẩn dấu hiệu automation, duy trì session cookies từ lần đăng nhập trước, và giới hạn batch size xuống 3 với delay dài hơn (3–8s). Scraper này được bật/tắt qua Airflow Variable `ENABLE_LINKEDIN`.

---

## Tier 2 — Company Career Page Crawlers

### Bước 1 — Thu thập Danh sách Công ty (`company_list_crawler.py`)

Crawl toàn bộ danh sách công ty từ `jobsgo.vn/cong-ty.html` qua phân trang.

**Dữ liệu thu thập:**
- `company_name`: từ `h3` hoặc attribute `title` trong thẻ `a.grid-item`
- `jobsgo_url`: href → `/tuyen-dung/{company-slug}.html`
- `num_jobs`: số tin tuyển dụng hiện tại
- `business_sector`: ngành nghề chính

**Xử lý phân trang:** Kiểm tra `li.next` trong `ul.pagination` để xác định còn trang tiếp theo. Lặp đến khi không còn nút next.

**Output:** Bảng `companies` trong PostgreSQL với các trường trên, dùng làm input cho Bước 2.

### Bước 2 — Cào Chi tiết Công ty (`company_detail_crawler.py`)

Với mỗi URL từ Bước 1, cào trang chi tiết công ty để lấy website chính thức.

**Mapping selector (JobsGO):**
- Tên: `h1.mb-3` hoặc `div.company-name h1`
- Địa chỉ: `li > i.pb-heroicons-map-pin + span`
- Website: `a[target="_blank"][rel="nofollow"]` (lấy href)
- Lĩnh vực: `div.company-category-list a`

**Xử lý đặc thù:** Một công ty có thể có nhiều địa chỉ (multi-branch) hoặc nhiều website. Lưu tất cả, ưu tiên website đầu tiên cho Bước 3.

**Output:** Cập nhật bảng `companies` với trường `website` và `address`.

### Bước 3 — Tìm Career Page (`career_page_finder.py`)

Từ `website` chính thức, áp dụng chiến lược đa tầng để tìm trang tuyển dụng:

**Tầng 1 — Path Probing:** Thử lần lượt các đường dẫn phổ biến: `/careers`, `/jobs`, `/tuyen-dung`, `/work-with-us`, `/join-us`, `/about/careers`, `/en/careers`. Kiểm tra HTTP status 200 và nội dung có chứa từ khóa tuyển dụng.

**Tầng 2 — Navigation Parsing:** Fetch trang chủ, parse menu navigation (thẻ `nav`, `header`), tìm link có text chứa "career", "tuyển dụng", "việc làm", "join", "work with us".

**Tầng 3 — Sitemap Analysis:** Fetch `/sitemap.xml`, tìm URL chứa các từ khóa tuyển dụng trong danh sách URL.

**Tầng 4 — ATS Detection:** Nhận diện hệ thống ATS qua đặc điểm URL hoặc DOM: Workable (workable.com/jobs), Greenhouse (boards.greenhouse.io), Lever (jobs.lever.co), BambooHR (bamboohr.com/jobs), SmartRecruiters (jobs.smartrecruiters.com). Nếu phát hiện, chuyển sang adapter tương ứng.

**Output:** Trường `career_url` trong bảng `companies`. Nếu không tìm được, đánh dấu `career_url = NULL` và ghi log.

### Bước 4 — Cào Tin Tuyển dụng (`career_page_scraper.py`)

Từ `career_url`, cào danh sách tin tuyển dụng và chi tiết từng tin.

**Thách thức:** Mỗi công ty có cấu trúc HTML khác nhau hoàn toàn. Giải pháp áp dụng kỹ thuật phỏng đoán có cấu trúc:
- Tìm các thẻ lặp lại có chứa cả tên vị trí lẫn link chi tiết (likely job cards)
- Ưu tiên các CSS pattern phổ biến: `.job-item`, `.position`, `[data-job]`, `article`, `li` trong `ul.jobs`
- Nếu là ATS đã biết, dùng adapter chuyên biệt với selector cứng

**Output:** Raw dict với `source = "direct"` và `company_website = {domain}`, đưa vào cùng pipeline Transform → Load với Tier 1.

### ATS Adapters

Mỗi adapter chuyên biệt cho một hệ thống ATS:

| ATS | Đặc điểm nhận dạng | Endpoint list | Selector/Format |
|---|---|---|---|
| Workable | URL chứa `workable.com` | `/jobs` | JSON widget API |
| Greenhouse | URL chứa `boards.greenhouse.io` | `/jobs` | HTML có cấu trúc chuẩn |
| Lever | URL chứa `jobs.lever.co` | Root page | HTML + JSON-LD |
| BambooHR | URL chứa `bamboohr.com` | `/jobs` | JSON API công khai |
| SmartRecruiters | URL chứa `smartrecruiters.com` | `/jobs` | REST API |

---

## Chiến lược Chống Phát hiện Chi tiết

### Theo Mức độ Rủi ro

**Rủi ro thấp (TopCV, JobsGO, Ybox):** Chỉ cần Random User-Agent và delay ngẫu nhiên 1–2s là đủ.

**Rủi ro trung bình (ITViec, VietnamWorks, CareerViet):** Bổ sung proxy rotation sau mỗi 50–100 request, block tài nguyên không cần thiết.

**Rủi ro cao (JobStreet, LinkedIn):** Playwright Stealth Mode (ẩn `navigator.webdriver`, fake GPU/screen info), session persistence, delay dài hơn (3–8s), batch size nhỏ hơn (3–5), proxy xoay vòng thường xuyên hơn.

### Random User-Agent Pool

Duy trì pool 20+ User-Agent strings của các trình duyệt phổ biến (Chrome, Firefox, Safari, Edge), xoay vòng ngẫu nhiên mỗi request. Cập nhật pool định kỳ để phản ánh phiên bản trình duyệt mới nhất.

### Resource Blocking

Tắt tải các tài nguyên không cần thiết cho việc extract text:
- Image và video → tiết kiệm ~60% bandwidth
- CSS stylesheet → không ảnh hưởng đến HTML structure
- Web font → giảm thêm ~10% thời gian
- Analytics scripts → tránh bị track

Kết quả: thời gian fetch mỗi trang giảm 40–70%, giảm đáng kể "browser fingerprint" so với load đầy đủ.

---

## Xử lý Lỗi và Độ Bền Vững

### Phân loại Lỗi

| Loại Lỗi | Hành động | Ghi log |
|---|---|---|
| HTTP 429 (Rate limit) | Retry với backoff, tăng delay | WARNING |
| HTTP 503 (Server error) | Retry 3 lần, sau đó skip | WARNING |
| Timeout | Retry 2 lần, sau đó skip | WARNING |
| Parse error (selector không tìm thấy) | Skip job này, tiếp tục | ERROR |
| Playwright crash | Restart browser, retry | ERROR |
| Network offline | Raise ngay, báo lỗi DAG | CRITICAL |

### Partial Success

Nếu một portal thất bại hoàn toàn, pipeline vẫn tiếp tục với các portal còn lại. Airflow DAG dùng trigger rule `all_done` cho task transform, cho phép xử lý dữ liệu từ các portal thành công ngay cả khi một số portal gặp lỗi. Kết quả được ghi đầy đủ vào bảng `scrape_logs`.

---

## Output và Lưu trữ

### Format File Raw

```
data/raw/
├── topcv/
│   ├── 2026-03-10.json
│   └── 2026-03-11.json
├── itviec/
│   └── 2026-03-11.json
├── direct/                  ← Company career pages
│   └── 2026-03-11.json
└── ...
```

Mỗi file JSON là một mảng các raw dict. Cấu trúc raw dict thay đổi theo từng portal/scraper nhưng sau Transform sẽ đồng nhất về JobSchema.

### Retention Policy

File raw trong `data/raw/` giữ lại 30 ngày rồi xóa tự động để tiết kiệm disk. File processed trong `data/processed/` có thể xóa sau khi đã load vào PostgreSQL thành công.
