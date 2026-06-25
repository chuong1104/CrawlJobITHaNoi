"""
BaseScraper — Class cha chứa toàn bộ hạ tầng chung cho mọi scraper:

  Phase 1 · collect_urls(pages)         → list[str]  (raw, có thể trùng)
  Phase 2 · _deduplicate_urls(urls)     → list[str]  (đã loại trùng)
  Phase 3 · _fetch_details_batch(urls)  → list[dict] (raw job dicts)

Scraper con chỉ cần implement 2 phương thức:
  · extract_job_urls(list_page_html: str)        → list[str]
  · parse_job_detail(detail_html: str, url: str) → dict
"""

import abc
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional

from scrapling import StealthyFetcher, DynamicFetcher

from src.config import DATA_BRONZE_DIR, ScraperConfig
from src.utils import ensure_dir, fmt_duration, generate_job_id, get_date_str, setup_logger


class ScrapingException(Exception):
    """Raised khi scraper không thể fetch sau max_retries lần."""


class BaseScraper(abc.ABC):
       
    """
    Class cha trừu tượng. Subclass phải khai báo:
        source_name = "topcv"
        base_url    = "https://www.topcv.vn"

    và implement:
        extract_job_urls()
        parse_job_detail()
    """

    source_name: str = ""
    base_url: str = ""
    batch_size: int = ScraperConfig.BATCH_SIZE

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------
    def __init__(
        self,
        max_retries: int = ScraperConfig.MAX_RETRIES,
        delay_range: tuple[float, float] = ScraperConfig.delay_range(),
        proxy: Optional[str] = ScraperConfig.PROXY_URL or None,
        output_dir: Optional[Path] = None,
        use_playwright: bool = False,
    ) -> None:
        if not self.source_name:
            raise ValueError(f"{self.__class__.__name__} phải khai báo source_name")

        self.max_retries = max_retries
        self.delay_range = delay_range
        self.proxy = proxy
        self.use_playwright = use_playwright
        self.output_dir = output_dir or ensure_dir(DATA_BRONZE_DIR / self.source_name)
        self.logger = setup_logger(f"scraper.{self.source_name}")
        # Thống kê nội bộ
        self._stat_urls_raw    = 0
        self._stat_urls_new    = 0
        self._stat_fetch_ok    = 0
        self._stat_fetch_fail  = 0

    # ------------------------------------------------------------------
    # Abstract interface — subclass phải implement
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def extract_job_urls(self, list_page_html: str) -> list[str]:
        """
        Phase 1: từ HTML trang danh sách → trả về list[str] URL của job.
        URL có thể là relative; BaseScraper sẽ gọi make_absolute_url sau.
        """

    @abc.abstractmethod
    def parse_job_detail(self, detail_html: str, url: str) -> dict:
        """
        Phase 3: từ HTML trang chi tiết → trả về raw dict theo quy ước output.
        Bắt buộc phải có key 'source', 'job_url', 'scraped_at'.
        """

    def get_list_page_url(self, page_num: int) -> str:
        """
        Trả về URL trang danh sách thứ page_num.
        Override trong subclass nếu có pagination. Mặc định trả về base_url.
        """
        return self.base_url

    def get_next_page_url(
        self,
        list_page_html: str,
        page_num: int,
        current_url: str,
    ) -> str | None:
        # Default fallback: tăng page theo quy tắc URL của scraper
        return self.get_list_page_url(page_num + 1)
    
    @staticmethod
    def _block_media(route):
        if route.request.resource_type in ("image", "media", "font", "stylesheet"):
            route.abort()
        else:
            route.continue_() 

    # ------------------------------------------------------------------
    # HTTP fetch (private)
    # ------------------------------------------------------------------
    def _fetch_html(self, url: str) -> Optional[str]:
        """
        Fetch URL và trả về HTML string.
        Retry với exponential backoff khi gặp lỗi hoặc HTTP 429/503.
        Trả về None nếu vẫn thất bại sau max_retries.
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                html = self._do_fetch(url)
                if html:
                    if self._is_valid_html(html, url):
                        return html
                    else:
                        wait = self._backoff(attempt)
                        self.logger.warning(
                            f"Blocked or Invalid HTML (attempt {attempt}/{self.max_retries}) → retry in {wait:.0f}s: {url}"
                        )
                else:
                    wait = self._backoff(attempt)
                    self.logger.warning(
                        f"Empty response (attempt {attempt}/{self.max_retries}) → retry in {wait:.0f}s: {url}"
                    )

                if attempt < self.max_retries:
                    time.sleep(wait)

            except Exception as exc:
                wait = self._backoff(attempt)
                self.logger.warning(
                    f"Fetch error (attempt {attempt}/{self.max_retries}): {type(exc).__name__} → retry in {wait:.0f}s: {url}"
                )
                if attempt < self.max_retries:
                    time.sleep(wait)

        self.logger.error(f"Gave up after {self.max_retries} retries: {url}")
        return None

    def _is_valid_html(self, html: str, url: str) -> bool:
        """
        Hook để subclass kiểm tra xem HTML có bị chặn hay không (CAPTCHA, 429...).
        Mặc định là True.
        """
        return True

    def _do_fetch(self, url: str) -> Optional[str]:
        """Thực hiện 1 lần fetch, trả về HTML string hoặc None."""
        if self.use_playwright:
            page = DynamicFetcher.fetch(
                url,
                headless=True,
                disable_resources=True,
                network_idle=False,
                proxy=self.proxy or None,
            )
        else:
            page = StealthyFetcher.fetch(
                url,
                block_resources=True,
                network_idle=False,
                proxy=self.proxy or None,
            )

        return self._adaptor_to_html(page)

    @staticmethod
    def _adaptor_to_html(page) -> Optional[str]:
        """
        Lấy HTML string từ kết quả fetch của Scrapling.
        Hỗ trợ nhiều phiên bản Scrapling API.
        """
        if page is None:
            return None
        # Thử các property phổ biến theo thứ tự ưu tiên
        for attr in ("html_content", "content", "body", "html"):
            val = getattr(page, attr, None)
            if val is not None:
                return val.decode("utf-8") if isinstance(val, bytes) else str(val)
        return str(page)

    def _backoff(self, attempt: int) -> float:
        """Exponential backoff với jitter. Tăng thời gian chờ khi bị chặn."""
        base_wait = 2.0 ** attempt
        jitter = random.uniform(2.0, 5.0)
        return base_wait + jitter + (5.0 * attempt)

    def _resolve_pages(self, pages: Optional[int]) -> Optional[int]:
        """
        Resolve số trang cào.

        - pages=None  -> chế độ auto (crawl đến khi không còn dữ liệu mới)
        - pages>0     -> crawl tối đa đúng pages trang
        """
        if pages is None:
            return None
        if pages <= 0:
            raise ValueError("pages phải > 0")
        return pages

    # ------------------------------------------------------------------
    # Phase 1: Collect URLs
    # ------------------------------------------------------------------
    def _collect_urls(self, pages: Optional[int] = None) -> list[str]:
        """
        Thu thập URL theo pagination.

        - pages=None: auto-crawl đến khi gặp điều kiện dừng an toàn.
        - pages>0: crawl tối đa số trang chỉ định.
        """
        max_pages = self._resolve_pages(pages)
        all_urls: list[str] = []
        seen_urls: set[str] = set()
        visited_pages: set[str] = set()

        page_num = 1
        current_url = self.get_list_page_url(page_num)

        while current_url:
            if current_url in visited_pages:
                self.logger.debug(f"[Phase 1] Loop detected at page {page_num} → stop")
                break
            visited_pages.add(current_url)

            page_label = f"{page_num}/{max_pages}" if max_pages is not None else f"p{page_num}"
            self.logger.info(f"[Phase 1] {page_label} fetching...")

            html = self._fetch_html(current_url)
            if not html:
                self.logger.warning(f"[Phase 1] Fetch failed at page {page_num} → stop")
                break

            try:
                urls = self.extract_job_urls(html)
            except Exception as exc:
                self.logger.warning(f"[Phase 1] extract_job_urls error p{page_num}: {type(exc).__name__}")
                urls = []

            new_urls_count = 0
            for u in urls:
                if u not in seen_urls:
                    seen_urls.add(u)
                    new_urls_count += 1

            self.logger.info(
                f"[Phase 1] {page_label} → {len(urls)} URLs found, {new_urls_count} new"
            )
            all_urls.extend(urls)

            if len(urls) == 0:
                self.logger.info(f"[Phase 1] No URLs on page {page_num} → stop")
                break

            if new_urls_count == 0:
                self.logger.info(f"[Phase 1] No new URLs on page {page_num} → stop")
                break

            if max_pages is not None and page_num >= max_pages:
                break

            next_url = self.get_next_page_url(html, page_num, current_url)
            if not next_url:
                self.logger.info("[Phase 1] No next page → stop")
                break

            delay = random.uniform(*self.delay_range)
            time.sleep(delay)
            page_num += 1
            current_url = next_url

        return all_urls

    # ------------------------------------------------------------------
    # Phase 2: Deduplicate
    # ------------------------------------------------------------------
    def _deduplicate_urls(
        self,
        urls: list[str],
        existing_urls: Optional[set[str]] = None,
    ) -> list[str]:
        """
        Loại URL trùng nội bộ + loại URL đã tồn tại trong DB.
        Giữ nguyên thứ tự.
        """
        seen: set[str] = set()
        unique: list[str] = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                unique.append(u)

        before = len(unique)
        if existing_urls:
            unique = [u for u in unique if u not in existing_urls]

        self.logger.info(
            f"[Phase 2] Dedup: {len(urls)} raw → {before} unique → {len(unique)} new"
        )
        self._stat_urls_raw = len(urls)
        self._stat_urls_new = len(unique)
        return unique

    # ------------------------------------------------------------------
    # Phase 3: Batch-parallel detail fetch
    # ------------------------------------------------------------------
    def _fetch_details_batch(self, urls: list[str]) -> list[dict]:
        """
        Chia URLs thành batches, mỗi batch fetch song song bằng ThreadPoolExecutor.
        Sleep random giữa các batch để tránh rate limit.
        """
        results: list[dict] = []
        batches = [
            urls[i : i + self.batch_size]
            for i in range(0, len(urls), self.batch_size)
        ]
        total_batches = len(batches)

        for idx, batch in enumerate(batches, 1):
            t_batch = time.time()
            self.logger.info(f"[Phase 3] [Batch {idx}/{total_batches}] {len(batch)} URLs processing...")
            batch_results = self._process_batch(batch)
            results.extend(batch_results)
            ok   = len(batch_results)
            fail = len(batch) - ok
            self._stat_fetch_ok   += ok
            self._stat_fetch_fail += fail
            elapsed_b = time.time() - t_batch
            self.logger.info(
                f"[Phase 3] [Batch {idx}/{total_batches}] "
                f"✔ {ok}/{len(batch)} parsed  "
                f"({fmt_duration(elapsed_b)})"
                + (f"  ✖ {fail} failed" if fail else "")
            )

            if idx < total_batches:
                delay = random.uniform(*self.delay_range)
                time.sleep(delay)

        return results

    def _process_batch(self, batch: list[str]) -> list[dict]:
        """Fetch và parse song song một batch URL."""
        results: list[dict] = []
        with ThreadPoolExecutor(max_workers=len(batch)) as executor:
            future_to_url = {
                executor.submit(self._fetch_and_parse, url): url for url in batch
            }
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as exc:
                    self.logger.warning(f"[Phase 3] Error processing URL: {type(exc).__name__}")
        return results

    def _fetch_and_parse(self, url: str) -> Optional[dict]:
        """Fetch 1 URL và parse, trả về dict hoặc None nếu thất bại."""
        html = self._fetch_html(url)
        if not html:
            return None
        try:
            job = self.parse_job_detail(html, url)
            # Đảm bảo các field bắt buộc luôn có
            job.setdefault("source", self.source_name)
            job.setdefault("job_url", url)
            job.setdefault("scraped_at", datetime.now().isoformat())
            job.setdefault("job_id", generate_job_id(self.source_name, url))
            return job
        except Exception as exc:
            self.logger.warning(f"[Phase 3] Parse error: {type(exc).__name__}: {exc}")
            return None

    def save_raw(
        self,
        results: list[dict],
        date_str: Optional[str] = None,
        elapsed: float = 0.0,
    ) -> Path:
        """
        Lưu kết quả qua BronzeManager để validate (RawJobPosting), chia jsonl,
        lưu metadata và upload lên S3.
        """
        try:
            from src.storage.bronze_manager import BronzeManager
            from src.config import DATA_BRONZE_DIR

            manager = BronzeManager(local_bronze_dir=DATA_BRONZE_DIR, s3_bucket="jobit-bronze")
            success = manager.process_and_upload(
                source=self.source_name,
                records=results,
                scrape_duration_seconds=elapsed,
            )

            if success:
                self.logger.info("Successfully processed and uploaded to Bronze.")
            else:
                self.logger.warning("Bronze process/upload completed with some errors.")
        except Exception as e:
            self.logger.error(f"Error during Bronze processing: {e}")

        return self.output_dir

    # ------------------------------------------------------------------
    # Save links
    # ------------------------------------------------------------------
    def save_links(
        self,
        links: list[str],
        date_str: Optional[str] = None,
    ) -> Path:
        """
        Lưu toàn bộ links (đã dedup) vào 1 file:
        data/raw/{source_name}/links/{YYYY-MM-DD}_links.json
        """
        date_str = date_str or get_date_str()
        links_dir = ensure_dir(self.output_dir / "links")
        out_path = links_dir / f"{date_str}_links.json"

        payload = {
            "source": self.source_name,
            "saved_at": datetime.now().isoformat(),
            "total_links": len(links),
            "links": links,
        }

        with out_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        self.logger.info(f"Saved {len(links)} links -> {out_path}")
        return out_path

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    def run(
        self,
        pages: Optional[int] = None,
        existing_urls: Optional[set[str]] = None,
    ) -> list[dict]:
        """
        Chạy toàn bộ pipeline 3 giai đoạn và lưu kết quả thô.

        Args:
            pages: số trang danh sách cào ở Phase 1.
                Nếu None, dùng AirflowConfig.SCRAPE_PAGES.
            existing_urls: tập URL đã có trong DB (để dedup ở Phase 2).

        Returns:
            list[dict] — raw job data (đã lưu ra disk).
        """
        pages_label = str(self._resolve_pages(pages)) if pages is not None else "AUTO"
        self.logger.info(f"Start  pages={pages_label}")
        start_time = datetime.now()
        t0 = time.monotonic()

        # Phase 1: collect URLs
        t1 = time.monotonic()
        raw_urls = self._collect_urls(pages)
        self.logger.info(f"[Phase 1] Done — {len(raw_urls)} URLs in {fmt_duration(time.monotonic()-t1)}")

        # Phase 2: dedup
        urls = self._deduplicate_urls(raw_urls, existing_urls)
        if not urls:
            self.logger.info("No new URLs to scrape — skipping Phase 3")
            return []

        # Phase 3: fetch details
        t3 = time.monotonic()
        results = self._fetch_details_batch(urls)
        self.logger.info(
            f"[Phase 3] Done — {self._stat_fetch_ok} parsed, "
            f"{self._stat_fetch_fail} failed in {fmt_duration(time.monotonic()-t3)}"
        )

        # Persist
        date_str = get_date_str(start_time)
        elapsed = time.monotonic() - t0
        self.save_raw(results, date_str, elapsed)

        self.logger.info(
            f"Finished — {len(results)} jobs saved  ⏱ {fmt_duration(elapsed)}"
        )
        return results

    def run_links_only(
        self,
        pages: Optional[int] = None,
        existing_urls: Optional[set[str]] = None,
    ) -> list[str]:
        """Cào links chỉ, không cần parse. pages=None sẽ dùng config trung tâm."""
        raw_urls = self._collect_urls(pages)
        links = self._deduplicate_urls(raw_urls, existing_urls)
        self.save_links(links)
        return links
