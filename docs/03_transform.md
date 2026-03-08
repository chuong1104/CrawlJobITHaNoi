# Transform Layer - Làm sạch và Chuẩn hóa dữ liệu

## Tổng quan

Lớp Transform nhận **raw data** (dict chưa chuẩn hóa) từ lớp Extract, qua 3 bước:

```
Raw dict (từ scraper)
      │
      ▼
 1. Cleaner         → Làm sạch text, parse ngày tháng, xóa HTML
      │
      ▼
 2. Normalizer      → Chuẩn hóa lương, cấp bậc, loại công việc, địa điểm
      │
      ▼
 3. Schema validate → Pydantic v2 validation + type coercion + tạo job_id
      │
      ▼
JobSchema object (validated, type-safe)
```

---

## Cấu trúc thư mục

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

Chuyển đổi dữ liệu **thô, bẩn** từ HTML sang text thuần và chuẩn hóa format cơ bản.

### Các hàm chính

#### `strip_html(html_text: str) -> str`
Xóa toàn bộ HTML tags, giữ lại text thuần.

```
Input:  "<p>Mô tả <strong>công việc</strong>:</p>\n<ul><li>Task 1</li></ul>"
Output: "Mô tả công việc:\n- Task 1"
```

- Dùng `BeautifulSoup(html, "lxml")` để parse
- Chuyển `<li>` thành `"- item"`, `<br>` thành `"\n"`
- Strip khoảng trắng thừa, loại bỏ dòng trống liên tiếp

#### `parse_date(date_text: str) -> date | None`
Parse nhiều format ngày tháng khác nhau về `datetime.date`.

| Input | Output |
|---|---|
| `"03/03/2026"` | `date(2026, 3, 3)` |
| `"2026-03-03"` | `date(2026, 3, 3)` |
| `"3 tháng 3, 2026"` | `date(2026, 3, 3)` |
| `"2 ngày trước"` | `date.today() - timedelta(2)` |
| `"Hôm nay"` | `date.today()` |
| `"Just now"` | `date.today()` |
| `None` / không hợp lệ | `None` |

#### `normalize_whitespace(text: str) -> str`
- Thay thế `\t`, multiple spaces bằng single space
- Strip leading/trailing whitespace
- Loại bỏ zero-width characters (`\u200b`, `\u00a0`, ...)

#### `clean_job(raw: dict) -> dict`
Hàm tổng hợp, nhận raw dict và apply tất cả cleaning:

```python
def clean_job(raw: dict) -> dict:
    return {
        **raw,
        "title":        normalize_whitespace(raw.get("title", "")),
        "company":      normalize_whitespace(raw.get("company", "")),
        "location":     normalize_whitespace(raw.get("location", "")),
        "description":  strip_html(raw.get("description_html", "")),
        "requirements": strip_html(raw.get("requirements_html", "")),
        "benefits":     strip_html(raw.get("benefits_html", "")),
        "posted_date":  parse_date(raw.get("posted_date_text")),
        "deadline":     parse_date(raw.get("deadline_text")),
    }
```

---

## 2. Normalizer (`normalizer.py`)

### Nhiệm vụ

Chuẩn hóa các trường có nhiều biến thể khác nhau về **giá trị chuẩn** (Enum/số).

### Các hàm chính

#### `normalize_salary(salary_text: str) -> tuple[int|None, int|None, str]`

Parse chuỗi lương thô thành `(min_vnd, max_vnd, currency)`.

**Bảng mapping ví dụ:**

| Input | min | max | currency |
|---|---|---|---|
| `"10 - 15 triệu"` | 10_000_000 | 15_000_000 | VND |
| `"Lên đến 20 triệu"` | None | 20_000_000 | VND |
| `"Từ 15 triệu"` | 15_000_000 | None | VND |
| `"1,000 - 1,500 USD"` | 25_000_000 | 37_500_000 | USD |
| `"Thỏa thuận"` | None | None | VND |
| `"Competitive"` | None | None | VND |
| `"$800 - $1200"` | 20_000_000 | 30_000_000 | USD |

**Logic:**
1. Regex detect số + đơn vị (`triệu`, `tr`, `USD`, `$`, `VNĐ`)
2. Quy đổi đơn vị về VND (1 triệu = 1_000_000)
3. Nếu currency là USD: nhân với tỷ giá cố định (ví dụ: 25,000 VND/USD)
4. Trả về `(None, None, "VND")` nếu không parse được

#### `normalize_level(level_text: str) -> str`

Map text cấp bậc về ENUM chuẩn.

| Input (ví dụ) | Output |
|---|---|
| `"Thực tập sinh"`, `"Intern"` | `"INTERN"` |
| `"Mới ra trường"`, `"Fresher"` | `"FRESHER"` |
| `"Nhân viên"`, `"Junior"`, `"1-2 năm KN"` | `"JUNIOR"` |
| `"Nhân viên có kinh nghiệm"`, `"Mid"` | `"MID"` |
| `"Chuyên viên cao cấp"`, `"Senior"` | `"SENIOR"` |
| `"Trưởng nhóm"`, `"Team Lead"` | `"LEAD"` |
| `"Quản lý"`, `"Manager"`, `"Director"` | `"MANAGER"` |
| Không xác định | `"MID"` (default) |

#### `normalize_job_type(job_type_text: str) -> str`

| Input | Output |
|---|---|
| `"Toàn thời gian"`, `"Full-time"` | `"FULL_TIME"` |
| `"Bán thời gian"`, `"Part-time"` | `"PART_TIME"` |
| `"Hợp đồng"`, `"Contract"`, `"Freelance"` | `"CONTRACT"` |
| `"Làm việc từ xa"`, `"Remote"` | `"REMOTE"` |
| Không xác định | `"FULL_TIME"` (default) |

#### `normalize_location(location_text: str) -> str`

Chuẩn hóa tên tỉnh/thành phố về tên chuẩn.

| Input | Output |
|---|---|
| `"HCM"`, `"TP HCM"`, `"Hồ Chí Minh"`, `"Ho Chi Minh"` | `"Hồ Chí Minh"` |
| `"HN"`, `"Hà Nội"`, `"Ha Noi"` | `"Hà Nội"` |
| `"Đà Nẵng"`, `"Da Nang"`, `"DN"` | `"Đà Nẵng"` |
| `"Remote"`, `"Toàn quốc"` | `"Remote"` |
| Không mapping được | Giữ nguyên text gốc |

#### `normalize_skills(skills_raw: list[str] | str) -> list[str]`

- Nếu input là string (ví dụ: `"Python, Java, SQL"`) → split bằng `,` hoặc `/`
- Strip whitespace, lowercase, loại duplicate
- Loại bỏ skills quá ngắn (< 2 ký tự) hoặc quá dài (> 50 ký tự)

#### `normalize_job(cleaned: dict) -> dict`
Hàm tổng hợp, apply toàn bộ normalization:

```python
def normalize_job(cleaned: dict) -> dict:
    salary_min, salary_max, currency = normalize_salary(cleaned.get("salary_text", ""))
    return {
        **cleaned,
        "salary_min":      salary_min,
        "salary_max":      salary_max,
        "salary_currency": currency,
        "level":           normalize_level(cleaned.get("level_text", "")),
        "job_type":        normalize_job_type(cleaned.get("job_type_text", "")),
        "location":        normalize_location(cleaned.get("location", "")),
        "skills":          normalize_skills(cleaned.get("skills_raw", [])),
    }
```

---

## 3. Schema (`schemas.py`)

### Nhiệm vụ

Định nghĩa schema chuẩn bằng **Pydantic v2**, đảm bảo type safety và validation trước khi load vào DB.

### JobSchema Definition

```python
from pydantic import BaseModel, Field, computed_field
from datetime import date, datetime
from enum import Enum
import hashlib

class JobType(str, Enum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    CONTRACT  = "CONTRACT"
    REMOTE    = "REMOTE"

class JobLevel(str, Enum):
    INTERN   = "INTERN"
    FRESHER  = "FRESHER"
    JUNIOR   = "JUNIOR"
    MID      = "MID"
    SENIOR   = "SENIOR"
    LEAD     = "LEAD"
    MANAGER  = "MANAGER"

class JobSchema(BaseModel):
    # --- Identity ---
    job_id:          str            # SHA256(source + job_url)[:16]
    source:          str
    job_url:         str

    # --- Core info ---
    title:           str
    company:         str
    location:        str

    # --- Salary ---
    salary_min:      int | None = None
    salary_max:      int | None = None
    salary_currency: str        = "VND"

    # --- Classification ---
    job_type:        JobType    = JobType.FULL_TIME
    level:           JobLevel   = JobLevel.MID
    skills:          list[str]  = Field(default_factory=list)

    # --- Content ---
    description:     str        = ""
    requirements:    str        = ""
    benefits:        str        = ""

    # --- Dates ---
    posted_date:     date
    deadline:        date | None = None
    scraped_at:      datetime
```

### Validation rules

| Field | Rule |
|---|---|
| `job_url` | Phải là URL hợp lệ (bắt đầu bằng `http://` hoặc `https://`) |
| `title` | Không được rỗng, tối đa 500 ký tự |
| `company` | Không được rỗng |
| `salary_min` | Nếu có, phải ≥ 0 |
| `salary_max` | Nếu có `salary_min`, phải ≥ `salary_min` |
| `posted_date` | Không được trong tương lai |
| `skills` | Mỗi skill không được rỗng |

### Tạo job_id

```python
@computed_field
@property
def job_id(self) -> str:
    unique_str = f"{self.source}::{self.job_url}"
    return hashlib.sha256(unique_str.encode()).hexdigest()[:16]
```

Đảm bảo **idempotent**: cùng một job từ cùng portal → luôn có cùng `job_id`, phục vụ upsert.

---

## Xử lý lỗi Transform

| Tình huống | Xử lý |
|---|---|
| Field bắt buộc bị None/rỗng | Pydantic raise `ValidationError` → skip job + log |
| Ngày tháng không parse được | Set về `None` (nếu optional) hoặc dùng `date.today()` |
| Lương không parse được | Set `salary_min=None`, `salary_max=None` |
| Skills là chuỗi lạ | `normalize_skills()` trả về `[]` |
| HTML quá dài | Truncate description xuống `MAX_TEXT_LENGTH = 10_000` ký tự |

---

## Ví dụ end-to-end

```python
# Input: Raw dict từ scraper
raw = {
    "source": "topcv",
    "title": "  Senior Data Engineer  ",
    "company": "Công ty ABC",
    "location": "TP HCM",
    "salary_text": "20 - 35 triệu",
    "level_text": "Chuyên gia",
    "job_type_text": "Full time",
    "description_html": "<p>Xây dựng <b>data pipeline</b></p>",
    "requirements_html": "<ul><li>3+ năm Python</li><li>Biết Airflow</li></ul>",
    "skills_raw": ["Python", "Airflow", "Spark", "SQL"],
    "posted_date_text": "03/03/2026",
    "deadline_text": "03/04/2026",
    "job_url": "https://www.topcv.vn/job/123456",
    "scraped_at": "2026-03-05T08:30:00Z"
}

# Bước 1: Clean
cleaned = clean_job(raw)
# title → "Senior Data Engineer"
# description → "Xây dựng data pipeline"
# posted_date → date(2026, 3, 3)

# Bước 2: Normalize
normalized = normalize_job(cleaned)
# location → "Hồ Chí Minh"
# salary_min → 20_000_000, salary_max → 35_000_000
# level → "SENIOR"
# job_type → "FULL_TIME"

# Bước 3: Validate
job = JobSchema.model_validate(normalized)
# job.job_id → "a3f1b2c4d5e6f7a8"  (SHA256 hash)
```
