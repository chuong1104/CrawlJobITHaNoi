# Extract Layer - Scraping dữ liệu việc làm

## Tổng quan

Lớp Extract chịu trách nhiệm **cào dữ liệu thô** từ 11 trang tuyển dụng theo **luồng 3 giai đoạn**: thu thập URL → lọc trùng → batch cào chi tiết. Mọi scraper kế thừa từ `BaseScraper` và override các phương thức parse tương ứng.

---

## Luồng cào 3 giai đoạn

```
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 1: Collect URLs (nhẹ, nhanh)                                 │
│                                                                     │
│  Cào N trang list → extract href của từng job card                  │
│  Output: list[str] (raw URLs, có thể trùng)                         │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 2: Deduplicate URLs                                          │
│                                                                     │
│  1. Loại trùng trong batch hiện tại (set)                           │
│  2. Loại URL đã tồn tại trong DB (query bảng jobs theo job_url)     │
│  Output: list[str] (URLs mới, chưa có trong DB)                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 3: Batch fetch detail pages (song song, tối ưu tốc độ)      │
│                                                                     │
│  - Chia URLs thành batches (mặc định: 10 URLs/batch)                │
│  - Mỗi batch: fetch song song bằng asyncio / ThreadPoolExecutor     │
│  - Tắt load image, video, font, stylesheet                          │
│  - Parse HTML thuần → dict raw job                                  │
│  Output: list[dict] (raw job data, sẵn sàng cho Transform)          │
└─────────────────────────────────────────────────────────────────────┘
```

**Lợi ích của luồng này:**
- Phase 1 cực nhanh: chỉ đọc thẻ `<a>` trên trang list, không cần cào từng detail
- Phase 2 tránh cào lại job đã có → tiết kiệm request, giảm nguy cơ bị chặn
- Phase 3 song song: giảm tổng thời gian từ `N × t_request` xuống `ceil(N/batch) × t_request`
- Tắt media: giảm 30–70% thời gian load mỗi trang detail

---

## Cấu trúc thư mục

```
src/extract/
├── __init__.py
├── base_scraper.py     ← Class cha chứa logic chung
├── topcv.py
├── itviec.py
├── vietnamworks.py
├── jobsgo.py
├── joboko.py
├── job_123.py          ← (123job.vn - không đặt tên bắt đầu bằng số)
├── careerviet.py
├── careerlink.py
├── ybox.py
├── jobstreet.py        ← Playwright mode
└── linkedin.py         ← Playwright mode + proxy
```

---

## BaseScraper (`base_scraper.py`)

Class cha cung cấp toàn bộ cơ sở hạ tầng chung: fetch, dedup, batch, tắt media. Các scraper con chỉ cần implement 2 phương thức parse.

### Thuộc tính

| Thuộc tính | Kiểu | Mô tả |
|---|---|---|
| `source_name` | str | Tên portal (ví dụ: `"topcv"`) |
| `base_url` | str | URL gốc của portal |
| `max_retries` | int | Số lần retry tối đa (mặc định: 3) |
| `delay_range` | tuple | Khoảng delay ngẫu nhiên giây (mặc định: `(1, 3)`) |
| `proxy` | str \| None | Proxy URL nếu có |
| `output_dir` | Path | Thư mục lưu raw data (`data/raw/{source_name}/`) |
| `batch_size` | int | Số URL cào song song mỗi batch (mặc định: 10) |
| `block_resources` | list[str] | Loại tài nguyên bị chặn (mặc định: image, media, font, stylesheet) |

### Phương thức

```python
class BaseScraper:

    # ─── Bắt buộc override ────────────────────────────────────────────────

    def extract_job_urls(self, list_page_html: str) -> list[str]:
        """Phase 1: Parse trang list → trả về list URL của từng job card."""
        raise NotImplementedError

    def parse_job_detail(self, detail_html: str, url: str) -> dict:
        """Phase 3: Parse trang detail 1 job → dict raw đầy đủ fields."""
        raise NotImplementedError

    # ─── Phase 1: Collect URLs ────────────────────────────────────────────

    def collect_urls(self, pages: int) -> list[str]:
        """Cào N trang list, gộp tất cả job URLs lại thành 1 list."""

    # ─── Phase 2: Deduplicate ─────────────────────────────────────────────

    def deduplicate_urls(self, urls: list[str]) -> list[str]:
        """
        1. Loại trùng trong chính batch (dedup nội bộ bằng set).
        2. Query DB: loại các URL đã tồn tại trong bảng jobs.
        Trả về chỉ các URL mới cần cào.
        """

    # ─── Phase 3: Batch detail fetch ─────────────────────────────────────

    def fetch_details_batch(self, urls: list[str]) -> list[dict]:
        """
        Chia urls thành batches (batch_size), mỗi batch fetch song song
        bằng ThreadPoolExecutor. Tổng hợp kết quả thành list[dict].
        """

    def fetch_one(self, url: str) -> str:
        """
        Fetch HTML một trang detail.
        - HTTP mode : Scrapling HttpUrl (tắt image/media/font/css)
        - Playwright: PlaywrightFetcher (block_resources theo cấu hình)
        Có retry + exponential backoff.
        """

    # ─── Utility ──────────────────────────────────────────────────────────

    def save_raw(self, data: list[dict], date_str: str) -> Path:
        """Lưu list dict ra data/raw/{source}/{date}.json."""

    def run(self, pages: int = 5) -> list[dict]:
        """
        Điểm vào chính — chạy toàn bộ 3 giai đoạn:
          collect_urls → deduplicate_urls → fetch_details_batch → save_raw
        """
```

### Tắt tài nguyên không cần thiết (block_resources)

Khi fetch trang detail, BaseScraper chặn các loại tài nguyên không chứa dữ liệu text:

| Resource type | Lý do chặn |
|---|---|
| `image` | Không cần thiết, chiếm băng thông lớn nhất |
| `media` | Video/audio – không bao giờ cần |
| `font` | File `.woff2`, `.ttf` – không ảnh hưởng HTML text |
| `stylesheet` | File `.css` – không cần thiết cho parse dữ liệu |

**Với Scrapling HTTP mode** (các portal ít chặn): truyền header `Accept` tối giản, không request thêm sub-resources.

**Với Playwright mode** (JobStreet, LinkedIn): dùng `route.abort()` để hủy request trước khi gửi:

```
Browser phát hiện request tài nguyên
        │
        ├── type: "image"      → abort() → trang không load ảnh
        ├── type: "media"      → abort()
        ├── type: "font"       → abort()
        ├── type: "stylesheet" → abort()
        └── type: "document"   → fulfill() → cho phép load HTML
            type: "script"     → fulfill() (giữ lại để render JS nếu cần)
```

**Kết quả thực tế:** thời gian load trang detail giảm 40–70% tùy portal.

### Cơ chế Batch song song

```
urls = [url_1, url_2, ..., url_100]
batch_size = 10

Batch 1: [url_1..url_10]   → ThreadPoolExecutor(10 workers) → [html_1..html_10]
Batch 2: [url_11..url_20]  → ThreadPoolExecutor(10 workers) → [html_11..html_20]
...
Batch 10:[url_91..url_100] → ThreadPoolExecutor(10 workers) → [html_91..html_100]

Tổng thời gian: 10 × t_single_batch  (thay vì 100 × t_single_request)
```

- Giữa các batch: sleep random trong `delay_range` để tránh rate limit
- Nếu 1 request trong batch lỗi: log warning + skip, không block cả batch

### Cơ chế Deduplicate

```
Phase 1 output: [url_A, url_B, url_A, url_C, url_D]  (có trùng)
                       │
             Step 1: dedup nội bộ (set)
                       │
                       ▼
              [url_A, url_B, url_C, url_D]
                       │
             Step 2: query DB
             SELECT job_url FROM jobs
             WHERE job_url IN (url_A, url_B, url_C, url_D)
             → DB đã có: [url_A]
                       │
                       ▼
              [url_B, url_C, url_D]  ← chỉ cào 3 thay vì 5
```

### Cơ chế Retry

```
fetch_one(url)
    │ Lỗi (429 / 503 / timeout)
    ▼
Sleep 2^1 = 2s + jitter ngẫu nhiên
Retry lần 2
    │ Lỗi
    ▼
Sleep 2^2 = 4s + jitter
Retry lần 3 (max_retries=3)
    │ Lỗi
    ▼
Trả về None → batch bỏ qua URL này, ghi log warning
```

---

## Danh sách Scrapers

> Mỗi scraper chỉ cần implement **2 phương thức**:
> - `extract_job_urls(list_page_html)` → lấy URLs từ trang list
> - `parse_job_detail(detail_html, url)` → parse trang detail 1 job
>
> Toàn bộ logic collect → dedup → batch → retry do `BaseScraper` xử lý.

### 1. TopCV (`topcv.py`)

| Thuộc tính | Giá trị |
|---|---|
| URL list | `https://www.topcv.vn/viec-lam?page=N` |
| Anti-bot | Trung bình |
| Phương thức | Scrapling HTTP |
| URL selector | `a.job-item-title` hoặc `a[href*="/viec-lam/"]` |
| batch_size | 10 |

**Phase 1 - extract_job_urls:**
- Tìm tất cả thẻ `<a>` có `href` trỏ đến trang detail job
- Trả về absolute URL (prefix `https://www.topcv.vn` nếu là relative path)

**Phase 3 - parse_job_detail (fields lấy được):**
- `title`, `company`, `location`, `salary_text`, `deadline`
- `description`, `requirements`, `benefits` (các section riêng biệt)
- `skills` (tags trong sidebar)
- `level`, `job_type` (sidebar trang detail)

---

### 2. ITViec (`itviec.py`)

| Thuộc tính | Giá trị |
|---|---|
| URL list | `https://itviec.com/it-jobs?page=N` |
| Anti-bot | Thấp |
| Phương thức | Scrapling HTTP |
| URL selector | `a.job-title__text` hoặc `h3.imy-job-card__title a` |
| batch_size | 15 (anti-bot thấp → batch lớn hơn) |

**Phase 3 - parse_job_detail (fields lấy được):**
- `title`, `company`, `location`, `salary_text`, `skills` (trang list đã có nhưng lấy lại từ detail cho đầy đủ)
- `description`, `requirements`, `benefits`
- `posted_date` (dạng "2 days ago")

---

### 3. VietnamWorks (`vietnamworks.py`)

| Thuộc tính | Giá trị |
|---|---|
| URL | `https://www.vietnamworks.com/hrais/jobs/searches` |
| Anti-bot | Trung bình |
| Phương thức | **REST API** (ưu tiên hơn scraping HTML) |
| Phân trang | JSON body `{"from": 0, "size": 20}` |

> **Đặc biệt:** VietnamWorks có REST API trả về JSON đầy đủ, **không cần Phase 1-2-3**. Gọi API trực tiếp, mỗi response đã chứa đủ fields. Chỉ áp dụng dedup theo `job_url` trước khi load.

**API Request:**
```http
POST https://www.vietnamworks.com/hrais/jobs/searches
Content-Type: application/json

{
  "query": "",
  "location_ids": [],
  "industry_ids": [],
  "from": 0,
  "size": 20,
  "sort": "posted_date"
}
```

**Response:** `hits.hits[]._source` → object chứa đầy đủ thông tin job.

---

### 4. JobsGO (`jobsgo.py`)

| Thuộc tính | Giá trị |
|---|---|
| URL list | `https://jobsgo.vn/viec-lam.html?page=N` |
| Anti-bot | Thấp |
| Phương thức | Scrapling HTTP |
| URL selector | `.job-item a.title` hoặc `h3.job-title a` |
| batch_size | 15 |

---

### 5. Joboko (`joboko.py`)

| Thuộc tính | Giá trị |
|---|---|
| URL list | `https://joboko.com/tim-kiem-viec-lam?page=N` |
| Anti-bot | Thấp |
| Phương thức | Scrapling HTTP |
| URL selector | `.job-name a`, `h2.title a` |
| batch_size | 15 |

---

### 6. 123job (`job_123.py`)

| Thuộc tính | Giá trị |
|---|---|
| URL list | `https://123job.vn/tim-viec-lam?page=N` |
| Anti-bot | Trung bình |
| Phương thức | Scrapling HTTP |
| URL selector | `.job-title a`, `a.name-job` |
| batch_size | 10 |
| Ghi chú | File đặt tên `job_123.py` (Python không cho phép tên bắt đầu bằng số) |

---

### 7. CareerViet (`careerviet.py`)

| Thuộc tính | Giá trị |
|---|---|
| URL list | `https://careerviet.vn/viec-lam/tim-kiem.html?page=N` |
| Anti-bot | Trung bình |
| Phương thức | Scrapling HTTP |
| URL selector | `a.job-title`, `.job-item h3 a` |
| batch_size | 10 |

---

### 8. CareerLink (`careerlink.py`)

| Thuộc tính | Giá trị |
|---|---|
| URL list | `https://www.careerlink.vn/tim-viec-lam?page=N` |
| Anti-bot | Thấp - Trung bình |
| Phương thức | Scrapling HTTP |
| URL selector | `.job-title a`, `h2.title a` |
| batch_size | 10 |

---

### 9. Ybox (`ybox.py`)

| Thuộc tính | Giá trị |
|---|---|
| URL list | `https://ybox.vn/viec-lam?page=N` |
| Anti-bot | Thấp |
| Phương thức | Scrapling HTTP |
| URL selector | `.job-name a`, `.job_item h3 a` |
| batch_size | 15 |
| Đặc điểm | Nhắm đến đối tượng sinh viên / fresher |

---

### 10. JobStreet (`jobstreet.py`) ⚠️

| Thuộc tính | Giá trị |
|---|---|
| URL list | `https://www.jobstreet.vn/vi-vn/job-search/?page=N` |
| Anti-bot | **RẤT MẠNH** - Cloudflare, TLS fingerprinting |
| Phương thức | Scrapling **Playwright mode** |
| URL selector | `a[data-automation="jobTitle"]` |
| batch_size | 5 (Playwright chậm hơn, giảm batch để tránh timeout) |
| block_resources | image, media, font, stylesheet (áp dụng qua `route.abort()`) |

**Chiến lược Phase 1:**
- Dùng `PlaywrightFetcher` với stealth patches để vượt Cloudflare
- Sau khi có list URLs → switch sang fetch detail bằng HTTP nếu detail page không cần JS
- Nếu detail page cần JS: tiếp tục dùng Playwright với `block_resources`

---

### 11. LinkedIn (`linkedin.py`) ⚠️⚠️

| Thuộc tính | Giá trị |
|---|---|
| URL list | `https://www.linkedin.com/jobs/search/?location=Vietnam&start=N` |
| Anti-bot | **CỰC MẠNH** - login required, IP ban |
| Phương thức | Playwright + cookies + proxy |
| URL selector | `a.job-card-list__title` |
| batch_size | 3 (rate limit rất nghiêm ngặt) |
| block_resources | image, media, font, stylesheet |

**Chiến lược:**
1. Đăng nhập thủ công một lần, lưu cookies → `keys/linkedin_cookies.json`
2. Load cookies vào Playwright session
3. Phase 1 cào tối đa 2-3 trang list (rate limit: ~30–50 job URLs/phiên)
4. Dedup trước, chỉ fetch detail những job thực sự mới
5. Batch size = 3, delay 5-10s giữa các batch

> **Lưu ý:** Cân nhắc LinkedIn Jobs API nếu có thể xin access.

---

## Output format (Raw Data)

Mỗi scraper lưu dữ liệu thô ra `data/raw/{source}/{YYYY-MM-DD}.json` sau Phase 3:

```json
[
  {
    "source": "topcv",
    "title": "Senior Data Engineer",
    "company": "Công ty ABC",
    "location": "Hà Nội",
    "salary_text": "20 - 35 triệu",
    "job_type_text": "Toàn thời gian",
    "level_text": "Trưởng nhóm / Giám sát",
    "description_html": "<p>Mô tả công việc...</p>",
    "requirements_html": "<ul><li>3+ năm kinh nghiệm...</li></ul>",
    "benefits_html": "<p>Bảo hiểm đầy đủ...</p>",
    "skills_raw": ["Python", "Spark", "Airflow"],
    "posted_date_text": "03/03/2026",
    "deadline_text": "03/04/2026",
    "job_url": "https://www.topcv.vn/viec-lam/senior-data-engineer-abc/123456.html",
    "scraped_at": "2026-03-05T08:30:00Z"
  }
]
```

> **Lưu ý:** Chỉ chứa HTML thuần của các thẻ nội dung (`<p>`, `<ul>`, `<li>`, `<h3>`, `<strong>`, ...). Không có `<img>`, `<video>`, `<style>`, `<script>` trong output vì đã bị chặn từ lúc fetch.

---

## Tóm tắt cấu hình batch_size theo portal

| Portal | batch_size | Lý do |
|---|---|---|
| ITViec | 15 | Anti-bot thấp, cho phép batch lớn |
| JobsGO | 15 | Anti-bot thấp |
| Ybox | 15 | Anti-bot thấp |
| TopCV | 10 | Anti-bot trung bình |
| 123job | 10 | Anti-bot trung bình |
| CareerViet | 10 | Anti-bot trung bình |
| CareerLink | 10 | Anti-bot trung bình |
| Joboko | 15 | Anti-bot thấp |
| JobStreet | 5 | Playwright chậm hơn, anti-bot mạnh |
| LinkedIn | 3 | Rate limit cực nghiêm, Playwright |
| VietnamWorks | N/A | API — không cần batch detail |

---

## Xử lý lỗi

| Loại lỗi | HTTP Code | Xử lý |
|---|---|---|
| Rate limit | 429 | Retry với exponential backoff + tăng delay |
| Server error | 500, 503 | Retry 3 lần, sau đó skip + log warning |
| Blocked / CAPTCHA | 403 | Chuyển sang proxy khác, retry |
| Timeout | - | Retry với timeout cao hơn |
| Parse error | - | Log warning, skip job đó, tiếp tục batch |
| URL đã có trong DB | - | Bỏ qua trong Phase 2 (dedup), không fetch |
| Portal down | - | Fail task Airflow, gửi alert |

---

## Biến môi trường liên quan

```bash
PROXY_URL=http://proxy-provider.com:port
PROXY_USERNAME=your_username
PROXY_PASSWORD=your_password
```
