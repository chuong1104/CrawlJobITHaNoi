import os
import random
import time
from typing import Optional
from urllib.parse import urljoin

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

    def parse_job_detail(self, detail_html: str, url: str) -> dict:
        raise NotImplementedError("Implement parse_job_detail sau khi xong bước lấy link.")


if __name__ == "__main__":
    start_url = os.getenv("VIETNAMWORKS_START_URL")
    scraper = VietnamWorksScraper(start_url=start_url)
    links = scraper.run_links_only(pages=102)
    print(f"Total dedup links: {len(links)}")
