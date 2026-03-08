# Testing Guide - Unit Tests & Integration Tests

## Tổng quan

Dự án sử dụng **pytest** làm test framework. Tests được chia thành 2 nhóm chính:
- `tests/test_extract/` — Test logic parsing HTML của scrapers
- `tests/test_transform/` — Test cleaning, normalizing và schema validation

---

## Cấu trúc Tests

```
tests/
├── conftest.py                     ← Fixtures dùng chung (pytest fixtures)
├── test_extract/
│   ├── __init__.py
│   ├── conftest.py                 ← Fixtures cho extract (mock HTML, mock responses)
│   ├── test_base_scraper.py        ← Test retry, delay, save_raw
│   ├── test_topcv.py               ← Test parse HTML TopCV
│   ├── test_itviec.py              ← Test parse HTML ITViec
│   ├── test_vietnamworks.py        ← Test parse API response VietnamWorks
│   ├── test_jobsgo.py
│   ├── test_joboko.py
│   ├── test_123job.py
│   ├── test_careerviet.py
│   ├── test_careerlink.py
│   └── test_ybox.py
└── test_transform/
    ├── __init__.py
    ├── test_cleaner.py             ← Test strip HTML, parse dates
    ├── test_normalizer.py          ← Test chuẩn hóa lương, cấp bậc, job type
    └── test_schemas.py             ← Test Pydantic validation
```

---

## `tests/conftest.py` (Root fixtures)

```python
import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def sample_raw_job() -> dict:
    """Raw dict từ scraper (chưa clean, chưa normalize)."""
    return {
        "source": "topcv",
        "title": "  Senior Data Engineer  ",
        "company": "Công ty ABC",
        "location": "TP HCM",
        "salary_text": "20 - 35 triệu",
        "level_text": "Chuyên gia",
        "job_type_text": "Full time",
        "description_html": "<p>Xây dựng <b>data pipeline</b></p>",
        "requirements_html": "<ul><li>3+ năm Python</li></ul>",
        "benefits_html": "",
        "skills_raw": ["Python", "Airflow", "Spark"],
        "posted_date_text": "03/03/2026",
        "deadline_text": "03/04/2026",
        "job_url": "https://www.topcv.vn/job/123456",
        "scraped_at": "2026-03-05T08:30:00Z",
    }
```

---

## Test Extract Layer

### `test_base_scraper.py`

Kiểm tra các chức năng chung của `BaseScraper` mà không cần request thật ra internet.

```python
# Test 1: Retry mechanism
def test_retry_on_429(mock_responses):
    """BaseScraper phải retry khi nhận HTTP 429."""
    mock_responses.add(responses.GET, "https://example.com", status=429)
    mock_responses.add(responses.GET, "https://example.com", status=429)
    mock_responses.add(responses.GET, "https://example.com", status=200, body="OK")

    scraper = MockScraper()
    result = scraper.fetch("https://example.com")

    assert result == "OK"
    assert mock_responses.call_count == 3

# Test 2: Raise sau max retries
def test_raise_after_max_retries(mock_responses):
    """BaseScraper phải raise ScrapingException sau max_retries lần thất bại."""
    for _ in range(4):  # max_retries=3, nên lần 4 là fail hẳn
        mock_responses.add(responses.GET, "https://example.com", status=503)

    scraper = MockScraper(max_retries=3)
    with pytest.raises(ScrapingException):
        scraper.fetch("https://example.com")

# Test 3: save_raw lưu đúng format
def test_save_raw_creates_json(tmp_path):
    """save_raw() phải tạo file JSON đúng path."""
    scraper = MockScraper(output_dir=tmp_path)
    data = [{"title": "Job 1"}, {"title": "Job 2"}]

    path = scraper.save_raw(data, "2026-03-05")

    assert path.exists()
    assert path.suffix == ".json"
    loaded = json.loads(path.read_text())
    assert len(loaded) == 2
```

### `test_topcv.py`

```python
# Dùng fixture HTML thật từ file fixtures/topcv_list.html
@pytest.fixture
def topcv_list_html():
    return (FIXTURES_DIR / "topcv_list.html").read_text(encoding="utf-8")

@pytest.fixture
def topcv_detail_html():
    return (FIXTURES_DIR / "topcv_detail.html").read_text(encoding="utf-8")

# Test 1: parse_job_list trả về đúng số job
def test_parse_job_list_count(topcv_list_html):
    scraper = TopCVScraper()
    jobs = scraper.parse_job_list(topcv_list_html)
    assert len(jobs) >= 1

# Test 2: parse_job_list lấy đúng fields
def test_parse_job_list_fields(topcv_list_html):
    scraper = TopCVScraper()
    jobs = scraper.parse_job_list(topcv_list_html)
    job = jobs[0]

    assert "title" in job
    assert "company" in job
    assert "job_url" in job
    assert job["job_url"].startswith("https://")

# Test 3: parse_job_detail lấy đúng description
def test_parse_job_detail_has_description(topcv_detail_html):
    scraper = TopCVScraper()
    job = scraper.parse_job_detail(topcv_detail_html, url="https://topcv.vn/job/1")

    assert len(job.get("description_html", "")) > 10
    assert job.get("source") == "topcv"
```

### `test_vietnamworks.py`

```python
# Mock API response thay vì gọi thật
@pytest.fixture
def vnw_api_response():
    return {
        "hits": {
            "hits": [
                {
                    "_source": {
                        "job_title": "Data Engineer",
                        "company_name": "VNG Corporation",
                        "location_name_vi": "Hồ Chí Minh",
                        "salary_min": 2000,
                        "salary_max": 3500,
                        ...
                    }
                }
            ]
        }
    }

def test_parse_api_response(vnw_api_response):
    scraper = VietnamWorksScraper()
    jobs = scraper.parse_api_response(vnw_api_response)

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Data Engineer"
```

---

## Test Transform Layer

### `test_cleaner.py`

```python
from src.transform.cleaner import strip_html, parse_date, normalize_whitespace

class TestStripHtml:
    def test_removes_tags(self):
        assert strip_html("<p>Hello <b>World</b></p>") == "Hello World"

    def test_converts_li_to_bullet(self):
        result = strip_html("<ul><li>Item 1</li><li>Item 2</li></ul>")
        assert "- Item 1" in result
        assert "- Item 2" in result

    def test_empty_string(self):
        assert strip_html("") == ""

    def test_none_input(self):
        assert strip_html(None) == ""

    def test_removes_script_tags(self):
        result = strip_html('<script>alert("xss")</script>Nội dung')
        assert "alert" not in result
        assert "Nội dung" in result

class TestParseDate:
    def test_dd_mm_yyyy(self):
        assert parse_date("03/03/2026") == date(2026, 3, 3)

    def test_iso_format(self):
        assert parse_date("2026-03-03") == date(2026, 3, 3)

    def test_relative_days_ago(self):
        result = parse_date("2 ngày trước")
        expected = date.today() - timedelta(days=2)
        assert result == expected

    def test_hom_nay(self):
        assert parse_date("Hôm nay") == date.today()

    def test_invalid_returns_none(self):
        assert parse_date("không phải ngày") is None

    def test_none_input_returns_none(self):
        assert parse_date(None) is None
```

### `test_normalizer.py`

```python
from src.transform.normalizer import normalize_salary, normalize_level, normalize_job_type, normalize_location

class TestNormalizeSalary:
    def test_vnd_range(self):
        min_s, max_s, curr = normalize_salary("10 - 15 triệu")
        assert min_s == 10_000_000
        assert max_s == 15_000_000
        assert curr == "VND"

    def test_up_to(self):
        min_s, max_s, curr = normalize_salary("Lên đến 20 triệu")
        assert min_s is None
        assert max_s == 20_000_000

    def test_negotiable(self):
        min_s, max_s, curr = normalize_salary("Thỏa thuận")
        assert min_s is None
        assert max_s is None

    def test_usd_range(self):
        min_s, max_s, curr = normalize_salary("1000 - 1500 USD")
        assert curr == "USD"
        assert min_s > 0  # Đã quy đổi sang VND

    def test_empty_string(self):
        min_s, max_s, curr = normalize_salary("")
        assert min_s is None
        assert max_s is None

class TestNormalizeLevel:
    @pytest.mark.parametrize("input_text,expected", [
        ("Thực tập sinh", "INTERN"),
        ("Intern", "INTERN"),
        ("Fresher", "FRESHER"),
        ("Mới ra trường", "FRESHER"),
        ("Junior", "JUNIOR"),
        ("Nhân viên", "JUNIOR"),
        ("Senior", "SENIOR"),
        ("Chuyên viên cao cấp", "SENIOR"),
        ("Team Lead", "LEAD"),
        ("Trưởng nhóm", "LEAD"),
        ("Manager", "MANAGER"),
        ("Quản lý", "MANAGER"),
    ])
    def test_mapping(self, input_text, expected):
        assert normalize_level(input_text) == expected

class TestNormalizeLocation:
    @pytest.mark.parametrize("input_text,expected", [
        ("TP HCM", "Hồ Chí Minh"),
        ("HCM", "Hồ Chí Minh"),
        ("Hồ Chí Minh", "Hồ Chí Minh"),
        ("HN", "Hà Nội"),
        ("Ha Noi", "Hà Nội"),
        ("Đà Nẵng", "Đà Nẵng"),
        ("Remote", "Remote"),
        ("Toàn quốc", "Remote"),
    ])
    def test_mapping(self, input_text, expected):
        assert normalize_location(input_text) == expected
```

### `test_schemas.py`

```python
from src.transform.schemas import JobSchema
from pydantic import ValidationError

class TestJobSchema:
    def test_valid_job(self, sample_normalized_job):
        job = JobSchema.model_validate(sample_normalized_job)
        assert job.source == "topcv"
        assert job.job_id is not None
        assert len(job.job_id) == 16

    def test_job_id_is_deterministic(self, sample_normalized_job):
        """Cùng source + url phải cho cùng job_id."""
        job1 = JobSchema.model_validate(sample_normalized_job)
        job2 = JobSchema.model_validate(sample_normalized_job)
        assert job1.job_id == job2.job_id

    def test_missing_title_raises(self, sample_normalized_job):
        sample_normalized_job["title"] = ""
        with pytest.raises(ValidationError):
            JobSchema.model_validate(sample_normalized_job)

    def test_invalid_url_raises(self, sample_normalized_job):
        sample_normalized_job["job_url"] = "not-a-url"
        with pytest.raises(ValidationError):
            JobSchema.model_validate(sample_normalized_job)

    def test_salary_max_less_than_min_raises(self, sample_normalized_job):
        sample_normalized_job["salary_min"] = 20_000_000
        sample_normalized_job["salary_max"] = 10_000_000
        with pytest.raises(ValidationError):
            JobSchema.model_validate(sample_normalized_job)

    def test_future_posted_date_raises(self, sample_normalized_job):
        from datetime import date, timedelta
        sample_normalized_job["posted_date"] = date.today() + timedelta(days=1)
        with pytest.raises(ValidationError):
            JobSchema.model_validate(sample_normalized_job)
```

---

## Chạy Tests

### Chạy toàn bộ

```bash
pytest tests/ -v
```

### Chạy theo nhóm

```bash
# Chỉ test transform
pytest tests/test_transform/ -v

# Chỉ test extract
pytest tests/test_extract/ -v

# Chỉ test cleaner
pytest tests/test_transform/test_cleaner.py -v
```

### Chạy với coverage report

```bash
pytest tests/ --cov=src --cov-report=html
# Mở htmlcov/index.html để xem báo cáo chi tiết
```

### Chạy trong Docker

```bash
docker-compose exec airflow-worker pytest /opt/airflow/tests/ -v
```

---

## Fixtures HTML

Lưu HTML mẫu thực tế từ các portal vào `tests/fixtures/`:

```
tests/
└── fixtures/
    ├── topcv_list.html          ← Trang list jobs của TopCV
    ├── topcv_detail.html        ← Trang detail 1 job TopCV
    ├── itviec_list.html
    ├── itviec_detail.html
    ├── vietnamworks_api.json    ← Response mẫu của API VietnamWorks
    └── ...
```

**Cách lấy HTML mẫu:**
```bash
# Lưu HTML trang list
curl -A "Mozilla/5.0" "https://www.topcv.vn/viec-lam?page=1" > tests/fixtures/topcv_list.html
```

---

## Mục tiêu coverage

| Module | Target coverage |
|---|---|
| `src/transform/cleaner.py` | ≥ 90% |
| `src/transform/normalizer.py` | ≥ 90% |
| `src/transform/schemas.py` | ≥ 85% |
| `src/extract/base_scraper.py` | ≥ 80% |
| `src/extract/*.py` (mỗi portal) | ≥ 70% |
| `src/load/load_to_dw.py` | ≥ 75% |

---

## CI/CD (Tùy chọn)

Thêm file `.github/workflows/test.yml` để tự động chạy tests khi push code:

```yaml
name: Run Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: pytest tests/test_transform/ -v --cov=src/transform
```
