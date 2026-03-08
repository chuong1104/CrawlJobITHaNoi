# Scrapling Portals Reference

Tài liệu implement từng scraper sử dụng **Scrapling**, theo luồng 3 giai đoạn tích hợp vào `BaseScraper`.

---

## 1. Luồng cào tổng thể

```
BaseScraper.run(pages)

 Phase 1  collect_urls(pages)
    Với mỗi trang list:
       StealthyFetcher / PlaywrightFetcher  HTML
       extract_job_urls(html)  list[str]    Override tại scraper con

 Phase 2  deduplicate_urls(urls)
    dedup nội bộ (set)
    loại URL đã có trong DB (query bảng jobs.job_url)

 Phase 3  fetch_details_batch(urls)
    chia thành batches (batch_size)
    ThreadPoolExecutor(fetch_one per URL)
      block_resources=True  tắt image/font/css/media
    parse_job_detail(html, url)  dict   Override tại scraper con

 save_raw(results, date_str)  data/raw/{source}/{YYYY-MM-DD}.json
```

**Scraper con chỉ cần implement 2 method:**

```python
def extract_job_urls(self, list_page_html: str) -> list[str]: ...
def parse_job_detail(self, detail_html: str, url: str) -> dict: ...
```

---

## 2. Scrapling API thiết yếu

### Fetchers

| Fetcher | Dùng cho | Tham số quan trọng |
|---|---|---|
| `StealthyFetcher` | Hầu hết portal (HTTP mode) | `block_resources=True`, `network_idle=False` |
| `PlaywrightFetcher` | Portal JS-heavy / chặn mạnh | `stealth=True`, `headless=True`, `block_resources=True`, `extra_cookies` |

```python
from scrapling import StealthyFetcher, PlaywrightFetcher
from scrapling.parser import Adaptor   # Parse HTML tĩnh, không cần fetch

# Fetch trang web
page = StealthyFetcher().get(url, block_resources=True, network_idle=False)

# Parse HTML có sẵn (dùng trong parse_job_detail)
page = Adaptor(html_string)
```

### Selector cheatsheet

```python
# Text đầu tiên
page.css("h1.title::text").get()

# Tất cả text, lọc trống, nối lại
" ".join(p.strip() for p in page.css("div.desc ::text").getall() if p.strip())

# Attribute
page.css("a.job-link::attr(href)").getall()

# XPath  tìm text theo label
page.xpath('//div[contains(text(), "Lương")]/following-sibling::div[1]//text()').get()

# Nested Adaptor
for item in page.css("div.benefit-item"):   #  list[Adaptor]
    item.css("::text").getall()
```

---

## 3. Quy ước output dict

Mỗi `parse_job_detail()` trả về dict với các key sau (trường `None` nếu không tìm thấy):

```python
{
    "title":            str | None,
    "company":          str | None,
    "salary":           str | None,
    "location":         str | None,
    "job_type":         str | None,
    "experience_level": str | None,
    "education_level":  str | None,
    "job_industry":     str | None,
    "job_position":     str | None,
    "job_description":  str | None,
    "requirements":     str | None,
    "benefits":         str | None,
    "job_deadline":     str | None,
    "job_url":          str,          # bắt buộc
    "source":           str,          # bắt buộc, = self.source_name
    "scraped_at":       str,          # datetime.now().isoformat()
}
```

---

## 4. CareerLink (`careerlink.vn`)

| | |
|---|---|
| `source_name` | `"careerlink"` |
| `base_url` | `https://www.careerlink.vn` |
| Fetcher | `StealthyFetcher` |
| `batch_size` | `10` |

### URL & Pagination

```python
from urllib.parse import quote

list_url  = f"https://www.careerlink.vn/viec-lam/k/{quote(keyword)}"
next_page = page.css('a[href*="?page="]::attr(href)').get()
# Link relative  thêm "https://www.careerlink.vn" + next_page
```

### Phase 1  extract_job_urls

```python
page = Adaptor(list_page_html)
return page.css('a[class*="job-link"][href*="tim-viec-lam"]::attr(href)').getall()
```

### Phase 3  Selectors

| Trường | Phương thức | Selector / Label |
|---|---|---|
| `title` | CSS | `h1#job-title::text` |
| `company` | CSS | `a[href*="viec-lam-cua"] ::text` |
| `salary` | XPath icon | icon class `cli-currency-circle-dollar` |
| `location` | XPath icon | `cli-map-pin-line`  fallback `cli-building` |
| `job_type` | XPath label | `"Loại công việc"` |
| `experience_level` | XPath label | `"Kinh nghiệm"` |
| `education_level` | XPath label | `"Học vấn"` |
| `job_industry` | XPath label | `"Ngành nghề"`  getall() |
| `job_position` | XPath label | `"Cấp bậc"` |
| `job_deadline` | CSS + regex | `div[class*="day-expired"]`  parse "còn N ngày" |
| `job_description` | CSS | `div.rich-text-content ::text` |
| `requirements` | CSS | `div.raw-content.rich-text-content ::text` |
| `benefits` | CSS loop | `div[class*="job-benefit-item"]` |

### parse_job_detail

```python
import re
from datetime import datetime, timedelta
from scrapling.parser import Adaptor

def parse_job_detail(self, detail_html: str, url: str) -> dict:
    page = Adaptor(detail_html)

    def _by_icon(icon_class):
        parts = page.xpath(
            f"//i[contains(@class,'{icon_class}')]/following-sibling::span[1]//text()"
        ).getall()
        return " ".join(p.strip() for p in parts if p.strip()) or None

    def _by_label(label, all_text=False):
        xpath = f'//div[contains(text(),"{label}")]/following-sibling::div[1]//text()'
        if all_text:
            parts = page.xpath(xpath).getall()
            return " ".join(p.strip() for p in parts if p.strip()) or None
        t = page.xpath(xpath).get()
        return t.strip() if t else None

    # Deadline
    deadline = None
    deadline_parts = page.css('div[class*="day-expired"] ::text').getall()
    if deadline_parts:
        m = re.search(r"\d+", " ".join(deadline_parts))
        if m:
            deadline = (datetime.now().date() + timedelta(days=int(m.group()))).strftime("%Y-%m-%d")

    # Benefits
    benefits_list = []
    for item in page.css('div[class*="job-benefit-item"]'):
        t = " ".join(x.strip() for x in item.css("::text").getall() if x.strip())
        if t:
            benefits_list.append(t)

    return {
        "title":            page.css("h1#job-title::text").get(),
        "company":          page.css('a[href*="viec-lam-cua"] ::text').get(),
        "salary":           _by_icon("cli-currency-circle-dollar"),
        "location":         _by_icon("cli-map-pin-line") or _by_icon("cli-building"),
        "job_type":         _by_label("Loại công việc"),
        "experience_level": _by_label("Kinh nghiệm"),
        "education_level":  _by_label("Học vấn"),
        "job_industry":     _by_label("Ngành nghề", all_text=True),
        "job_position":     _by_label("Cấp bậc"),
        "job_deadline":     deadline,
        "job_description":  " ".join(p.strip() for p in page.css("div.rich-text-content ::text").getall() if p.strip()) or None,
        "requirements":     " ".join(p.strip() for p in page.css("div.raw-content.rich-text-content ::text").getall() if p.strip()) or None,
        "benefits":         " ".join(benefits_list) or None,
        "job_url":          url,
        "source":           self.source_name,
        "scraped_at":       datetime.now().isoformat(),
    }
```

---

## 5. CareerViet (`careerviet.vn`)

| | |
|---|---|
| `source_name` | `"careerviet"` |
| `base_url` | `https://careerviet.vn` |
| Fetcher | `StealthyFetcher` |
| `batch_size` | `10` |

### URL & Pagination

```python
from urllib.parse import quote

list_url  = f"https://careerviet.vn/viec-lam/{quote(keyword.replace(' ', '-'))}-k-vi.html"
next_page = page.css('li[class*="next-page"] a::attr(href)').get()
```

### Phase 1  extract_job_urls

```python
page = Adaptor(list_page_html)
return list(set(page.css('a[href*="/tim-viec-lam/"]::attr(href)').getall()))
```

### Phase 3  Selectors

| Trường | Selector / Label |
|---|---|
| `title` | CSS `h1.title::text` |
| `company` | CSS `a.employer.job-company-name::text` |
| `salary` | XPath `<strong>Lương</strong>`  `following-sibling::p` |
| `location` | XPath `<strong>Địa điểm</strong>` |
| `job_type` | XPath `<strong>Hình thức</strong>` |
| `experience_level` | XPath `<strong>Kinh nghiệm</strong>` + normalize space |
| `education_level` | CSS `div.content_fck li::text`  tìm dòng chứa `"Bằng cấp"` |
| `job_industry` | XPath `<strong>Ngành nghề</strong>` |
| `job_position` | XPath `<strong>Cấp bậc</strong>` |
| `job_description` | XPath `h2[Mô tả Công việc]`  all following sibling text |
| `requirements` | XPath `h2[Yêu Cầu Công Việc]` |
| `benefits` | XPath `h2[Phúc lợi]` |
| `job_deadline` | XPath `<strong>Hết hạn nộp</strong>` |

### parse_job_detail

```python
from datetime import datetime
from scrapling.parser import Adaptor

def parse_job_detail(self, detail_html: str, url: str) -> dict:
    page = Adaptor(detail_html)

    def _strong_text(label):
        parts = page.xpath(
            f'//strong[contains(normalize-space(.), "{label}")]/following-sibling::p//text()'
        ).getall()
        return " ".join(p.strip() for p in parts if p.strip()) or None

    def _h2_paragraph(heading):
        parts = page.xpath(
            f'//h2[contains(normalize-space(.), "{heading}")]/following-sibling::*//text()'
        ).getall()
        return " ".join(p.strip() for p in parts if p.strip()) or None

    # Education  tìm trong li
    education = None
    for li in page.css("div.content_fck li::text").getall():
        if "Bằng cấp" in li:
            education = " ".join(li.split())
            break

    exp_raw = _strong_text("Kinh nghiệm")
    return {
        "title":            page.css("h1.title::text").get(),
        "company":          page.css("a.employer.job-company-name::text").get(),
        "salary":           _strong_text("Lương"),
        "location":         _strong_text("Địa điểm"),
        "job_type":         _strong_text("Hình thức"),
        "experience_level": " ".join(exp_raw.split()) if exp_raw else None,
        "education_level":  education,
        "job_industry":     _strong_text("Ngành nghề"),
        "job_position":     _strong_text("Cấp bậc"),
        "job_deadline":     _strong_text("Hết hạn nộp"),
        "job_description":  _h2_paragraph("Mô tả Công việc"),
        "requirements":     _h2_paragraph("Yêu Cầu Công Việc"),
        "benefits":         _h2_paragraph("Phúc lợi"),
        "job_url":          url,
        "source":           self.source_name,
        "scraped_at":       datetime.now().isoformat(),
    }
```

---

## 6. ITViec (`itviec.com`)

| | |
|---|---|
| `source_name` | `"itviec"` |
| `base_url` | `https://itviec.com` |
| Fetcher | `StealthyFetcher` |
| `batch_size` | `15` |

> Không cần đăng nhập để cào thông tin cơ bản. Lương bị ẩn một phần nếu chưa login  trả về `None` khi gặp `"Sign in to view"`.

### URL & Pagination

```python
list_url  = f"https://itviec.com/it-jobs/{keyword.replace(' ', '-')}"
next_page = page.css("a[rel='next']::attr(href)").get()
# Link relative  "https://itviec.com" + next_page
```

### Phase 1  extract_job_urls

```python
page = Adaptor(list_page_html)
relative_urls = page.css("h3[data-url*='/it-jobs/']::attr(data-url)").getall()
return [
    f"https://itviec.com{u}" if u.startswith("/") else u
    for u in relative_urls
]
```

### Phase 3  Selectors

| Trường | Selector |
|---|---|
| `title` | `h1[class*="text-it-black"]::text` |
| `company` | `a[href*="/companies/"][class*="normal-text"]::text` |
| `salary` | `span.ips-2.fw-500::text`  check `"sign in"`  `None` |
| `location` | `div.d-inline-block.text-dark-grey::text` |
| `job_description` | `section.job-description ::text` |
| `requirements` | `section.job-experiences ::text` |
| `benefits` | `section.job-why-love-working ::text` |
| `job_industry` | `div.d-inline-flex.text-wrap::text` |
| Các trường còn lại | `None`  ITViec không hiển thị |

### parse_job_detail

```python
from datetime import datetime
from scrapling.parser import Adaptor

def parse_job_detail(self, detail_html: str, url: str) -> dict:
    page = Adaptor(detail_html)

    def _section(selector):
        parts = page.css(f"{selector} ::text").getall()
        return " ".join(p.strip() for p in parts if p.strip()) or None

    salary_raw = page.css("span.ips-2.fw-500::text").get()
    salary = None if (salary_raw and "sign in" in salary_raw.lower()) else (salary_raw.strip() if salary_raw else None)

    return {
        "title":            page.css('h1[class*="text-it-black"]::text').get(),
        "company":          page.css('a[href*="/companies/"][class*="normal-text"]::text').get(),
        "salary":           salary,
        "location":         page.css("div.d-inline-block.text-dark-grey::text").get(),
        "job_type":         None,
        "experience_level": None,
        "education_level":  None,
        "job_industry":     page.css("div.d-inline-flex.text-wrap::text").get(),
        "job_position":     None,
        "job_deadline":     None,
        "job_description":  _section("section.job-description"),
        "requirements":     _section("section.job-experiences"),
        "benefits":         _section("section.job-why-love-working"),
        "job_url":          url,
        "source":           self.source_name,
        "scraped_at":       datetime.now().isoformat(),
    }
```

---

## 7. 123job (`123job.vn`)

| | |
|---|---|
| `source_name` | `"job_123"` |
| `base_url` | `https://123job.vn` |
| Fetcher | `StealthyFetcher` |
| `batch_size` | `10` |

### URL & Pagination

```python
from urllib.parse import quote

list_url  = f"https://123job.vn/tuyen-dung?q={quote(keyword)}"
next_page = page.css('a[rel="Next"]::attr(href)').get()
```

### Phase 1  extract_job_urls

```python
page = Adaptor(list_page_html)
return list(set(page.css('a[href*="/viec-lam/"]::attr(href)').getall()))
```

### Phase 3  Selectors

| Trường | Selector / Label |
|---|---|
| `title` | CSS `[class*='job-title'] ::text` |
| `company` | CSS `[class*='company-name'] ::text` |
| `salary` | XPath: `div.attr-item` chứa `i[class*="la-money"]`  `div[class*="value"]` |
| `location` | XPath label `"Khu vực"` |
| `job_type` | XPath label `"Hình thức làm việc"` |
| `experience_level` | XPath `div[contains(., "Kinh nghiệm yêu cầu")]/following-sibling::div[1]` |
| `education_level` | XPath label `"Trình độ yêu cầu"` |
| `job_industry` | XPath label `"Ngành nghề"` |
| `job_position` | XPath label `"Cấp bậc"` |
| `job_deadline` | XPath label `"Hạn nộp"` |
| `job_description` | XPath `h2[Mô tả công việc]`  `following-sibling::*[1]` |
| `requirements` | XPath `h2[Yêu cầu]` |
| `benefits` | XPath `h2[Quyền lợi]` |

### parse_job_detail

```python
from datetime import datetime
from scrapling.parser import Adaptor

def parse_job_detail(self, detail_html: str, url: str) -> dict:
    page = Adaptor(detail_html)

    def _label(label):
        t = page.xpath(
            f"//*[contains(text(),'{label}')]/following-sibling::*[1]//text()"
        ).get()
        return t.strip() if t else None

    def _h2_para(heading):
        parts = page.xpath(
            f'//h2[contains(normalize-space(.), "{heading}")]/following-sibling::*[1]//text()'
        ).getall()
        return " ".join(p.strip() for p in parts if p.strip()) or None

    # Salary  tìm theo icon
    salary = None
    container = page.xpath(
        '//div[contains(@class,"attr-item") and .//i[contains(@class,"la-money")]]'
    )
    if container:
        v = container[0].css('div[class*="value"] ::text').get()
        salary = v.strip() if v else None

    # Experience  selector riêng
    exp = page.xpath(
        '//div[contains(.,"Kinh nghiệm yêu cầu")]/following-sibling::div[1]//text()'
    ).get()

    return {
        "title":            page.css("[class*='job-title'] ::text").get(),
        "company":          page.css("[class*='company-name'] ::text").get(),
        "salary":           salary,
        "location":         _label("Khu vực"),
        "job_type":         _label("Hình thức làm việc"),
        "experience_level": exp.strip() if exp else None,
        "education_level":  _label("Trình độ yêu cầu"),
        "job_industry":     _label("Ngành nghề"),
        "job_position":     _label("Cấp bậc"),
        "job_deadline":     _label("Hạn nộp"),
        "job_description":  _h2_para("Mô tả công việc"),
        "requirements":     _h2_para("Yêu cầu"),
        "benefits":         _h2_para("Quyền lợi"),
        "job_url":          url,
        "source":           self.source_name,
        "scraped_at":       datetime.now().isoformat(),
    }
```

---

## 8. Joboko (`vn.joboko.com`)

| | |
|---|---|
| `source_name` | `"joboko"` |
| `base_url` | `https://vn.joboko.com` |
| Fetcher | `StealthyFetcher` |
| `batch_size` | `15` |

### URL & Pagination

```python
from urllib.parse import quote_plus

list_url = f"https://vn.joboko.com/jobs?q={quote_plus(keyword)}&p={page_num}"
```

### Phase 1  extract_job_urls

```python
page = Adaptor(list_page_html)
return page.css('div.nw-job-list__list a[href*="viec-lam"]::attr(href)').getall()
```

### Phase 3  Selectors

| Trường | Selector / Label |
|---|---|
| `title` | CSS `[class*="nw-company-hero__title"] ::text` |
| `company` | CSS `[class*="nw-company-hero__text"] ::text` |
| `salary` | XPath text-node label `"Thu nhập"` |
| `location` | XPath `"Địa điểm làm việc"`  fallback CSS `span.fz-13.fw-medium.letter-spacing-1.c-text-2` |
| `job_type` | XPath `"Loại hình"` |
| `experience_level` | XPath `"Kinh nghiệm"` |
| `job_position` | XPath `"Chức vụ"` |
| `job_deadline` | CSS `[class*="mt-1 fz-16"] ::text`  regex `\d{1,2}/\d{1,2}/\d{4}` |
| `job_description` | XPath `"Mô tả công việc"`  fallback CSS `div[class="text-left job-desc-full"]` |
| `requirements` | XPath `"Yêu cầu"` |
| `benefits` | XPath `"Quyền lợi"` |
| `education_level`, `job_industry` | `None` |

### parse_job_detail

```python
import re
from datetime import datetime
from scrapling.parser import Adaptor

def parse_job_detail(self, detail_html: str, url: str) -> dict:
    page = Adaptor(detail_html)

    def _all(selector):
        parts = page.css(f'[class*="{selector}"] ::text').getall()
        return " ".join(p.strip() for p in parts if p.strip()) or None

    def _label(label):
        t = page.xpath(
            f'//text()[contains(.,"{label}")]/following-sibling::*/text()'
        ).get()
        return t.strip() if t else None

    def _para(label):
        parts = page.xpath(
            f'//*[contains(normalize-space(),"{label}")]/following-sibling::*[1]//text()'
        ).getall()
        return " ".join(p.strip() for p in parts if p.strip()) or None

    # Deadline
    deadline = None
    dl_text = page.css('[class*="mt-1 fz-16"] ::text').get()
    if dl_text:
        m = re.search(r"\d{1,2}/\d{1,2}/\d{4}", dl_text)
        deadline = m.group() if m else None

    # Description + fallback
    description = _para("Mô tả công việc")
    if not description:
        parts = page.css('div[class="text-left job-desc-full"] ::text').getall()
        description = " ".join(p.strip() for p in parts if p.strip()) or None

    # Location + fallback
    location = _label("Địa điểm làm việc")
    if not location:
        location = page.css("span.fz-13.fw-medium.letter-spacing-1.c-text-2::text").get()

    return {
        "title":            _all("nw-company-hero__title"),
        "company":          _all("nw-company-hero__text"),
        "salary":           _label("Thu nhập"),
        "location":         location,
        "job_type":         _label("Loại hình"),
        "experience_level": _label("Kinh nghiệm"),
        "education_level":  None,
        "job_industry":     None,
        "job_position":     _label("Chức vụ"),
        "job_deadline":     deadline,
        "job_description":  description,
        "requirements":     _para("Yêu cầu"),
        "benefits":         _para("Quyền lợi"),
        "job_url":          url,
        "source":           self.source_name,
        "scraped_at":       datetime.now().isoformat(),
    }
```

---

## 9. TopCV (`topcv.vn`)

| | |
|---|---|
| `source_name` | `"topcv"` |
| `base_url` | `https://www.topcv.vn` |
| Fetcher | `StealthyFetcher` |
| `batch_size` | `10` |
| `delay_range` | `(4, 8)` |
| `max_retries` | `6` |

> TopCV có 2 dạng trang detail  regular (`/viec-lam/`) và brand (`/brand/`)  cấu trúc HTML khác nhau. Phân biệt bằng `"brand" in url`.
> Regular pages nhúng dữ liệu vào `window.qgTracking` JS object  ưu tiên extract từ JS, fallback sang HTML.

### URL & Pagination

```python
list_url  = f"https://www.topcv.vn/tim-viec-lam-{'-'.join(keyword.lower().split())}"
next_page = page.css('a[data-href*="?page="]::attr(data-href)').get()
# TopCV dùng data-href (không phải href) cho pagination
```

### Phase 1  extract_job_urls

```python
page = Adaptor(list_page_html)
return page.css(
    'a[href*="/viec-lam/"]::attr(href), '
    'a[href*="/brand/"][href*="tuyen-dung"]::attr(href)'
).getall()
```

### Phase 3  parse_job_detail

```python
import re
from datetime import datetime, timedelta
from scrapling.parser import Adaptor

def parse_job_detail(self, detail_html: str, url: str) -> dict:
    page = Adaptor(detail_html)
    is_brand = "brand" in url

    def _from_js(field):
        js = page.xpath('//script[contains(text(),"window.qgTracking")]/text()').get()
        if not js:
            return None
        m = re.search(rf'"{field}"\s*:\s*"([^"]*)"', js)
        if not m:
            return None
        v = m.group(1)
        try:
            v = v.encode().decode("unicode_escape") if "\\" in v else v
        except Exception:
            pass
        return v.replace("\\", "").strip() or None

    def _label_regular(label):
        parts = page.xpath(
            f'//*[contains(text(),"{label}") and contains(@class,"box-general-group-info-title")]'
            f'/following-sibling::*[position()<=2]//text()'
        ).getall()
        return " ".join(p.strip() for p in parts if p.strip()) or None

    def _label_any(label):
        parts = page.xpath(
            f'//*[contains(text(),"{label}")]/following-sibling::*[position()<=2]//text()'
        ).getall()
        return " ".join(p.strip() for p in parts if p.strip()) or None

    def _para(heading):
        parts = page.xpath(
            f'//*[contains(text(),"{heading}")]/following-sibling::div[position()<=2]//text()'
        ).getall()
        return " ".join(p.strip() for p in parts if p.strip()) or None

    if is_brand:
        title = " ".join(
            t.strip() for t in page.css('h2[class*="title"] ::text').getall() if t.strip()
        ) or None
    else:
        title = _from_js("job_title") or " ".join(
            t.strip() for t in page.css("h1.box-header-job__title ::text").getall() if t.strip()
        ) or None

    if is_brand:
        company = (
            page.css('div[class="footer-info-content footer-info-company-name"]::text').get()
            or page.css('h1[class="company-content__title--name"]::text').get()
        )
        company = company.strip() if company else None
    else:
        company = _from_js("recruiter_company") or " ".join(
            t.strip() for t in page.css("div.box-job-info a.text-dark-blue ::text").getall() if t.strip()
        ) or None

    salary_raw = (
        _label_any("Mức lương") or _label_any("Thu nhập")
        if is_brand
        else _from_js("salary_range") or page.css("h4.box-header-job__salary::text").get()
    )
    salary = salary_raw.strip() if salary_raw else None

    if is_brand:
        location = _label_any("Địa điểm")
    else:
        loc_raw = _from_js("work_location") or " ".join(
            t.strip() for t in page.css("span.hight-light.city-name ::text").getall() if t.strip()
        )
        location = loc_raw.replace("Địa điểm:", "").strip() if loc_raw else None

    if is_brand:
        deadline = None
        for txt in page.css('span[class="deadline"] ::text').getall():
            m = re.search(r"\d+", txt)
            if m:
                deadline = (datetime.now() + timedelta(days=int(m.group()))).strftime("%d/%m/%Y")
                break
        deadline = deadline or _label_any("Hạn nộp hồ sơ")
    else:
        deadline = page.css('div[class="job-detail__info--deadline-date"]::text').get()

    _label = _label_any if is_brand else _label_regular

    return {
        "title":            title,
        "company":          company,
        "salary":           salary,
        "location":         location,
        "job_type":         _label("Hình thức làm việc"),
        "experience_level": _from_js("experience") if not is_brand else _label_any("Kinh nghiệm"),
        "education_level":  _label("Học vấn"),
        "job_industry":     _from_js("job_category") if not is_brand else _label_any("Ngành nghề"),
        "job_position":     _label("Cấp bậc"),
        "job_deadline":     deadline,
        "job_description":  _para("Mô tả công việc"),
        "requirements":     _para("Yêu cầu ứng viên"),
        "benefits":         _para("Quyền lợi"),
        "job_url":          url,
        "source":           self.source_name,
        "scraped_at":       datetime.now().isoformat(),
    }
```

---

## 10. LinkedIn (`linkedin.com`)

| | |
|---|---|
| `source_name` | `"linkedin"` |
| `base_url` | `https://www.linkedin.com` |
| Fetcher | `PlaywrightFetcher` (`stealth=True`) |
| `batch_size` | `3` |

> LinkedIn yêu cầu đăng nhập. Thay vì Selenium click từng card, Scrapling **fetch trực tiếp URL detail** sau khi collect URL.

### Cookie Management (chạy 1 lần thủ công)

```python
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

COOKIE_FILE = Path("data/raw/linkedin_cookies.json")

def login_and_save_cookies(username: str, password: str):
    """Chạy headless=False để xử lý CAPTCHA/challenge nếu xuất hiện."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://www.linkedin.com/login")
        page.fill("#username", username)
        page.fill("#password", password)
        page.click("button[type='submit']")
        page.wait_for_url("**/feed/**", timeout=30_000)
        COOKIE_FILE.write_text(json.dumps(browser.contexts[0].cookies()))
        browser.close()

def load_cookies() -> list[dict]:
    return json.loads(COOKIE_FILE.read_text()) if COOKIE_FILE.exists() else []
```

### URL & Pagination

```python
from urllib.parse import urlencode

params   = {"keywords": keyword, "location": "Vietnam"}
list_url = f"https://www.linkedin.com/jobs/search?{urlencode(params)}"
# Phân trang: &start=0, &start=25, &start=50 ...
page_url = f"{list_url}&start={page_index * 25}"
```

### Phase 1  extract_job_urls

> `collect_urls()` trong `BaseScraper` phải truyền `extra_cookies=load_cookies()` vào `PlaywrightFetcher`.

```python
page = Adaptor(list_page_html)
raw = page.css("a[href*='/jobs/view/']::attr(href)").getall()
return list({
    re.sub(r'\?.*$', '', href)
    for href in raw
    if '/jobs/view/' in href
})
```

### Phase 3  Selectors

| Trường | Selector |
|---|---|
| `title` | `h1[class*="t-24 t-bold inline"]::text` |
| `company` | `div[class*="job-details-jobs-unified-top-card__company-name"] ::text` |
| `location` | `span[dir="ltr"] span.tvm__text.tvm__text--low-emphasis::text` |
| `job_description` | `div.mt4 p[dir="ltr"] ::text` |
| `job_industry` | `div.t-14.mt5 ::text`  lọc (xem parse_job_detail) |
| Các trường còn lại | `None` |

### parse_job_detail

```python
import re
from datetime import datetime
from scrapling.parser import Adaptor

def parse_job_detail(self, detail_html: str, url: str) -> dict:
    page = Adaptor(detail_html)

    def _join(selector):
        parts = page.css(f"{selector} ::text").getall()
        return " ".join(p.strip() for p in parts if p.strip()) or None

    # Industry  bỏ qua phần mô tả quy mô công ty
    industry = None
    for part in page.css("div.t-14.mt5 ::text").getall():
        p = part.strip()
        if not p:
            continue
        if any(k in p.lower() for k in ["employees", "on linkedin", "followers", "connections"]):
            continue
        if not re.search(r'\d{2,}', p):
            industry = p
            break

    return {
        "title":            page.css("h1[class*='t-24 t-bold inline']::text").get(),
        "company":          _join("div[class*='job-details-jobs-unified-top-card__company-name']"),
        "salary":           None,
        "location":         page.css("span[dir='ltr'] span.tvm__text.tvm__text--low-emphasis::text").get(),
        "job_type":         None,
        "experience_level": None,
        "education_level":  None,
        "job_industry":     industry,
        "job_position":     None,
        "job_deadline":     None,
        "job_description":  _join("div.mt4 p[dir='ltr']"),
        "requirements":     None,
        "benefits":         None,
        "job_url":          url,
        "source":           self.source_name,
        "scraped_at":       datetime.now().isoformat(),
    }
```

---

## 11. Bảng tổng hợp

| Portal | `source_name` | Fetcher | `batch_size` | Phase 1 Selector |
|---|---|---|---|---|
| CareerLink | `careerlink` | `StealthyFetcher` | 10 | `a[class*="job-link"][href*="tim-viec-lam"]` |
| CareerViet | `careerviet` | `StealthyFetcher` | 10 | `a[href*="/tim-viec-lam/"]` |
| ITViec | `itviec` | `StealthyFetcher` | 15 | `h3[data-url*='/it-jobs/']::attr(data-url)` |
| 123job | `job_123` | `StealthyFetcher` | 10 | `a[href*="/viec-lam/"]` |
| Joboko | `joboko` | `StealthyFetcher` | 15 | `div.nw-job-list__list a[href*="viec-lam"]` |
| TopCV | `topcv` | `StealthyFetcher` | 10 | `a[href*="/viec-lam/"]` + brand URLs |
| VietnamWorks | `vietnamworks` | REST API | N/A | REST JSON endpoint |
| JobsGO | `jobsgo` | `StealthyFetcher` | 15 | TBD |
| Ybox | `ybox` | `StealthyFetcher` | 15 | TBD |
| JobStreet | `jobstreet` | `PlaywrightFetcher` | 5 | JS rendered |
| LinkedIn | `linkedin` | `PlaywrightFetcher` | 3 | `a[href*='/jobs/view/']` |

---

## 12. Các lưu ý quan trọng

| Tình huống | Cách xử lý |
|---|---|
| Selector trả về `None` | Luôn guard: `t.strip() if t else None` |
| URL relative | `urljoin(base_url, path)` trước khi return |
| Deadline dạng "còn N ngày" | `datetime.now() + timedelta(days=N)`  format `%Y-%m-%d` |
| HTTP 429 (TopCV) | `delay_range=(4,8)`, `max_retries=6`  BaseScraper đã có exponential backoff |
| LinkedIn / JobStreet JS-heavy | Bắt buộc `PlaywrightFetcher`  `StealthyFetcher` nhận HTML chưa render |
| Cookie LinkedIn hết hạn | Chạy lại `login_and_save_cookies()`, cookies thường hết hạn sau vài tuần |
| `getall()` trả về text node rỗng | Filter: `[p.strip() for p in parts if p.strip()]` |
