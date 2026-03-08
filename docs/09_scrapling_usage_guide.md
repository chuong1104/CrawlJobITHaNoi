# Hướng dẫn sử dụng Scrapling để cào dữ liệu (Quickstart -> Production)

Tài liệu này phân tích nhanh các đoạn code Scrapling bạn đưa và chuẩn hóa thành workflow thực tế để áp dụng vào project ETL hiện tại.

---

## 1. Khi nào dùng Fetcher nào?

| Fetcher/Session | Dùng khi | Ưu điểm | Hạn chế |
|---|---|---|---|
| `Fetcher` / `FetcherSession` | Trang tĩnh, anti-bot thấp | Nhanh, nhẹ, ít tốn RAM | Dễ bị chặn ở site JS-heavy |
| `StealthyFetcher` / `StealthySession` | Có Cloudflare/chống bot vừa-mạnh | Browser stealth, bypass tốt hơn | Chậm hơn HTTP mode |
| `DynamicFetcher` / `DynamicSession` | Cần render JS, chờ DOM/network idle | Lấy dữ liệu sau khi JS chạy | Tốn tài nguyên hơn HTTP mode |
| `Spider` | Crawl nhiều trang, có phân trang/link graph | Quản lý queue, concurrency, callback | Cần thiết kế callback và flow rõ ràng |

Quy tắc thực tế:
- Bắt đầu bằng `FetcherSession` để tối ưu tốc độ.
- Nếu fail do challenge hoặc JS render, nâng lên `StealthySession` hoặc `DynamicSession`.
- Nếu crawl nhiều page và có follow link, chuyển sang `Spider`.

---

## 2. Phân tích các snippet bạn cung cấp

### A. HTTP mode (`FetcherSession`, `Fetcher`)

```python
from scrapling.fetchers import Fetcher, FetcherSession

with FetcherSession(impersonate='chrome') as session:
    page = session.get('https://quotes.toscrape.com/', stealthy_headers=True)
    quotes = page.css('.quote .text::text').getall()

page = Fetcher.get('https://quotes.toscrape.com/')
quotes = page.css('.quote .text::text').getall()
```

Nhận xét:
- Đây là mode nhanh nhất, phù hợp portal đơn giản.
- `impersonate='chrome'` giúp TLS/client fingerprint giống browser phổ biến.
- `stealthy_headers=True` giúp request headers tự nhiên hơn.

Nên dùng trong project:
- `topcv`, `itviec`, `jobsgo`, `joboko`, `ybox` (ưu tiên test từ HTTP mode trước).

### B. Stealth browser (`StealthySession`, `StealthyFetcher`)

```python
from scrapling.fetchers import StealthyFetcher, StealthySession

with StealthySession(headless=True, solve_cloudflare=True) as session:
    page = session.fetch('https://nopecha.com/demo/cloudflare', google_search=False)
    data = page.css('#padded_content a').getall()

page = StealthyFetcher.fetch('https://nopecha.com/demo/cloudflare')
data = page.css('#padded_content a').getall()
```

Nhận xét:
- Dùng cho site có challenge bot mạnh.
- Session mode tốt khi cần crawl nhiều URL liên tiếp vì giữ browser context.
- One-off mode tiện cho script nhỏ, không tối ưu cho batch lớn.

Nên dùng trong project:
- `jobstreet`, `linkedin` hoặc portal có tỷ lệ 403/429 cao.

### C. Dynamic render (`DynamicSession`, `DynamicFetcher`)

```python
from scrapling.fetchers import DynamicFetcher, DynamicSession

with DynamicSession(headless=True, disable_resources=False, network_idle=True) as session:
    page = session.fetch('https://quotes.toscrape.com/', load_dom=False)
    data = page.xpath('//span[@class="text"]/text()').getall()

page = DynamicFetcher.fetch('https://quotes.toscrape.com/')
data = page.css('.quote .text::text').getall()
```

Nhận xét:
- Phù hợp khi nội dung chỉ xuất hiện sau JS execution.
- `network_idle=True` giúp đợi trang tải ổn định trước khi parse.
- `disable_resources=False` có thể làm chậm; trong scraping thực tế thường nên tắt bớt tài nguyên nặng.

### D. Spider API

```python
from scrapling.spiders import Spider, Request, Response

class QuotesSpider(Spider):
    name = "quotes"
    start_urls = ["https://quotes.toscrape.com/"]
    concurrent_requests = 10

    async def parse(self, response: Response):
        for quote in response.css('.quote'):
            yield {
                "text": quote.css('.text::text').get(),
                "author": quote.css('.author::text').get(),
            }

        next_page = response.css('.next a')
        if next_page:
            yield response.follow(next_page[0].attrib['href'])
```

Nhận xét:
- `Spider` phù hợp crawl có phân trang và nhiều nhánh link.
- `concurrent_requests` cần cân bằng để tránh ban IP.
- Với production, nên thêm retry policy, rate-limit, và logging theo từng request.

### E. Multi-session Spider

Ý tưởng đúng:
- Dùng session nhanh cho trang thường.
- Route trang "protected" qua session stealth.

Điểm cần chỉnh trong snippet gốc:
- Tránh gọi `QuotesSpider(...).start()` bên trong `parse()` của spider khác.
- Tránh đặt `import` bên trong callback nếu không cần.
- Nên chuẩn hóa URL trước khi `yield Request(...)`.

---

## 3. Selector API quan trọng

Bạn có thể trộn nhiều kiểu selector trong cùng workflow:

```python
page = Fetcher.get('https://quotes.toscrape.com/')

quotes_css = page.css('.quote')
quotes_xpath = page.xpath('//div[@class="quote"]')
quotes_bs = page.find_all('div', {'class': 'quote'})

first_text = page.css('.quote')[0].css('.text::text').get()
all_text = page.css('.quote').css('.text::text').getall()
```

Best practices:
- Ưu tiên CSS selector cho dễ đọc và bảo trì.
- Dùng XPath khi cần match theo label/quan hệ phức tạp.
- Luôn `.strip()` hoặc normalize whitespace trước khi ghi dữ liệu.

---

## 4. Async usage

```python
import asyncio
from scrapling.fetchers import AsyncStealthySession

async def fetch_many(urls: list[str]):
    async with AsyncStealthySession(max_pages=2) as session:
        tasks = [session.fetch(url) for url in urls]
        pages = await asyncio.gather(*tasks, return_exceptions=True)
        return pages
```

Lưu ý:
- Dùng `return_exceptions=True` để 1 URL lỗi không làm hỏng toàn batch.
- Theo dõi pool stats nếu session hỗ trợ để debug nghẽn tab/browser.

---

## 5. Mẫu workflow chuẩn cho dự án này

Áp dụng theo kiến trúc hiện tại (`BaseScraper` 3 phase):

1. Phase 1: `collect_urls(pages)`
- Cào trang list bằng HTTP mode trước.
- Trích xuất URL job bằng CSS/XPath.

2. Phase 2: `_deduplicate_urls(urls, existing_urls)`
- Loại trùng trong batch.
- Loại URL đã có trong DB.

3. Phase 3: `_fetch_details_batch(new_urls)`
- Chạy song song theo `batch_size`.
- Parse detail -> raw dict chuẩn key.
- Gán `job_id = generate_job_id(source, url)`.

4. Persist raw
- Ghi `data/raw/{source}/{YYYY-MM-DD}.json`.

5. Transform + Load
- Cleaner -> Normalizer -> Pydantic `JobSchema` -> upsert DB.

---

## 6. Mẫu code scraper tối giản (khuyến nghị)

```python
from scrapling.parser import Adaptor

from src.extract.base_scraper import BaseScraper
from src.utils import make_absolute_url


class ExamplePortalScraper(BaseScraper):
    source_name = "example_portal"
    base_url = "https://example.com"
    batch_size = 10

    def get_list_page_url(self, page_num: int) -> str:
        return f"{self.base_url}/jobs?page={page_num}"

    def extract_job_urls(self, list_page_html: str) -> list[str]:
        page = Adaptor(list_page_html)
        urls = page.css("a.job-link::attr(href)").getall()
        return [make_absolute_url(u, self.base_url) for u in urls if u]

    def parse_job_detail(self, detail_html: str, url: str) -> dict:
        page = Adaptor(detail_html)
        title = (page.css("h1::text").get() or "").strip()
        company = (page.css(".company::text").get() or "").strip()

        return {
            "source": self.source_name,
            "job_url": url,
            "title": title,
            "company": company,
            "location": (page.css(".location::text").get() or "").strip(),
            "salary_text": (page.css(".salary::text").get() or "").strip(),
            "description_html": page.css(".job-description").get() or "",
            "requirements_html": page.css(".requirements").get() or "",
            "benefits_html": page.css(".benefits").get() or "",
            "job_type_text": (page.css(".job-type::text").get() or "").strip(),
            "level_text": (page.css(".level::text").get() or "").strip(),
            "posted_date_text": (page.css(".posted-date::text").get() or "").strip(),
            "deadline_text": (page.css(".deadline::text").get() or "").strip(),
        }
```

---

## 7. Checklist chống block khi crawl thật

- Random delay giữa batches (1-3s hoặc cao hơn nếu bị rate-limit).
- Retry theo exponential backoff khi gặp `429/503`.
- Giữ `batch_size` vừa phải (5-15 tùy portal).
- Không fetch lại URL đã tồn tại trong DB.
- Tắt tài nguyên nặng khi dùng browser mode (image/media/font/stylesheet).
- Thêm proxy rotation cho portal có fingerprint mạnh.
- Log đầy đủ URL lỗi để retry sau.

---

## 8. Lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `quotes` rỗng dù request 200 | Selector sai hoặc dữ liệu render bằng JS | In `page.html`, đổi selector, hoặc dùng Dynamic/Stealth |
| Lỗi timeout nhiều | Concurrency quá cao, mạng chậm | Giảm `batch_size`, tăng timeout, thêm retry |
| Bị `403/429` liên tục | Bot detection/rate limit | Delay dài hơn, bật stealth, thêm proxy |
| Trích sai URL relative | Chưa chuẩn hóa URL | Dùng `make_absolute_url()` trước khi fetch detail |
| Parse detail fail từng phần | HTML thay đổi | Viết fallback selector + test fixtures |

---

## 9. Gợi ý kiểm thử nhanh

- Viết fixture HTML list/detail cho từng portal trong `tests/fixtures/`.
- Unit test `extract_job_urls()` và `parse_job_detail()` độc lập, không gọi mạng thật.
- Chạy:

```bash
pytest tests/test_extract/ -v
```

- Trước khi đưa vào DAG, chạy local 1 portal với `pages=1` để xác nhận schema output.

---

## 10. Kết luận

Bộ API Scrapling bạn đưa đã bao phủ đủ 3 mức:
- HTTP nhanh (`Fetcher*`),
- Browser stealth (`Stealthy*`),
- JS render sâu (`Dynamic*`) + crawl orchestration (`Spider`).

Trong project này, hướng đi tối ưu là:
- Mặc định HTTP mode cho đa số portal.
- Chỉ bật Stealthy/Dynamic cho portal khó.
- Duy trì luồng 3 phase hiện có trong `BaseScraper` để đảm bảo tốc độ, idempotency và khả năng scale trong Airflow.
