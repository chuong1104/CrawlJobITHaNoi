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

from scrapling import Fetcher, StealthyFetcher, DynamicFetcher

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
    # State Management
    # ------------------------------------------------------------------
    def _get_state_file(self) -> Path:
        return self.output_dir / "state.json"

    def _load_state(self) -> dict:
        state_file = self._get_state_file()
        if state_file.exists():
            try:
                with state_file.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_state(self, state: dict) -> None:
        state_file = self._get_state_file()
        with state_file.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def _clear_state(self) -> None:
        state_file = self._get_state_file()
        if state_file.exists():
            state_file.unlink()

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
        if self.use_playwright is True or self.use_playwright == "playwright":
            page = DynamicFetcher.fetch(
                url,
                headless=True,
                disable_resources=True,
                network_idle=True,
                proxy=self.proxy or None,
            )
        elif self.use_playwright in ("stealth", "stealthy"):
            page = StealthyFetcher.fetch(
                url,
                block_resources=True,
                network_idle=True,
                proxy=self.proxy or None,
            )
        else:
            # use_playwright = False hoặc "http" -> Dùng Fetcher (curl_cffi) để bypass Cloudflare/anti-bot tốt hơn mà không cần chạy browser
            page = Fetcher.get(
                url,
                proxy=self.proxy or None,
                stealthy_headers=True,
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
    def _fetch_details_batch(self, urls: list[str], manager, date_str: str, state: dict) -> list[dict]:
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

        # Initialize validation stats in state if not present
        if "total_validated" not in state: state["total_validated"] = 0
        if "total_rejected" not in state: state["total_rejected"] = 0

        for idx, batch in enumerate(batches, 1):
            t_batch = time.time()
            self.logger.info(f"[Phase 3] [Batch {idx}/{total_batches}] {len(batch)} URLs processing...")
            batch_results = self._process_batch(batch)
            results.extend(batch_results)
            
            ok   = len(batch_results)
            fail = len(batch) - ok
            self._stat_fetch_ok   += ok
            self._stat_fetch_fail += fail
            
            # --- Save local batch ---
            num_valid, num_rejected = manager.append_local_batch(
                source=self.source_name,
                date_str=date_str,
                records=batch_results
            )
            state["total_validated"] += num_valid
            state["total_rejected"] += num_rejected
            
            # --- Update state ---
            for url in batch:
                if url in state["pending_urls"]:
                    state["pending_urls"].remove(url)
                state["completed_urls"].append(url)
            self._save_state(state)

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
            if not job:
                return None
            
            # --- Thêm Regex Fallback tự động ---
            full_text = f"{job.get('job_description', '')}\n{job.get('requirements', '')}\n{job.get('benefits', '')}".strip()
            if full_text:
                from src.extract.utils.regex_extractor import FallbackRegexExtractor
                extracted = FallbackRegexExtractor.parse_all(full_text)
                for key, val in extracted.items():
                    if not job.get(key) and val:
                        job[key] = val
            # ------------------------------------
            
            # Đảm bảo các field bắt buộc luôn có
            job.setdefault("source", self.source_name)
            job.setdefault("job_url", url)
            job.setdefault("scraped_at", datetime.now().isoformat())
            job.setdefault("job_id", generate_job_id(self.source_name, url))
            return job
        except Exception as exc:
            self.logger.warning(f"[Phase 3] Parse error: {type(exc).__name__}: {exc}")
            return None

    def run(
        self,
        pages: Optional[int] = None,
        existing_urls: Optional[set[str]] = None,
    ) -> list[dict]:
        """
        Chạy toàn bộ pipeline 3 giai đoạn và lưu kết quả thô.
        Hỗ trợ Resume từ state.json nếu lần chạy trước đó bị lỗi.
        """
        start_time = datetime.now()
        date_str = get_date_str(start_time)
        t0 = time.monotonic()
        
        from src.storage.bronze_manager import BronzeManager
        from src.config import DATA_BRONZE_DIR
        manager = BronzeManager(local_bronze_dir=DATA_BRONZE_DIR, s3_bucket="jobit-bronze")

        state = self._load_state()
        if state.get("status") == "FAILED" and state.get("pending_urls"):
            self.logger.info(f"Resuming from previous FAILED state. {len(state['pending_urls'])} URLs pending.")
            urls = state["pending_urls"]
            self._stat_urls_new = len(urls)
        else:
            pages_label = str(self._resolve_pages(pages)) if pages is not None else "AUTO"
            self.logger.info(f"Start  pages={pages_label}")

            # Phase 1: collect URLs
            t1 = time.monotonic()
            raw_urls = self._collect_urls(pages)
            self.logger.info(f"[Phase 1] Done — {len(raw_urls)} URLs in {fmt_duration(time.monotonic()-t1)}")

            # Phase 2: dedup
            urls = self._deduplicate_urls(raw_urls, existing_urls)
            if not urls:
                self.logger.info("No new URLs to scrape — skipping Phase 3")
                self._clear_state()
                return []
            
            # Khởi tạo trạng thái mới
            state = {
                "status": "IN_PROGRESS",
                "date_str": date_str,
                "pending_urls": urls,
                "completed_urls": [],
                "total_urls": len(urls)
            }
            self._save_state(state)

        # Sử dụng date_str từ state nếu đang resume
        current_date_str = state.get("date_str", date_str)

        # Phase 3: fetch details
        t3 = time.monotonic()
        results = []
        try:
            results = self._fetch_details_batch(urls, manager, current_date_str, state)
            state["status"] = "SUCCESS"
            self._save_state(state)
            
            elapsed = time.monotonic() - t0
            
            # Finalize and upload
            success = manager.finalize_and_upload(
                source=self.source_name,
                date_str=current_date_str,
                total_scraped=state.get("total_urls", len(urls)),
                total_validated=state.get("total_validated", 0),
                total_rejected=state.get("total_rejected", 0),
                scrape_duration_seconds=elapsed,
            )
            
            if success:
                self.logger.info("Successfully processed and uploaded to Bronze.")
                self._clear_state()
            else:
                self.logger.warning("Bronze process/upload completed with some errors.")

            self.logger.info(f"Finished — {len(results)} jobs processed  ⏱ {fmt_duration(elapsed)}")
            return results
            
        except Exception as exc:
            self.logger.error(f"Global error during scraping Phase 3: {exc}")
            state["status"] = "FAILED"
            self._save_state(state)
            raise

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
