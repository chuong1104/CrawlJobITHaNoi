import os
import random
import re
import time
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urljoin, urlparse, urlunparse

from scrapling.parser import Adaptor

from src.extract.job_online.base_scraper import BaseScraper


class VietnamWorksScraper(BaseScraper):
    source_name = "vietnamworks"
    base_url = "https://www.vietnamworks.com"
    batch_size = 10

    # l=24 là bộ lọc Hà Nội — KHÔNG strip query string
    DEFAULT_START_URL = "https://www.vietnamworks.com/viec-lam?q=data&l=24"
    MAX_SCROLLS = 100
    SCROLL_PAUSE = (1.5, 3.0)

    def __init__(self, start_url: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        # Giữ nguyên query string (l=24) — không split("?")
        self.start_url = start_url or self.DEFAULT_START_URL

    def get_list_page_url(self, page_num: int) -> str:
        return self.start_url

    def get_next_page_url(
        self, list_page_html: str, page_num: int, current_url: str
    ) -> str | None:
        return None  # Infinite scroll — không có next page URL

    def extract_job_urls(self, list_page_html: str) -> list[str]:
        """
        Extract job URLs using multiple robust selectors, inspired by Selenium/Scrapy logic.
        """
        page = Adaptor(list_page_html)
        selectors = [
            "div.sc-cdaca-d h2 a::attr(href)",
            "a[href*='-jv']::attr(href)",
            "a[href*='-jv?']::attr(href)",
            "a[href*='viec-lam-']::attr(href)",
        ]
        hrefs = []
        for sel in selectors:
            hrefs.extend(page.css(sel).getall())
        # Remove duplicates
        hrefs = list(set(hrefs))
        links: list[str] = []
        seen: set[str] = set()
        for href in hrefs:
            if not href:
                continue
            full_url = urljoin(self.base_url, href).split("#")[0]
            # Chỉ lấy URL job detail (kết thúc bằng -jv hoặc -jv?...)
            if "-jv" not in full_url:
                continue
            if full_url not in seen:
                seen.add(full_url)
                links.append(full_url)
        return links

    # ------------------------------------------------------------------
    # Các selector tìm nút "trang kế tiếp" trên VietnamWorks
    # ------------------------------------------------------------------
    _NEXT_PAGE_SELECTORS = [
        "a[aria-label='Next page']",
        "a[aria-label='Next']",
        "a[aria-label='next']",
        "a[rel='next']",
        "li.next a",
        "a.next",
        "[class*='pagination'] a[class*='next' i]",
        "[class*='Pagination'] a[class*='next' i]",
        "ul.pagination li.btn-default button",  # Selenium XPATH fallback
    ]

    def _find_next_page_url(self, pw_page) -> str | None:
        """
        Tìm URL trang kế tiếp:
        1. Ưu tiên các selector cũ (a[rel=next], ...)
        2. Nếu không có, tìm <button> có text '>' trong .pagination
        3. Nếu có, tự build next_url dạng ?page=N+1
        """
        # 1. Thử các selector cũ
        for sel in self._NEXT_PAGE_SELECTORS:
            el = pw_page.query_selector(sel)
            if el:
                href = el.get_attribute("href")
                if href:
                    return urljoin(self.base_url, href)

        # 2. Tìm <button> next trong .pagination
        btns = pw_page.query_selector_all("ul.pagination button")
        for btn in btns:
            text = btn.inner_text().strip()
            if text == ">":
                # 3. Build next_url dạng ?page=N+1
                # Lấy current page từ button.active
                active_btn = pw_page.query_selector("ul.pagination li.active button")
                if active_btn:
                    try:
                        current_page = int(active_btn.inner_text().strip())
                        next_page = current_page + 1
                        # Build next_url
                        # Nếu self.start_url đã có ?page=, thay thế, nếu chưa thì thêm
                        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
                        url = self.start_url
                        parsed = urlparse(url)
                        qs = parse_qs(parsed.query)
                        qs["page"] = [str(next_page)]
                        new_query = urlencode(qs, doseq=True)
                        next_url = urlunparse(parsed._replace(query=new_query))
                        return next_url
                    except Exception:
                        pass
        return None

    def _collect_urls(self, pages: Optional[int] = None) -> list[str]:
        """
        VietnamWorks: cuộn dần từng bước + pagination fallback.
        - Scroll từng 800px, đợi lazy load, thu URL mới.
        - Khi đến đáy: đợi 4s, nếu chiều cao không tăng sau 3 lần → hết trang.
        - Sau khi hết trang: tìm nút "Next page" và chuyển sang trang kế.
        """
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

        all_urls: list[str] = []
        seen_urls: set[str] = set()
        max_pages = pages  # None = tự động dừng khi hết data

        # Use BaseScraper._block_media for resource blocking
        _block_media = BaseScraper._block_media

        def _scroll_page(pw_page, page_label: str) -> int:
            """Scroll đến đáy trang, thu URL, trả về số URL mới."""
            collected = 0
            scroll_step = 800      # px mỗi bước — scroll rộng hơn để tăng tốc
            current_pos = 0
            bottom_streak = 0       # đếm số lần đụng đáy mà chiều cao không tăng
            MAX_BOTTOM_STREAK = 5   # dừng sau 5 lần đáy "không có gì mới"
            no_new_links_streak = 0
            MAX_NO_NEW_LINKS_STREAK = 5

            for scroll_num in range(1, self.MAX_SCROLLS + 1):
                # Thu URL trước khi scroll
                before = len(all_urls)
                for u in self.extract_job_urls(pw_page.content()):
                    if u not in seen_urls:
                        seen_urls.add(u)
                        all_urls.append(u)
                new_count = len(all_urls) - before
                collected += new_count

                if new_count == 0:
                    no_new_links_streak += 1
                else:
                    no_new_links_streak = 0

                if no_new_links_streak >= MAX_NO_NEW_LINKS_STREAK:
                    self.logger.info(
                        f"[{page_label}] Không còn link mới sau {MAX_NO_NEW_LINKS_STREAK} lần scroll → dừng sớm"
                    )
                    break

                self.logger.info(
                    f"[{page_label} | Scroll {scroll_num}] "
                    f"Tổng: {len(all_urls)}, mới: {new_count}"
                )

                # Scroll một bước
                current_pos += scroll_step
                pw_page.evaluate(f"window.scrollTo(0, {current_pos})")
                time.sleep(random.uniform(0.8, 1.5))

                page_height = pw_page.evaluate("document.body.scrollHeight")

                if current_pos >= page_height:
                    # Đã đến đáy — scroll hẳn xuống đáy và đợi lazy load
                    pw_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    self.logger.info(f"[{page_label}] Đến đáy, đợi lazy load...")
                    time.sleep(4.0)

                    new_height = pw_page.evaluate("document.body.scrollHeight")
                    if new_height > page_height:
                        # Có thêm content → tiếp tục scroll
                        self.logger.info(
                            f"[{page_label}] Trang cao thêm ({page_height}→{new_height}px), tiếp tục"
                        )
                        bottom_streak = 0
                        # Không reset current_pos — tiếp tục từ đáy cũ
                    else:
                        bottom_streak += 1
                        self.logger.info(
                            f"[{page_label}] Đáy không tăng ({bottom_streak}/{MAX_BOTTOM_STREAK})"
                        )
                        if bottom_streak >= MAX_BOTTOM_STREAK:
                            self.logger.info(f"[{page_label}] Hết nội dung trang")
                            break
                        # Đợi thêm trước lần thử tiếp theo
                        time.sleep(2.0)

            return collected

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=False)
                ctx_opts = {
                    "viewport": {"width": 1280, "height": 900},
                    "user_agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0.0.0 Safari/537.36"
                    ),
                }
                if self.proxy:
                    ctx_opts["proxy"] = {"server": self.proxy}
                context = browser.new_context(**ctx_opts)
                pw_page = context.new_page()
                pw_page.route("**/*", _block_media)

                current_url = self.start_url
                page_num = 1

                while True:
                    if max_pages is not None and page_num > max_pages:
                        self.logger.info(f"[Phase 1] Đã đủ {max_pages} trang → dừng")
                        break

                    self.logger.info(f"[Phase 1] Trang {page_num} → {current_url}")
                    pw_page.goto(current_url, wait_until="domcontentloaded", timeout=45_000)

                    try:
                        pw_page.wait_for_selector("a[href*='-jv']", timeout=20_000)
                        self.logger.info(f"Job links đã render ✓ (trang {page_num})")
                    except PlaywrightTimeout:
                        self.logger.warning(f"Timeout chờ job links trang {page_num} — thử tiếp")
                        self.logger.debug(f"HTML snippet:\n{pw_page.content()[:2000]}")

                    collected = _scroll_page(pw_page, f"Trang {page_num}")

                    # Trang mới (page_num > 1) mà không có URL mới → đã hết data
                    if collected == 0 and page_num > 1:
                        self.logger.info("[Phase 1] Trang kế không có URL mới → dừng")
                        break

                    # Tìm nút next page
                    next_url = self._find_next_page_url(pw_page)
                    if not next_url:
                        self.logger.info("[Phase 1] Không tìm thấy trang kế → dừng")
                        break

                    current_url = next_url
                    page_num += 1
                    time.sleep(random.uniform(*self.SCROLL_PAUSE))

                browser.close()

        except Exception as exc:
            self.logger.error(f"[Phase 1] Lỗi: {exc!r}")

        self.logger.info(f"[Phase 1] Tổng thu thập: {len(all_urls)} URLs")
        return all_urls

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _get_block_text(page: Adaptor, selector: str) -> str | None:
        """Lấy toàn bộ inner text (multi-line) của một block."""
        el = page.css(selector)
        if not el:
            return None
        parts = el.css("::text").getall()
        lines = [p.strip() for p in parts if p and p.strip()]
        return "\n".join(lines) or None

    @staticmethod
    def _find_label_value(page: Adaptor, label_keyword: str) -> str | None:
        """
        VietnamWorks dùng pattern:
          <div class="sc-7bf5461f-2 ...">
            <label name="label" ...>LABEL TEXT</label>
            <p name="paragraph" ...>VALUE</p>
          </div>
        Tìm div chứa <label> có text khớp keyword, trả về text của <p> tiếp theo.
        """
        for div in page.css("div"):
            label_el = div.css("label[name='label']")
            if not label_el:
                continue
            label_text = (label_el.css("::text").get() or "").strip().lower()
            if label_keyword.lower() in label_text:
                p_el = div.css("p[name='paragraph']")
                if p_el:
                    parts = p_el.css("::text").getall()
                    val = " ".join(p.strip() for p in parts if p.strip())
                    return val or None
        return None

    @staticmethod
    def _parse_deadline(post_date_str: str | None, expire_text: str | None) -> str | None:
        """
        Tính hạn ứng tuyển = ngày đăng + số ngày hết hạn.
        post_date_str: "11/06/2026" (dd/MM/yyyy)
        expire_text:   "Hết hạn trong 19 ngày"
        """
        if not post_date_str:
            return expire_text  # fallback: trả về text gốc
        try:
            post_date = datetime.strptime(post_date_str.strip(), "%d/%m/%Y")
            if expire_text:
                match = re.search(r"(\d+)\s*ngày", expire_text, re.IGNORECASE)
                if match:
                    days = int(match.group(1))
                    deadline = post_date + timedelta(days=days)
                    return deadline.strftime("%d/%m/%Y")
        except Exception:
            pass
        return post_date_str  # fallback

    # ------------------------------------------------------------------
    # Phase 3: Parse job detail page
    # ------------------------------------------------------------------
    def parse_job_detail(self, detail_html: str, url: str) -> dict:
        page = Adaptor(detail_html)

        # ── Tên job ─────────────────────────────────────────────────────
        # <h1 name="title" ...>AI Engineer Intern</h1>
        title = None
        title_el = page.css("h1[name='title']")
        if title_el:
            title = title_el.css("::text").get()
            if title:
                title = title.strip() or None

        # ── Tên công ty ─────────────────────────────────────────────────
        # <a name="label" href="/nha-tuyen-dung/...">K&M Holdings</a>  (đứng gần h1)
        company = None
        for a in page.css("a[name='label'][href*='/nha-tuyen-dung/']"):
            val = a.css("::text").get()
            if val and val.strip():
                company = val.strip()
                break

        # ── Địa chỉ ─────────────────────────────────────────────────────
        # <p name="paragraph" ...>33 Mạc Thái Tổ, Yên Hòa, Cầu Giấy, Hà Nội</p>
        # nằm trong block có h2 "Địa điểm làm việc"
        location = None
        for section in page.css("div"):
            h2 = section.css("h2[name='title']")
            if h2 and "địa điểm" in (h2.css("::text").get() or "").lower():
                parts = section.css("p[name='paragraph']::text").getall()
                texts = [p.strip() for p in parts if p.strip()]
                location = " | ".join(texts) or None
                break

        # ── Lương ────────────────────────────────────────────────────────
        # <span name="label" color="#FF7D55" ...>Thương lượng</span>
        salary = None
        for span in page.css("span[name='label']"):
            parent = span.root.getparent() if hasattr(span, "root") else None
            val = span.css("::text").get()
            if val and val.strip():
                # Lương thường có màu cam (#FF7D55) hoặc nằm trong vùng salary
                color = span.attrib.get("color", "")
                if color == "#FF7D55" or "lương" in val.lower() or "thương lượng" in val.lower():
                    salary = val.strip()
                    break
        # Fallback: tìm span name=label đứng đầu tiên sau h1 title
        if not salary:
            for span in page.css("span[name='label']"):
                val = (span.css("::text").get() or "").strip()
                if val and val not in ("", "K&M Holdings"):
                    salary = val
                    break

        # ── Kinh nghiệm ─────────────────────────────────────────────────
        # <label name="label">SỐ NĂM KINH NGHIỆM TỐI THIỂU</label>
        # <p name="paragraph">Không yêu cầu</p>
        experience = self._find_label_value(page, "kinh nghiệm")

        # ── Loại hình làm việc ───────────────────────────────────────────
        # <label name="label">LOẠI HÌNH LÀM VIỆC</label>
        # <p name="paragraph">Thực tập</p>
        job_type = self._find_label_value(page, "loại hình làm việc")

        # ── Cấp bậc ─────────────────────────────────────────────────────
        # <label name="label">CẤP BẬC</label>
        # <p name="paragraph">Thực tập sinh/Sinh viên</p>
        job_position = self._find_label_value(page, "cấp bậc")

        # ── Ngành nghề ───────────────────────────────────────────────────
        # <label name="label">NGÀNH NGHỀ</label>
        # <p name="paragraph"><span>Công Nghệ...</span> > <span>Data Engineer...</span></p>
        job_industry = self._find_label_value(page, "ngành nghề")

        # ── Hạn ứng tuyển ────────────────────────────────────────────────
        # Ngày đăng: <label>NGÀY ĐĂNG</label> → <p>11/06/2026</p>
        # Hết hạn:   <span name="paragraph" ...>Hết hạn trong 19 ngày</span>
        post_date = self._find_label_value(page, "ngày đăng")
        expire_text = None
        for span in page.css("span[name='paragraph']"):
            val = (span.css("::text").get() or "").strip()
            if "hết hạn" in val.lower():
                expire_text = val
                break
        deadline = self._parse_deadline(post_date, expire_text)

        # ── Mô tả công việc ──────────────────────────────────────────────
        # <h2 class="...">Mô tả công việc</h2>
        # <div class="sc-1671001a-6 ..."><div><p>...</p></div></div>
        job_description = None
        for section in page.css("div"):
            h2 = section.css("h2")
            h2_text = (h2.css("::text").get() or "").strip().lower()
            if h2_text == "mô tả công việc":
                # Lấy div content ngay sau h2 (class chứa dVvinc hoặc tương tự)
                content_div = section.css("div > div > p")
                if content_div:
                    parts = section.css("p::text").getall()
                    lines = [p.strip() for p in parts if p.strip()]
                    job_description = "\n".join(lines) or None
                break

        # ── Kỹ năng / Yêu cầu công việc ─────────────────────────────────
        # <h2 class="...">Yêu cầu công việc</h2>
        # <div class="..."><div><p>...</p></div></div>
        requirements = None
        for section in page.css("div"):
            h2 = section.css("h2")
            h2_text = (h2.css("::text").get() or "").strip().lower()
            if h2_text == "yêu cầu công việc":
                parts = section.css("p::text").getall()
                lines = [p.strip() for p in parts if p.strip()]
                requirements = "\n".join(lines) or None
                break

        # ── Phúc lợi ────────────────────────────────────────────────────
        # Mỗi benefit item: <p name="title">Thưởng</p> + <div>KPI sản phẩm...</div>
        benefits_parts: list[str] = []
        for benefit_div in page.css("div[data-benefit-name]"):
            name_p = benefit_div.css("p[name='title']")
            benefit_name = (name_p.css("::text").get() or "").strip()
            # Lấy text mô tả benefit (div con cuối)
            desc_div = benefit_div.css("div div div")
            desc_texts = [t.strip() for t in desc_div.css("::text").getall() if t.strip()]
            desc = " ".join(desc_texts)
            if benefit_name and desc:
                benefits_parts.append(f"{benefit_name}: {desc}")
            elif benefit_name:
                benefits_parts.append(benefit_name)
        benefits = "\n".join(benefits_parts) if benefits_parts else None

        # ── Thông tin công ty & Website ──────────────────────────────────
        # Vào trang: <a name="label" href="/nha-tuyen-dung/...">K&M Holdings</a>
        company_info = None
        company_website = None

        employer_href = page.css("a[name='label'][href*='/nha-tuyen-dung/']::attr(href)").get()
        employer_url = None
        if employer_href:
            # Bỏ query param fromPage
            parsed = urlparse(urljoin(self.base_url, employer_href.strip()))
            employer_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

        if employer_url:
            self.logger.info(f"Fetching employer page: {employer_url}")
            comp_html = self._fetch_html(employer_url)
            if comp_html:
                comp_page = Adaptor(comp_html)

                # Thông tin công ty: <p name="paragraph" ...> hoặc <p class*='ePFWJD'>
                # Dùng name attribute vì class là generated
                for p_el in comp_page.css("p[name='paragraph']"):
                    val = p_el.css("::text").get() or ""
                    # Tìm đoạn dài nhất (mô tả công ty thường nhiều chữ)
                    if len(val.strip()) > 100:
                        parts = p_el.css("::text").getall()
                        lines = [p.strip() for p in parts if p.strip()]
                        company_info = "\n".join(lines) or None
                        break

                # Fallback: lấy bất kỳ đoạn text dài trong trang employer
                if not company_info:
                    for div in comp_page.css("div"):
                        parts = div.css("p::text").getall()
                        text = " ".join(p.strip() for p in parts if p.strip())
                        if len(text) > 200:
                            lines = [p.strip() for p in parts if p.strip()]
                            company_info = "\n".join(lines) or None
                            break

                # Website công ty: tìm link ngoài domain vietnamworks trong trang employer
                for a in comp_page.css("a[href]"):
                    href = a.css("::attr(href)").get() or ""
                    if href.startswith("http") and "vietnamworks.com" not in href:
                        company_website = href.strip()
                        break

        return {
            "title": title,
            "company": company,
            "salary": salary,
            "location": location,
            "experience_level": experience,
            "job_type": job_type,
            "job_industry": job_industry,
            "job_position": job_position,
            "job_description": job_description,
            "requirements": requirements,
            "benefits": benefits,
            "job_deadline": deadline,
            "company_info": company_info,
            "company_website": company_website,
            "job_url": url,
            "source": self.source_name,
            "scraped_at": datetime.now().isoformat(),
        }


if __name__ == "__main__":
    start_url = os.getenv("VIETNAMWORKS_START_URL")
    scraper = VietnamWorksScraper(start_url=start_url)
    links = scraper.run_links_only(pages=102)
    print(f"Total dedup links: {len(links)}")
