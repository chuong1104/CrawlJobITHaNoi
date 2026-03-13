# 07 — Testing Guide — Unit Tests & Integration Tests

> **Cập nhật:** 2026-03-11 | Phiên bản: 2.0  
> Bổ sung test strategy cho NLP Layer (skill extraction, embedding), Search Layer (hybrid search), và Company Crawler. Làm rõ nguyên tắc tổ chức test theo từng giai đoạn phát triển.

---

## Tổng quan

Dự án sử dụng **pytest** làm test framework. Chiến lược testing tuân theo nguyên tắc: **test sớm, test độc lập, test theo layer**. Mỗi layer có bộ test riêng, không phụ thuộc vào layer khác khi chạy unit test.

Tests được chia thành bốn nhóm chính, phát triển theo từng giai đoạn:

| Nhóm | Layer | Giai đoạn | Coverage target |
|---|---|---|---|
| `test_extract/` | Data Collection | 1 | ≥ 70% |
| `test_transform/` | Transform | 1 | ≥ 90% |
| `test_load/` | Load | 1 | ≥ 75% |
| `test_nlp/` | NLP Processing | 2 | ≥ 80% |
| `test_search/` | Search | 2 | ≥ 80% |

---

## Cấu trúc Tests

```
tests/
├── conftest.py                         ← Root fixtures dùng chung
├── fixtures/                           ← HTML mẫu và JSON mẫu
│   ├── topcv_list.html
│   ├── topcv_detail.html
│   ├── itviec_list.html
│   ├── itviec_detail.html
│   ├── vietnamworks_api.json
│   ├── company_list.html               ← JobsGO company list
│   ├── company_detail.html             ← JobsGO company detail
│   └── career_page_sample.html         ← Mẫu career page
│
├── test_extract/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_base_scraper.py
│   ├── test_topcv.py
│   ├── test_itviec.py
│   ├── test_vietnamworks.py
│   ├── test_jobsgo.py
│   ├── test_joboko.py
│   ├── test_123job.py
│   ├── test_careerviet.py
│   ├── test_careerlink.py
│   ├── test_ybox.py
│   └── test_company/
│       ├── test_company_list_crawler.py
│       ├── test_company_detail_crawler.py
│       ├── test_career_page_finder.py
│       └── test_career_page_scraper.py
│
├── test_transform/
│   ├── __init__.py
│   ├── test_cleaner.py
│   ├── test_normalizer.py
│   └── test_schemas.py
│
├── test_load/
│   ├── __init__.py
│   └── test_load_to_dw.py
│
├── test_nlp/                           ← [Giai đoạn 2]
│   ├── __init__.py
│   ├── test_skill_extractor.py
│   ├── test_embedder.py
│   └── test_job_classifier.py
│
└── test_search/                        ← [Giai đoạn 2]
    ├── __init__.py
    ├── test_bm25.py
    ├── test_vector_search.py
    └── test_hybrid_search.py
```

---

## Root Fixtures (`conftest.py`)

### Fixture `sample_raw_job`

Raw dict từ scraper chưa qua bất kỳ xử lý nào — title có whitespace thừa, location là dạng viết tắt, salary là chuỗi text, description chứa HTML. Đây là trạng thái "bẩn nhất" trước khi vào pipeline Transform.

### Fixture `sample_normalized_job`

Dict đã qua Clean + Normalize, sẵn sàng cho Pydantic validation. Location đã là "Hồ Chí Minh", salary là số nguyên, description là text thuần.

### Fixture `sample_job_schema`

JobSchema object đã validated hoàn chỉnh. Dùng làm input test cho Load layer và NLP layer.

### Fixture `mock_db_connection`

Mock psycopg2 connection cho các test không cần DB thật. Trả về MagicMock cho phép assert số lần gọi và tham số.

---

## Test Extract Layer

### `test_base_scraper.py` — Test Logic Chung

**Test retry mechanism:** Mock HTTP responses trả về 429 hai lần rồi 200 lần thứ ba. Assert scraper gọi đúng 3 lần và trả về kết quả đúng. Test này xác minh exponential backoff hoạt động đúng.

**Test raise sau max retries:** Mock tất cả responses đều trả về 503. Assert `ScrapingException` được raise sau đúng `max_retries` lần thất bại.

**Test save_raw:** Sử dụng `tmp_path` fixture của pytest để tạo thư mục tạm. Assert file JSON được tạo đúng path, nội dung parse được, và có đúng số phần tử.

**Test deduplication:** Mock DB trả về một tập URLs đã tồn tại. Assert `deduplicate_urls()` loại đúng các URLs đó và chỉ giữ lại URLs mới.

### `test_topcv.py` — Test Portal Scraper

**Nguyên tắc:** Sử dụng HTML fixture từ file thực tế (lấy từ portal bằng curl), không mock request để test đúng logic selector.

**Test `parse_job_list`:** Assert kết quả có ≥ 1 phần tử, mỗi phần tử có đủ fields `title`, `company`, `job_url`, và `job_url` bắt đầu bằng `https://`.

**Test `parse_job_detail`:** Assert `description_html` có nội dung có nghĩa (len > 10), `source` đúng là `"topcv"`, các fields không bị None hoàn toàn.

**Test negative case:** HTML bị thay đổi selector không tìm thấy → Assert trả về dict với fields None/empty thay vì raise exception. Scraper không được crash, chỉ trả về dữ liệu thiếu.

### `test_company/test_career_page_finder.py` — Test Company Crawler

**Test path probing:** Mock HTTP responses. Giả lập server có `/careers` trả về 200 với nội dung có từ "jobs". Assert `career_page_finder` tìm được URL đúng.

**Test ATS detection:** Cung cấp HTML có chứa link `boards.greenhouse.io`. Assert finder nhận diện đúng ATS type là "greenhouse".

**Test not found:** Tất cả paths đều trả về 404, sitemap rỗng, navigation không có từ khóa tuyển dụng. Assert trả về `None` thay vì raise.

---

## Test Transform Layer

### `test_cleaner.py`

#### TestStripHtml

Kiểm tra các trường hợp:
- Xóa thẻ `<strong>`, `<p>`, `<div>` đơn giản
- Chuyển `<li>` thành `"- item"` giữ cấu trúc list
- Xóa `<script>` và `<style>` hoàn toàn, không để lại content
- Decode HTML entities (`&amp;` → `&`, `&nbsp;` → space)
- Input None → trả về empty string (không raise)
- Input rỗng → trả về empty string

#### TestParseDate

Kiểm tra các format:
- ISO format `YYYY-MM-DD`
- Vietnamese format `DD/MM/YYYY`
- Relative: `"2 ngày trước"`, `"1 tuần trước"`, `"Hôm nay"`
- English relative: `"2 days ago"`, `"Today"`, `"Just now"`
- Invalid → None
- None input → None

**Quan trọng:** Test relative dates phải mock `date.today()` để kết quả deterministic, không phụ thuộc ngày chạy test.

#### TestNormalizeWhitespace

- Tab → single space
- Multiple spaces → single space
- Leading/trailing whitespace bị strip
- Zero-width characters `\u200b` bị loại bỏ
- Non-breaking space `\u00a0` được thay bằng space thường

### `test_normalizer.py`

#### TestNormalizeSalary

Kiểm tra toàn bộ bảng mapping đã định nghĩa trong tài liệu Transform. Đặc biệt cần test:
- Range có dấu `-` với các khoảng trắng khác nhau: `"10-15 triệu"`, `"10 - 15 triệu"`, `"10- 15triệu"`
- USD range → kết quả là số dương (đã quy đổi sang VND)
- salary_min ≤ salary_max trong mọi trường hợp parse được
- Mọi input "thỏa thuận" dạng → `(None, None, "VND")`

#### TestNormalizeLevel (parametrize)

Sử dụng `@pytest.mark.parametrize` với bảng đầy đủ mapping từ tài liệu. Đảm bảo không có input hợp lệ nào bị map về giá trị không đúng.

#### TestNormalizeLocation

Test toàn bộ aliases: HCM/TP HCM/Hồ Chí Minh/Ho Chi Minh → "Hồ Chí Minh". Test case-insensitive matching. Test location không trong mapping → trả về text gốc (đã capitalized), không raise.

### `test_schemas.py`

#### TestJobSchema

**Test job_id deterministic:** Tạo hai JobSchema từ cùng một dict, assert `job1.job_id == job2.job_id`.

**Test validation errors:**
- Title rỗng → `ValidationError`
- `job_url` không phải URL → `ValidationError`
- `salary_max < salary_min` → `ValidationError`
- `posted_date` trong tương lai → `ValidationError`

**Test default values:** Không cung cấp `job_type` → mặc định là `"FULL_TIME"`. Không cung cấp `level` → mặc định là `"MID"`.

**Test truncation:** Description dài hơn 10,000 ký tự → được truncate, không raise.

**Test source "direct":** Tạo JobSchema với `source = "direct"` → hợp lệ, job_id khác với cùng job từ portal.

---

## Test Load Layer

### `test_load_to_dw.py`

**Test batch splitting:** Cung cấp 1,100 jobs, assert `execute_values` được gọi đúng 3 lần (batch 500 + 500 + 100).

**Test upsert idempotency (integration):** Dùng PostgreSQL test database (pytest-postgresql hoặc docker test container). Load cùng một danh sách jobs hai lần, assert bảng `jobs` chỉ có số bản ghi của lần đầu, không bị duplicate.

**Test NLP flag reset:** Load một job, sau đó update `nlp_processed=TRUE` trong DB. Load lại job đó với `description` khác, assert `nlp_processed` được reset về `FALSE`.

**Test partial failure:** Trong batch có một record vi phạm constraint. Assert batch được rollback và thử lại từng record, chỉ record lỗi bị skip, các record còn lại được insert thành công.

**Test scrape_log được ghi:** Assert bảng `scrape_logs` có bản ghi mới sau mỗi lần `load_jobs()` với `status="SUCCESS"` và số liệu thống kê chính xác.

---

## Test NLP Layer (Giai đoạn 2)

### `test_skill_extractor.py`

**Test dictionary matching:** Cung cấp text `"Yêu cầu: Python, SQL, và kinh nghiệm với Apache Spark"`. Assert kết quả extract chứa đúng ba skill: Python, SQL, Apache Spark. Assert confidence của exact match là 1.0.

**Test fuzzy matching:** Cung cấp text có lỗi chính tả nhỏ `"Pyhton"` hoặc viết tắt `"PySpark"`. Assert skill được nhận diện với confidence < 1.0 nhưng vẫn vượt ngưỡng.

**Test no false positive:** Text không liên quan `"Công ty có văn hóa tốt và môi trường thân thiện"`. Assert không extract ra kỹ năng kỹ thuật nào có confidence cao.

**Test position tagging:** Cùng một kỹ năng xuất hiện ở cả title lẫn description → assert position được ghi nhận đúng.

### `test_embedder.py`

**Test output shape:** Embed một job, assert kết quả là vector có dimension đúng với model (768 cho multilingual-e5-base).

**Test semantic similarity:** Embed hai jobs có mô tả tương tự nhau (cùng là Data Engineer), embed một job khác hoàn toàn (Marketing). Assert cosine similarity của hai jobs cùng loại cao hơn similarity với job khác loại.

**Test batch consistency:** Embed 10 jobs theo batch, embed từng job riêng lẻ, assert kết quả giống nhau (batch không làm thay đổi output).

**Test với mock model:** Trong unit test, mock SentenceTransformer để trả về vector ngẫu nhiên có đúng dimension. Không cần load model thật để test pipeline logic.

---

## Test Search Layer (Giai đoạn 2)

### `test_bm25.py`

**Test basic retrieval:** Index 10 job documents, query "Python data engineer", assert kết quả có job liên quan ở top và không có job hoàn toàn không liên quan ở top 3.

**Test IDF weighting:** Document có từ hiếm được tìm kiếm → nên xếp hạng cao hơn document có nhiều từ phổ biến nhưng ít liên quan.

### `test_vector_search.py`

**Test với mock pgvector:** Mock `execute()` của psycopg2 để trả về list (job_id, similarity_score) giả. Assert hàm search parse kết quả đúng và sort theo score giảm dần.

### `test_hybrid_search.py`

**Test score fusion:** Cung cấp BM25 results và vector results với scores giả. Assert Reciprocal Rank Fusion tính điểm đúng theo công thức `1/(k + rank)`.

**Test deduplication:** Cùng job_id xuất hiện trong cả BM25 và vector results. Assert kết quả cuối chỉ có một bản ghi, không bị duplicate.

---

## Chạy Tests

```bash
# Toàn bộ test suite
pytest tests/ -v

# Theo nhóm
pytest tests/test_transform/ -v
pytest tests/test_extract/ -v
pytest tests/test_nlp/ -v

# Với coverage
pytest tests/ --cov=src --cov-report=html --cov-report=term-missing

# Chỉ test nhanh (skip integration tests cần DB)
pytest tests/ -v -m "not integration"

# Chạy trong Docker
docker-compose exec airflow-worker pytest /opt/airflow/tests/ -v

# Chạy parallel (cần pytest-xdist)
pytest tests/ -n auto
```

### Đánh dấu Test

```python
@pytest.mark.integration   # Test cần DB thật
@pytest.mark.slow          # Test chạy lâu (NLP model)
@pytest.mark.unit          # Test thuần logic, không cần external
```

---

## Fixtures HTML

Lưu HTML mẫu thực tế vào `tests/fixtures/`. Cần cập nhật định kỳ vì portal thay đổi HTML structure.

```bash
# Cập nhật HTML fixtures
curl -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0" \
     "https://www.topcv.vn/viec-lam?page=1" \
     -o tests/fixtures/topcv_list.html
```

**Chú ý:** HTML fixtures được commit vào git. Khi portal thay đổi cấu trúc HTML và tests bắt đầu fail, đó là tín hiệu cần cập nhật selector trong scraper.

---

## Mục tiêu Coverage

| Module | Target | Ghi chú |
|---|---|---|
| `src/transform/cleaner.py` | ≥ 90% | Nhiều nhánh edge case |
| `src/transform/normalizer.py` | ≥ 90% | Nhiều regex pattern |
| `src/transform/schemas.py` | ≥ 85% | Validation rules |
| `src/extract/base_scraper.py` | ≥ 80% | Retry logic |
| `src/extract/portals/*.py` | ≥ 70% | Mỗi portal scraper |
| `src/extract/company/*.py` | ≥ 70% | Company crawlers |
| `src/load/load_to_dw.py` | ≥ 75% | Batch logic + error handling |
| `src/nlp/skill_extractor.py` | ≥ 80% | NLP logic |
| `src/search/hybrid_search.py` | ≥ 80% | Fusion logic |

---

## CI/CD Pipeline

File `.github/workflows/test.yml` tự động chạy test khi push hoặc pull request:

**Job 1 — Unit Tests (nhanh, không cần DB):**
- Python 3.11, install dependencies
- `pytest tests/test_transform/ tests/test_extract/ -v -m "not integration" --cov=src/transform --cov=src/extract`

**Job 2 — Integration Tests (chậm hơn, cần PostgreSQL):**
- Khởi động PostgreSQL service trong GitHub Actions
- `pytest tests/test_load/ -v -m "integration"`

**Job 3 — NLP Tests (rất chậm, chạy ít hơn):**
- Chỉ chạy khi có thay đổi trong `src/nlp/`
- `pytest tests/test_nlp/ -v -m "not slow"` (bỏ qua test cần load model thật)

---

## Nguyên tắc Viết Test Tốt cho Dự án Này

Không test third-party libraries: không test Scrapling hoạt động đúng, không test Pydantic validate đúng. Chỉ test logic của code chúng ta viết.

Dùng fixture HTML thực: test scraper trên HTML thật từ portal, không mock HTMLParser. Điều này đảm bảo test phản ánh đúng reality và catch được khi portal thay đổi cấu trúc.

Mock ở ranh giới hệ thống: mock HTTP request (không gọi Internet), mock DB connection (không cần DB thật trong unit test), mock NLP model (không load weights thật trong unit test).

Parametrize thay vì copy-paste: mọi bảng mapping trong Normalizer đều phải được test bằng `@pytest.mark.parametrize`, không viết 15 test function riêng lẻ.

Test edge cases trước happy path: khi dữ liệu thực tế 30% là "lạ" (salary=thỏa thuận, date=không rõ, location=null), edge cases quan trọng hơn happy path.
