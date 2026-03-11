import os
import random
import time
from typing import Optional
from urllib.parse import urljoin

from scrapling.parser import Adaptor

from src.extract.job_online.base_scraper import BaseScraper


class YboxScraper(BaseScraper):
    source_name = "ybox"
    base_url = "https://ybox.vn"
    batch_size = 10

    # URL lọc Hà Nội — không cần trailing ?keyword=
    DEFAULT_START_URL = "https://ybox.vn/tuyen-dung-viec-lam-tai-ha-noi-tk-c1e2"
    MAX_SCROLLS = 1000
    SCROLL_PAUSE = (1.5, 3.0)

    def __init__(self, start_url: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.start_url = start_url or self.DEFAULT_START_URL

    def get_list_page_url(self, page_num: int) -> str:
        return self.start_url

    def get_next_page_url(
        self, list_page_html: str, page_num: int, current_url: str
    ) -> str | None:
        return None  # Infinite scroll — không có next page URL

    def extract_job_urls(self, list_page_html: str) -> list[str]:
        page = Adaptor(list_page_html)
        hrefs = page.css("h2.post-title a.internal::attr(href)").getall()
        # Fallback nếu selector trên thay đổi
        if not hrefs:
            hrefs = page.css("a[href*='/tuyen-dung/']::attr(href)").getall()
        links: list[str] = []
        seen: set[str] = set()
        for href in hrefs:
            if not href:
                continue
            full_url = urljoin(self.base_url, href).split("#")[0]
            if "/tuyen-dung/" not in full_url:
                continue
            if full_url not in seen:
                seen.add(full_url)
                links.append(full_url)
        return links

    def _find_next_page_url(self, pw_page, page_num: int) -> str | None:
        """
        Tìm URL trang kế tiếp:
        1. Ưu tiên selector CSS (a[rel='next'], .next a, ...)
        2. Fallback: xây URL ?page=N+1 theo pattern Ybox
        """
        NEXT_SELECTORS = [
            "a[rel='next']",
            "a.next",
            "li.next a",
            ".pagination a.next",
            ".pager a[class*='next' i]",
            "[class*='pagination'] a[class*='next' i]",
        ]
        for sel in NEXT_SELECTORS:
            el = pw_page.query_selector(sel)
            if el:
                href = el.get_attribute("href")
                if href:
                    return urljoin(self.base_url, href)
        # Fallback: Ybox dùng ?page=N — sẽ dừng khi trang trả về 0 URL mới
        base = self.start_url.split("?")[0]
        return f"{base}?page={page_num + 1}"

    def _collect_urls(self, pages: Optional[int] = None) -> list[str]:
        """
        Override: scroll sim trên từng trang + pagination fallback.
        Khi scroll đến đáy mà không render thêm job → chuyển sang trang kế,
        tiếp tục cào cho đến khi không còn trang nào mới.
        """
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

        max_pages = pages  # None = tự động dừng khi hết data
        all_urls: list[str] = []
        seen_urls: set[str] = set()

        # Chỉ block image/media — stylesheet/font cần cho render
        # Use BaseScraper._block_media for resource blocking
        _block_media = BaseScraper._block_media

        def _scroll_page(pw_page, page_label: str) -> tuple[int, bool]:
            """Scroll đến đáy trang hiện tại, trả về số URL mới tìm được và trạng thái đã scroll hết."""
            collected = 0
            scroll_step = 800      # px mỗi bước — scroll rộng hơn để tăng tốc
            current_pos = 0
            bottom_streak = 0       # đếm số lần đụng đáy mà chiều cao không tăng
            MAX_BOTTOM_STREAK = 3   # dừng sau 3 lần đáy "không có gì mới"
            no_new_links_streak = 0
            MAX_NO_NEW_LINKS_STREAK = 3
            scrolled_to_bottom = False

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
                            scrolled_to_bottom = True
                            break
                        # Đợi thêm trước lần thử tiếp theo
                        time.sleep(2.0)

            # Luôn scroll đến đáy, không dừng sớm khi hết link mới
            return collected, scrolled_to_bottom

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

                    # Chờ job card render
                    try:
                        pw_page.wait_for_selector("a[href*='/tuyen-dung/']", timeout=15_000)
                        self.logger.info(f"Job links đã render ✓ (trang {page_num})")
                    except PlaywrightTimeout:
                        self.logger.warning(f"Timeout chờ job links trang {page_num} — thử tiếp")
                        snippet = pw_page.content()[:2000]
                        self.logger.debug(f"HTML snippet:\n{snippet}")

                    collected, scrolled_to_bottom = _scroll_page(pw_page, f"Trang {page_num}")

                    # Chỉ chuyển trang khi đã scroll hết (scrolled_to_bottom)
                    if not scrolled_to_bottom:
                        self.logger.info(f"[Phase 1] Chưa scroll hết trang {page_num} → không chuyển trang")
                        break

                    # Trang mới (page_num > 1) mà không có URL mới → đã hết data
                    if collected == 0 and page_num > 1:
                        self.logger.info("[Phase 1] Trang kế không có URL mới → dừng")
                        break

                    # Tìm / xây URL trang kế
                    next_url = self._find_next_page_url(pw_page, page_num)
                    if not next_url:
                        self.logger.info("[Phase 1] Không tìm thấy trang kế tiếp → dừng")
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
    start_url = os.getenv("YBOX_START_URL")
    scraper = YboxScraper(start_url=start_url)
    links = scraper.run_links_only(pages=3)
    print(f"Total dedup links: {len(links)}")
