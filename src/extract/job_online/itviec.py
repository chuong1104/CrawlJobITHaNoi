import json
import os
import random
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from scrapling.parser import Adaptor

from src.extract.job_online.base_scraper import BaseScraper


class ITViecScraper(BaseScraper):

    _block_media = BaseScraper._block_media
    source_name = "itviec"
    base_url = "https://itviec.com"
    batch_size = 10

    # URL list theo khu vực Hà Nội
    DEFAULT_START_URL = "https://itviec.com/it-jobs/ha-noi"

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------
    def __init__(self, start_url: str | None = None, **kwargs) -> None:
        # Sử dụng curl_cffi, không dùng Playwright để bypass Cloudflare mượt hơn
        kwargs["use_playwright"] = False
        super().__init__(**kwargs)
        self.start_url = self._clean_list_url(start_url or self.DEFAULT_START_URL)

        # Thông tin đăng nhập từ .env
        self.email = os.getenv("ITVIEC_EMAIL")
        self.password = os.getenv("ITVIEC_PASSWORD")

        # File lưu session cookies để tái sử dụng
        self.session_file = Path("itviec_session.json")

        # Khởi tạo persistent session với curl_cffi
        from curl_cffi import requests
        proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
        self.session = requests.Session(impersonate="chrome110", proxies=proxies)

        # Thử load cookie từ file
        if self.session_file.exists():
            try:
                with open(self.session_file, "r") as f:
                    cookies = json.load(f)
                    if isinstance(cookies, dict):
                        for k, v in cookies.items():
                            self.session.cookies.set(k, v)
                    elif isinstance(cookies, list):
                        for c in cookies:
                            self.session.cookies.set(c["name"], c["value"], domain=c.get("domain"))
            except Exception as e:
                self.logger.warning(f"Lỗi load session: {e}")

    # ------------------------------------------------------------------
    # URL Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _clean_list_url(url: str) -> str:
        """Bỏ query tracking để có list URL ổn định."""
        parsed = urlparse(url)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

    @staticmethod
    def _drop_tracking_query(url: str) -> str:
        """Loại bỏ query tracking, chỉ giữ lại key 'page'."""
        parsed = urlparse(url)
        query = parse_qs(parsed.query, keep_blank_values=True)

        keep_keys = {"page"}
        filtered = {
            key: value
            for key, value in query.items()
            if key in keep_keys and value and value[0] != ""
        }

        new_query = urlencode(filtered, doseq=True)
        return urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, "")
        )

    def _canonicalize_job_url(self, url: str) -> str:
        """
        Đưa URL về dạng canonical:
        - relative -> absolute
        - bỏ query tracking (lab_feature, click_source, job_selected...)
        - đổi /it-jobs/<slug>/content?... -> /it-jobs/<slug>
        """
        full_url = urljoin(self.base_url, (url or "").strip())
        full_url = self._drop_tracking_query(full_url)

        parsed = urlparse(full_url)
        path = parsed.path
        if path.endswith("/content"):
            path = path[: -len("/content")]

        return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------
    def get_list_page_url(self, page_num: int) -> str:
        if page_num <= 1:
            return self.start_url
        return f"{self.start_url}?page={page_num}"

    def get_next_page_url(
        self,
        list_page_html: str,
        page_num: int,
        current_url: str,
    ) -> str | None:
        page = Adaptor(list_page_html)
        next_href = page.css("div.page.next a[rel='next']::attr(href)").get() or page.css(
            "a[rel='next']::attr(href)"
        ).get()
        if next_href:
            return urljoin(self.base_url, next_href)
        return self.get_list_page_url(page_num + 1)

    # ------------------------------------------------------------------
    # Phase 1: Extract job URLs from list page
    # ------------------------------------------------------------------
    def extract_job_urls(self, list_page_html: str) -> list[str]:
        page = Adaptor(list_page_html)

        candidate_urls: list[str] = []

        # Ưu tiên attr trên card list
        candidate_urls.extend(
            page.css("div.job-card::attr(data-search--job-selection-job-url-value)").getall()
        )

        # Fallback từ data-url trong title h3
        candidate_urls.extend(page.css("h3[data-url]::attr(data-url)").getall())

        # Fallback từ anchor detail trong selected preview panel
        candidate_urls.extend(
            page.css(
                "a[data-controller='utm-tracking'][target='_blank'][href*='/it-jobs/']::attr(href)"
            ).getall()
        )

        links: list[str] = []
        seen: set[str] = set()

        for raw in candidate_urls:
            if not raw:
                continue
            canonical = self._canonicalize_job_url(raw)
            if "/it-jobs/" not in canonical:
                continue
            if canonical not in seen:
                seen.add(canonical)
                links.append(canonical)

        return links

    # ------------------------------------------------------------------
    # Fetcher Override (để dùng chung session giữ cookies)
    # ------------------------------------------------------------------
    def _fetch_html(self, url: str) -> str | None:
        """Sử dụng persistent session của curl_cffi để gửi cookie."""
        for attempt in range(1, self.max_retries + 1):
            try:
                r = self.session.get(url)
                if r.status_code == 200:
                    return r.text
                wait = self._backoff(attempt)
                self.logger.warning(f"Status {r.status_code} [{url}] attempt {attempt}/{self.max_retries}")
                time.sleep(wait)
            except Exception as exc:
                wait = self._backoff(attempt)
                self.logger.warning(f"Error fetching [{url}]: {exc!r}")
                if attempt < self.max_retries:
                    time.sleep(wait)
        self.logger.error(f"Giving up on [{url}] sau {self.max_retries} attempts.")
        return None

    # ------------------------------------------------------------------
    # curl_cffi Login
    # ------------------------------------------------------------------
    def _perform_login(self) -> bool:
        """Đăng nhập bằng HTTP request (curl_cffi) qua mặt Cloudflare."""
        if not self.email or not self.password:
            self.logger.warning(
                "Không tìm thấy ITVIEC_EMAIL / ITVIEC_PASSWORD trong .env. "
                "Cào không cần đăng nhập (lương có thể bị ẩn)."
            )
            return False

        # Kiểm tra session cũ xem còn hiệu lực không
        try:
            r = self.session.get("https://itviec.com/profile")
            if r.status_code == 200 and "sign_in" not in r.url:
                self.logger.info("Sử dụng session cũ thành công!")
                return True
        except Exception:
            pass

        self.logger.info("Đang đăng nhập ITViec bằng curl_cffi...")
        try:
            from bs4 import BeautifulSoup
            r_get = self.session.get("https://itviec.com/sign_in")
            soup = BeautifulSoup(r_get.text, 'html.parser')
            csrf_token = soup.find('meta', {'name': 'csrf-token'})
            
            if not csrf_token:
                self.logger.error("Không tìm thấy CSRF token trên trang đăng nhập.")
                return False
                
            data = {
                "authenticity_token": csrf_token['content'],
                "user[email]": self.email,
                "user[password]": self.password,
                "commit": "Sign In"
            }
            
            r_post = self.session.post("https://itviec.com/sign_in", data=data, allow_redirects=False)
            
            if r_post.status_code == 302 and r_post.headers.get("Location"):
                self.logger.info("Đăng nhập ITViec thành công!")
                with open(self.session_file, "w") as f:
                    json.dump(self.session.cookies.get_dict(), f)
                return True
            else:
                self.logger.error(f"Đăng nhập thất bại (Status: {r_post.status_code}).")
                return False

        except Exception as e:
            self.logger.error(f"Lỗi khi đăng nhập ITViec: {e}")
            return False

    # ------------------------------------------------------------------
    # Override _collect_urls để gọi login trước
    # ------------------------------------------------------------------
    def _collect_urls(self, pages: int | None = None) -> list[str]:
        # Thực hiện login trước khi collect urls
        self._perform_login()
        # Delegate cho base class thu thập URL (sẽ gọi _fetch_html của mình)
        return super()._collect_urls(pages)

    # ------------------------------------------------------------------
    # Helpers cho parse
    # ------------------------------------------------------------------
    @staticmethod
    def _join_text(page: Adaptor, selector: str) -> str | None:
        """Ghép tất cả text node bên trong selector thành string."""
        parts = page.css(f"{selector} ::text").getall()
        text = " ".join(p.strip() for p in parts if p and p.strip())
        return text or None

    @staticmethod
    def _inner_lines(page: Adaptor, selector: str) -> str | None:
        """Lấy nội dung text của block, giữ xuống dòng giữa các phần tử."""
        el = page.css(selector)
        if not el:
            return None
        parts = el.css("::text").getall()
        lines = [p.strip() for p in parts if p and p.strip()]
        return "\n".join(lines) or None

    # ------------------------------------------------------------------
    # Phase 3: Parse job detail
    # ------------------------------------------------------------------
    def parse_job_detail(self, detail_html: str, url: str) -> dict:
        page = Adaptor(detail_html)

        # ── Tên job ─────────────────────────────────────────────────────
        title = page.css("h1.ipt-xl-6.text-it-black::text").get()
        if not title:
            title = page.css("h1[class*='text-it-black']::text").get()
        if title:
            title = title.strip()

        # ── Tên công ty ─────────────────────────────────────────────────
        company = page.css("div.employer-name::text").get()
        if not company:
            # Fallback: link công ty
            company = page.css("a[href*='/companies/'][class*='text-it-black']::text").get()
        if company:
            company = company.strip()

        # ── Lương ───────────────────────────────────────────────────────
        salary_raw = page.css("span.ips-2.fw-500::text").get()
        if salary_raw:
            salary_raw = salary_raw.strip()
            if "sign in" in salary_raw.lower() or "đăng nhập" in salary_raw.lower():
                salary = None
            else:
                salary = salary_raw
        else:
            # Fallback: tìm span chứa USD/VND hoặc pattern lương
            for span in page.css("span::text").getall():
                span = span.strip()
                if re.search(r"(USD|VNĐ|VND|triệu|million|\d[\d,.]+\s*-)", span, re.IGNORECASE):
                    salary = span
                    break
            else:
                salary = None

        # ── Địa chỉ ─────────────────────────────────────────────────────
        # <span class="normal-text text-rich-grey"> bên trong div.d-inline-block.text-dark-grey
        location_el = page.css("div.d-inline-block.text-dark-grey span.normal-text.text-rich-grey")
        if location_el:
            location = location_el.css("::text").get()
            if location:
                location = location.strip()
        else:
            location = None

        # ── Kinh nghiệm / Experience level ──────────────────────────────
        # Trích từ phần "Your skills and experience" h2 block
        experience_level = None
        for block in page.css("div.imy-5.paragraph"):
            heading = block.css("h2::text").get() or ""
            if "skill" in heading.lower() or "experience" in heading.lower():
                texts = block.css("::text").getall()
                for t in texts:
                    t = t.strip()
                    # Tìm dòng nói về năm kinh nghiệm
                    m = re.search(r"(\d+\+?\s*năm|\d+\+?\s*year)", t, re.IGNORECASE)
                    if m:
                        experience_level = t
                        break
                break

        # ── Hạn ứng tuyển / Posted time ─────────────────────────────────
        deadline = None
        for span in page.css("span.normal-text.text-rich-grey"):
            text = " ".join((span.css("::text").getall() or [])).strip()
            if "posted" in text.lower() or "ago" in text.lower():
                deadline = re.sub(r"\s+", " ", text).strip()
                break

        # ── Mô tả công việc ─────────────────────────────────────────────
        job_description = None
        for block in page.css("div.imy-5.paragraph"):
            heading = block.css("h2::text").get() or ""
            if "job description" in heading.lower() or "mô tả" in heading.lower():
                parts = block.css("::text").getall()
                lines = [p.strip() for p in parts if p and p.strip()]
                # Bỏ dòng tiêu đề
                lines = [l for l in lines if l.lower() not in ("job description", "mô tả công việc")]
                job_description = "\n".join(lines) or None
                break

        # ── Phúc lợi ────────────────────────────────────────────────────
        benefits = None
        for block in page.css("div.imy-5.paragraph"):
            heading = block.css("h2::text").get() or ""
            if "love working" in heading.lower() or "phúc lợi" in heading.lower() or "why you" in heading.lower():
                parts = block.css("::text").getall()
                lines = [p.strip() for p in parts if p and p.strip()]
                lines = [l for l in lines if l.lower() not in ("why you'll love working here",)]
                benefits = "\n".join(lines) or None
                break

        # ── Kỹ năng / Yêu cầu ───────────────────────────────────────────
        requirements = None
        for block in page.css("div.imy-5.paragraph"):
            heading = block.css("h2::text").get() or ""
            if "skill" in heading.lower() or "experience" in heading.lower() or "yêu cầu" in heading.lower():
                parts = block.css("::text").getall()
                lines = [p.strip() for p in parts if p and p.strip()]
                lines = [l for l in lines if l.lower() not in ("your skills and experience", "yêu cầu công việc")]
                requirements = "\n".join(lines) or None
                break

        # ── Loại công việc ───────────────────────────────────────────────
        # <span class="normal-text text-rich-grey ms-1">At office</span>
        job_type = None
        for div in page.css("div.d-flex.align-items-center"):
            span = div.css("span.normal-text.text-rich-grey.ms-1::text").get()
            if span and span.strip():
                job_type = span.strip()
                break

        # ── Cấp bậc / Job position ───────────────────────────────────────
        # ITViec không hiển thị cấp bậc riêng, để None
        job_position = None

        # ── Ngành nghề / Job industry ────────────────────────────────────
        # <a ... href="/it-jobs/data-engineer">Data Engineer</a> trong Job Expertise
        job_industry = None
        for row in page.css("div.imb-4.imb-xl-3.d-flex"):
            label_el = row.css("div.fw-600.text-rich-grey::text").get() or ""
            if "expertise" in label_el.lower() or "industry" in label_el.lower() or "ngành" in label_el.lower():
                tags = row.css("a.itag::text").getall()
                if tags:
                    job_industry = ", ".join(t.strip() for t in tags if t.strip())
                break

        # ── Thông tin công ty ─────────────────────────────────────────────
        company_info = self._inner_lines(page, "div.paragraph.ipt-4.text-break")
        if not company_info:
            company_info = self._join_text(page, "div[class*='company-description']")

        # ── Website công ty ───────────────────────────────────────────────
        company_website = None
        # data-redirect-url-url-value attribute trên div
        for el in page.css("div[data-redirect-url-url-value]"):
            url_val = el.css("::attr(data-redirect-url-url-value)").get()
            if url_val and url_val.startswith("http"):
                company_website = url_val.strip()
                break
        # Fallback: anchor trong khu vực thông tin công ty
        if not company_website:
            for a in page.css("a[href*='http'][target='_blank']"):
                href = a.css("::attr(href)").get() or ""
                if href and "itviec.com" not in href and "google.com" not in href:
                    company_website = href.strip()
                    break

        return {
            "title": title,
            "company": company,
            "salary": salary,
            "location": location,
            "experience_level": experience_level,
            "job_type": job_type,
            "job_industry": job_industry,
            "job_position": job_position,
            "job_description": job_description,
            "requirements": requirements,
            "benefits": benefits,
            "job_deadline": deadline,
            "company_info": company_info,
            "company_website": company_website,
            "job_url": self._canonicalize_job_url(url),
            "source": self.source_name,
            "scraped_at": datetime.now().isoformat(),
        }


if __name__ == "__main__":
    scraper = ITViecScraper()
    links = scraper.run_links_only()
    print(f"Total dedup links: {len(links)}")
