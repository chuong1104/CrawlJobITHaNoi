# 03 — Transform Layer — Làm sạch và Chuẩn hóa Dữ liệu

> **Cập nhật:** 2026-03-11 | Phiên bản: 2.0  
> Lớp Transform giữ nguyên ba bước xử lý cốt lõi (Clean → Normalize → Validate), được bổ sung ghi chú về vị trí của lớp này trong pipeline tổng thể và mở rộng một số quy tắc chuẩn hóa phục vụ NLP downstream.

---

## Tổng quan

Lớp Transform nhận **raw data** (dict chưa chuẩn hóa) từ lớp Extract của cả hai nguồn (Portal Scrapers và Company Crawlers), xử lý qua ba bước tuần tự:

```
Raw dict (từ scraper / company crawler)
          │
          ▼
  1. Cleaner         → Làm sạch text, parse ngày tháng, xóa HTML tags
          │
          ▼
  2. Normalizer      → Chuẩn hóa lương, cấp bậc, loại công việc, địa điểm
          │
          ▼
  3. Schema Validate → Pydantic v2 validation + type coercion + tạo job_id
          │
          ▼
JobSchema object (validated, type-safe)
          │
          ▼ (sau khi Load vào PostgreSQL)
NLP Pipeline        → Skill Extraction + Text Embedding (xử lý async riêng)
```

**Lưu ý quan trọng về phân tách trách nhiệm:** Lớp Transform chỉ làm sạch và chuẩn hóa dữ liệu đã có trong raw dict — chuẩn hóa lương, cấp bậc, địa điểm, loại hình. Việc trích xuất kỹ năng từ văn bản mô tả (NLP Skill Extraction) và tạo embedding thuộc về lớp NLP Processing và chạy trong một DAG riêng sau khi dữ liệu đã được load vào database.

---

## Cấu trúc Thư mục

```
src/transform/
├── __init__.py
├── cleaner.py       ← Bước 1: Làm sạch text thô
├── normalizer.py    ← Bước 2: Chuẩn hóa về giá trị chuẩn
└── schemas.py       ← Bước 3: Pydantic schema + validation
```

---

## 1. Cleaner (`cleaner.py`)

### Nhiệm vụ

Chuyển đổi dữ liệu thô, "bẩn" từ HTML sang text thuần và chuẩn hóa format cơ bản. Bước này không thay đổi ý nghĩa dữ liệu, chỉ làm sạch hình thức.

### Hàm `strip_html(html_text: str) -> str`

Xóa toàn bộ HTML tags, giữ lại text thuần theo cách có ý nghĩa:

| Input | Output |
|---|---|
| `<p>Mô tả <strong>công việc</strong>:</p>` | `Mô tả công việc:` |
| `<ul><li>Task 1</li><li>Task 2</li></ul>` | `- Task 1\n- Task 2` |
| `<br>` hoặc `<br/>` | `\n` |
| `<script>...</script>` | `` (xóa hoàn toàn) |
| `&amp;` `&lt;` `&gt;` `&nbsp;` | `&` `<` `>` ` ` (decode HTML entities) |

Sử dụng `BeautifulSoup(html, "lxml")` để parse. Thẻ `<li>` được chuyển thành `"- item"` để giữ cấu trúc list khi xuất ra text — điều này quan trọng cho NLP downstream vì danh sách kỹ năng/yêu cầu thường ở dạng `<ul><li>`.

### Hàm `parse_date(date_text: str) -> date | None`

Parse đa dạng format ngày tháng về `datetime.date`. Thứ tự thử: regex ISO → regex DD/MM/YYYY → relative date → return None.

| Input | Output |
|---|---|
| `"2026-03-03"` | `date(2026, 3, 3)` |
| `"03/03/2026"` | `date(2026, 3, 3)` |
| `"3 tháng 3, 2026"` | `date(2026, 3, 3)` |
| `"2 ngày trước"` | `date.today() - timedelta(2)` |
| `"Hôm nay"` / `"Just now"` / `"Today"` | `date.today()` |
| `"1 tuần trước"` | `date.today() - timedelta(7)` |
| `None` / chuỗi không nhận ra | `None` |

### Hàm `normalize_whitespace(text: str) -> str`

- Thay thế `\t`, multiple spaces bằng single space
- Strip leading/trailing whitespace
- Loại bỏ zero-width characters: `\u200b` (zero-width space), `\u00a0` (non-breaking space), `\ufeff` (BOM)
- Chuẩn hóa các dấu nháy và dấu ngang về dạng ASCII tiêu chuẩn

### Hàm `clean_job(raw: dict) -> dict`

Hàm tổng hợp, nhận raw dict từ bất kỳ scraper nào và áp dụng tất cả cleaning. Trả về dict mới với các trường đã được làm sạch, giữ nguyên các trường không liên quan để không làm mất dữ liệu.

Quy tắc xử lý theo nguồn: nếu `source == "direct"` (company crawler), một số trường có thể ở format khác và cần được xử lý với regex linh hoạt hơn so với portal cố định.

---

## 2. Normalizer (`normalizer.py`)

### Nhiệm vụ

Chuẩn hóa các trường có nhiều biến thể khác nhau về giá trị chuẩn (Enum/số). Bước này biến dữ liệu từ "đọc được" thành "có thể so sánh và lọc được".

### Hàm `normalize_salary(salary_text: str) -> tuple[int|None, int|None, str]`

Parse chuỗi lương thô thành `(salary_min_vnd, salary_max_vnd, currency)`.

| Input | min | max | currency |
|---|---|---|---|
| `"10 - 15 triệu"` | 10_000_000 | 15_000_000 | VND |
| `"Lên đến 20 triệu"` | None | 20_000_000 | VND |
| `"Từ 15 triệu"` | 15_000_000 | None | VND |
| `"1,000 - 1,500 USD"` | 25_000_000 | 37_500_000 | USD |
| `"$800 - $1200"` | 20_000_000 | 30_000_000 | USD |
| `"Thỏa thuận"` / `"Competitive"` / `""` | None | None | VND |

**Logic xử lý:** Regex detect số + đơn vị (`triệu`, `tr`, `USD`, `$`, `VNĐ`). Quy đổi: 1 triệu = 1,000,000 VND. Nếu currency là USD: nhân với tỷ giá cố định trong config (mặc định 25,000 VND/USD, cập nhật định kỳ). Trả về `(None, None, "VND")` nếu không parse được thay vì raise exception.

**Ý nghĩa downstream:** salary_min và salary_max được lưu vào database dưới dạng số nguyên, cho phép filter và sort chính xác trong UI. NLP layer sau này có thể impute giá trị ước tính cho các job có `salary = NULL` dựa trên role/company/location tương tự.

### Hàm `normalize_level(level_text: str) -> str`

Map text cấp bậc về Enum chuẩn. Sử dụng kết hợp exact match và keyword detection.

| Input (ví dụ) | Output |
|---|---|
| `"Thực tập sinh"`, `"Intern"`, `"Internship"` | `"INTERN"` |
| `"Mới ra trường"`, `"Fresher"`, `"Entry level"` | `"FRESHER"` |
| `"Nhân viên"`, `"Junior"`, `"1-2 năm"` | `"JUNIOR"` |
| `"Nhân viên có kinh nghiệm"`, `"Mid-level"`, `"2-5 năm"` | `"MID"` |
| `"Chuyên viên cao cấp"`, `"Senior"`, `"5+ năm"` | `"SENIOR"` |
| `"Trưởng nhóm"`, `"Team Lead"`, `"Tech Lead"` | `"LEAD"` |
| `"Quản lý"`, `"Manager"`, `"Director"`, `"Head of"` | `"MANAGER"` |
| Không xác định | `"MID"` (default) |

**Lý do cần chuẩn hóa:** Khi người dùng lọc "việc làm cho Fresher", hệ thống cần so sánh một giá trị duy nhất, không phải đối chiếu với hàng chục cách diễn đạt khác nhau từ các portal.

### Hàm `normalize_job_type(job_type_text: str) -> str`

| Input | Output |
|---|---|
| `"Toàn thời gian"`, `"Full-time"`, `"Permanent"` | `"FULL_TIME"` |
| `"Bán thời gian"`, `"Part-time"` | `"PART_TIME"` |
| `"Hợp đồng"`, `"Contract"`, `"Freelance"`, `"Project-based"` | `"CONTRACT"` |
| `"Làm việc từ xa"`, `"Remote"`, `"Work from home"` | `"REMOTE"` |
| Không xác định | `"FULL_TIME"` (default) |

### Hàm `normalize_location(location_text: str) -> str`

Chuẩn hóa tên tỉnh/thành phố về tên chuẩn tiếng Việt. Đây là trường quan trọng vì user thường filter theo địa điểm.

| Input | Output |
|---|---|
| `"HCM"`, `"TP HCM"`, `"Hồ Chí Minh"`, `"Ho Chi Minh City"` | `"Hồ Chí Minh"` |
| `"HN"`, `"Hà Nội"`, `"Ha Noi"`, `"Hanoi"` | `"Hà Nội"` |
| `"Đà Nẵng"`, `"Da Nang"`, `"DN"` | `"Đà Nẵng"` |
| `"Remote"`, `"Toàn quốc"`, `"Anywhere"`, `"Work from home"` | `"Remote"` |
| `"Bình Dương"`, `"BD"` | `"Bình Dương"` |
| Không mapping được | Giữ nguyên text gốc (capitalized) |

Mapping được lưu trong file config `config/location_mapping.json` để dễ cập nhật khi cần thêm tỉnh/thành mới.

### Hàm `normalize_skills(skills_raw: list[str] | str) -> list[str]`

Chuẩn hóa danh sách kỹ năng từ raw input.

- Nếu input là string: split bằng `,` `/` `;` hoặc `•`
- Strip whitespace từng phần tử
- Loại bỏ phần tử rỗng, quá ngắn (< 2 ký tự) hoặc quá dài (> 60 ký tự)
- Loại bỏ duplicate (case-insensitive)
- Không lowercase — giữ nguyên case gốc để NLP downstream dễ nhận diện tên công nghệ

**Lưu ý:** Trường `skills` trong JobSchema là kỹ năng thô đã được extract trực tiếp từ scraper (ví dụ: thẻ tag có sẵn trên portal). Việc trích xuất kỹ năng từ văn bản mô tả tự do là nhiệm vụ của NLP Layer, không phải của Normalizer.

### Hàm `normalize_job(cleaned: dict) -> dict`

Hàm tổng hợp apply toàn bộ normalization. Nhận output của `clean_job()`, trả về dict sẵn sàng cho Pydantic validation.

---

## 3. Schema (`schemas.py`)

### Nhiệm vụ

Định nghĩa schema chuẩn bằng Pydantic v2, đảm bảo type safety và validation business rules trước khi load vào DB. Đây là "cửa kiểm tra cuối cùng" — dữ liệu nào không pass validation bị loại bỏ và log lại.

### Enum Definitions

**JobType:** `FULL_TIME | PART_TIME | CONTRACT | REMOTE`

**JobLevel:** `INTERN | FRESHER | JUNIOR | MID | SENIOR | LEAD | MANAGER`

### JobSchema Fields

| Field | Type | Ghi chú |
|---|---|---|
| `job_id` | str (computed) | SHA256(source + job_url)[:16] |
| `source` | str | "topcv", "itviec", "direct", ... |
| `job_url` | HttpUrl | Validated URL |
| `title` | str (max 500) | Không được rỗng |
| `company` | str | Không được rỗng |
| `location` | str | |
| `salary_min` | int ≥ 0 \| None | |
| `salary_max` | int ≥ salary_min \| None | |
| `salary_currency` | Literal["VND", "USD"] | |
| `job_type` | JobType | Default: FULL_TIME |
| `level` | JobLevel | Default: MID |
| `skills` | list[str] | Mỗi phần tử không rỗng |
| `description` | str (max 10000) | |
| `requirements` | str (max 10000) | |
| `benefits` | str (max 5000) | |
| `posted_date` | date ≤ today | |
| `deadline` | date \| None | |
| `scraped_at` | datetime | |

### Validation Rules

| Field | Rule | Hành động khi vi phạm |
|---|---|---|
| `job_url` | Phải bắt đầu http/https | ValidationError → skip |
| `title` | len > 0 và len ≤ 500 | ValidationError → skip |
| `company` | len > 0 | ValidationError → skip |
| `salary_min` | ≥ 0 nếu có giá trị | ValidationError → set None |
| `salary_max` | ≥ salary_min nếu cả hai có | ValidationError → swap hoặc set None |
| `posted_date` | ≤ date.today() | ValidationError → set today() |
| `description` | Truncate nếu > 10,000 ký tự | Truncate, log WARNING |

### Tạo `job_id` — Idempotency

```
job_id = SHA256( f"{source}::{job_url}" ).hexdigest()[:16]
```

Tính chất quan trọng: cùng một job từ cùng nguồn → luôn tạo ra cùng `job_id`, bất kể scraper được chạy bao nhiêu lần. Đây là điều kiện tiên quyết để `INSERT ON CONFLICT` hoạt động đúng trong lớp Load.

---

## Xử lý Lỗi Transform

| Tình huống | Xử lý | Hành động |
|---|---|---|
| Field bắt buộc bị None/rỗng | ValidationError | Skip job + log ERROR |
| Ngày không parse được | Set None (optional) / today() (bắt buộc) | Log WARNING |
| Lương không parse được | salary_min=None, salary_max=None | Log INFO |
| Skills là chuỗi lạ | normalize_skills() trả về [] | Chấp nhận |
| Description quá dài | Truncate xuống 10,000 ký tự | Log WARNING |
| HTML không clean được | Giữ text gốc, bỏ HTML best-effort | Log WARNING |
| source == "direct" nhưng thiếu company | Skip + log | ERROR |

---

## Ví dụ End-to-End

**Input raw dict từ scraper (TopCV):**

Trường `title` có khoảng trắng thừa `"  Senior Data Engineer  "`, `location` là `"TP HCM"`, `salary_text` là `"20 - 35 triệu"`, `description_html` chứa thẻ HTML, `level_text` là `"Chuyên gia"`.

**Sau Cleaner:**

Title trở thành `"Senior Data Engineer"` (strip whitespace), description trở thành text thuần `"Xây dựng data pipeline"` (bỏ HTML), posted_date trở thành `date(2026, 3, 3)`.

**Sau Normalizer:**

Location trở thành `"Hồ Chí Minh"`, salary_min = 20,000,000, salary_max = 35,000,000, level trở thành `"SENIOR"`, job_type trở thành `"FULL_TIME"`.

**Sau Schema Validation:**

job_id được tạo = `SHA256("topcv::https://topcv.vn/job/123456")[:16]`, tất cả fields có đúng type, object JobSchema sẵn sàng để load vào PostgreSQL.
