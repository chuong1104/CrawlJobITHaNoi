import os
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List
import re
import csv
import json
import urllib.parse

from src.extract.job_online.base_scraper import BaseScraper
from src.utils import ensure_dir, get_date_str


class LinkedInScraperV2(BaseScraper):
    source_name = "linkedin"
    base_url = "https://www.linkedin.com/jobs/search/?f_E=1%2C2%2C3&geoId=90010186"
    batch_size: int = 5

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("use_playwright", True)
        super().__init__(*args, **kwargs)
        self.username = os.getenv("LINKEDIN_USERNAME") or os.getenv("LINKEDIN_EMAIL")
        self.password = os.getenv("LINKEDIN_PASSWORD") or os.getenv("LINKEDIN_PASS")
        self.session_file = Path("linkedin_session.json")

    def get_list_page_url(self, page_num: int, keyword: Optional[str] = None) -> str:
        """
        Trả về URL phân trang LinkedIn. Hỗ trợ truyền keyword.
        """
        start = (page_num - 1) * 25
        
        parsed = urllib.parse.urlparse(self.base_url)
        query = urllib.parse.parse_qs(parsed.query)
        
        if keyword:
            query['keywords'] = [keyword]
            
        if start > 0:
            query['start'] = [str(start)]
            
        new_query = urllib.parse.urlencode(query, doseq=True)
        return urllib.parse.urlunparse(parsed._replace(query=new_query))

    def _perform_login(self, page, context) -> bool:
        """Đăng nhập và tái sử dụng session cookie."""
        if not self.username or not self.password:
            self.logger.warning("Không tìm thấy thông tin tài khoản LinkedIn, cào không cần đăng nhập.")
            return False

        # Thử load session cũ
        if self.session_file.exists():
            try:
                with open(self.session_file, "r") as f:
                    cookies = json.load(f)
                context.add_cookies(cookies)
                self.logger.info("Đã load session cookies từ lần chạy trước.")
                
                # Check login state
                page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
                if "feed" in page.url.lower() or "mynetwork" in page.url.lower():
                    self.logger.info("Sử dụng session cũ thành công!")
                    return True
                else:
                    self.logger.info("Session cũ đã hết hạn, tiến hành đăng nhập lại.")
                    # Clear cookies
                    context.clear_cookies()
            except Exception as e:
                self.logger.warning(f"Lỗi load session: {e}")

        self.logger.info("Đang đăng nhập LinkedIn qua Playwright...")
        try:
            page.goto("https://www.linkedin.com/checkpoint/rm/sign-in-another-account", wait_until="domcontentloaded")
            page.wait_for_selector("#username", timeout=15000)

            # Nhập liệu như người thật
            page.locator("#username").press_sequentially(self.username, delay=random.randint(50, 150))
            time.sleep(random.uniform(0.5, 1.0))
            page.locator("#password").press_sequentially(self.password, delay=random.randint(50, 150))
            time.sleep(random.uniform(0.5, 1.0))

            login_btn_selectors = [
                'button[type="submit"]',
                '.btn__primary--large.from__button--floating'
            ]
            login_btn = None
            for sel in login_btn_selectors:
                try:
                    btn = page.query_selector(sel)
                    if btn:
                        login_btn = btn
                        break
                except (AttributeError, TypeError):
                    continue
                except KeyboardInterrupt:
                    raise

            if login_btn:
                login_btn.click()
            else:
                page.click('button[type="submit"]')

            page.wait_for_timeout(5000)

            current_url = page.url.lower()
            if any(x in current_url for x in ['challenge', 'checkpoint', 'security-verification', 'authwall']):
                self.logger.error(f"Đăng nhập bị chặn bởi cơ chế bảo mật (checkpoint/2FA): {current_url}")
                page.screenshot(path="login_checkpoint_error.png")
                return False

            self.logger.info("Đăng nhập LinkedIn thành công!")
            
            # Lưu session
            cookies = context.cookies()
            with open(self.session_file, "w") as f:
                json.dump(cookies, f)
                
            return True
        except KeyboardInterrupt:
            raise
        except Exception as e:
            self.logger.error(f"Lỗi khi đăng nhập LinkedIn: {e}")
            page.screenshot(path="login_error.png")
            return False

    def _check_next_page_exists(self, page) -> bool:
        """Kiểm tra xem nút trang tiếp theo có khả dụng hay không."""
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.0)

            next_selectors = [
                'button.jobs-search-pagination__button--next',
                'xpath=//button[contains(@class, "jobs-search-pagination__button--next")]',
                'xpath=//button[.//span[text()="Tiếp theo"]]',
                'xpath=//button[.//span[text()="Next"]]'
            ]

            for sel in next_selectors:
                try:
                    btn = page.query_selector(sel)
                    if btn:
                        is_disabled = (
                            btn.is_disabled()
                            or btn.get_attribute("aria-disabled") == "true"
                            or "disabled" in (btn.get_attribute("class") or "")
                        )
                        if not is_disabled:
                            return True
                except (AttributeError, TypeError):
                    continue
                except KeyboardInterrupt:
                    raise
        except KeyboardInterrupt:
            raise
        except Exception as e:
            self.logger.warning(f"Lỗi kiểm tra nút phân trang: {e}")
        return False

    def _scroll_job_list(self, page) -> list[str]:
        """Cuộn danh sách job bên trái để tải hết job (virtual scrolling)."""
        self.logger.info("Bắt đầu tìm và cuộn danh sách job...")

        # Tìm và gán ID cho container cuộn
        job_list_container = "#job-scraper-scroll-container"
        container_found = False
        
        for _ in range(15):
            container_found = page.evaluate("""() => {
                if (document.querySelector('#job-scraper-scroll-container')) return true;
                
                let card = document.querySelector('li.scaffold-layout__list-item, a.job-card-container__link');
                if (!card) return false;
                
                let el = card.parentElement;
                let scrollableEl = null;
                
                while (el && el !== document.body) {
                    const style = window.getComputedStyle(el);
                    if ((style.overflowY === 'auto' || style.overflowY === 'scroll') && el.scrollHeight > el.clientHeight) {
                        scrollableEl = el;
                        break;
                    }
                    el = el.parentElement;
                }
                
                if (!scrollableEl) {
                    let parent = card.parentElement;
                    while (parent && parent !== document.body) {
                        if (parent.className && typeof parent.className === 'string' && parent.className.includes('list')) {
                            if (parent.scrollHeight > parent.clientHeight) {
                                scrollableEl = parent;
                                break;
                            }
                        }
                        parent = parent.parentElement;
                    }
                }
                
                if (!scrollableEl) {
                    let fallback = document.querySelector('.scaffold-layout__list');
                    if (fallback && fallback.scrollHeight > fallback.clientHeight) scrollableEl = fallback;
                }
                
                if (scrollableEl) {
                    scrollableEl.setAttribute('id', 'job-scraper-scroll-container');
                    return true;
                }
                return false;
            }""")
            
            if container_found:
                self.logger.info("✓ Đã tìm thấy và gán ID cho job list container.")
                break
            time.sleep(1.0)

        if not container_found:
            self.logger.error("✗ KHÔNG TÌM THẤY job list container có thể cuộn. Thử cuộn toàn bộ trang (window).")
            job_list_container = "window"

        collected_urls = set()

        def extract_urls_from_page():
            links = page.query_selector_all(
                "a.job-card-container__link, "
                "a.job-card-list__title--link, "
                "a.base-card__full-link"
            )
            for link in links:
                try:
                    href = link.get_attribute("href")
                    if href:
                        href = href.strip()
                        if href.startswith('/'):
                            href = f"https://www.linkedin.com{href}"
                        
                        # Fix chuẩn hóa URL theo Regex thay vì split('?')
                        m = re.search(r'/jobs/view/(\d+)', href)
                        if m:
                            collected_urls.add(f"https://www.linkedin.com/jobs/view/{m.group(1)}/")
                except (AttributeError, TypeError):
                    pass
                except KeyboardInterrupt:
                    raise

        extract_urls_from_page()
        self.logger.info(f"[Initial] Tìm thấy {len(collected_urls)} jobs trước cuộn")

        max_scrolls = 100
        scroll_step = 400
        consecutive_no_new = 0
        max_consecutive = 6

        for scroll_attempt in range(max_scrolls):
            if job_list_container == "window":
                page.evaluate(f"window.scrollBy(0, {scroll_step})")
            else:
                page.evaluate(f"""() => {{
                    const el = document.querySelector("{job_list_container}");
                    if (el) el.scrollTop += {scroll_step};
                }}""")

            # Explicit wait để kiểm tra số lượng job thay đổi thay vì sleep fix cứng
            try:
                page.wait_for_function(f"""() => {{
                    const links = document.querySelectorAll('a.job-card-container__link');
                    return links.length > {len(collected_urls)};
                }}""", timeout=1500)
            except Exception:
                # Nếu không có thẻ mới trong 1.5s thì bỏ qua (timeout)
                pass
            
            urls_before = len(collected_urls)
            extract_urls_from_page()
            urls_after = len(collected_urls)

            new_count = urls_after - urls_before
            
            if new_count > 0:
                self.logger.info(f"[Scroll #{scroll_attempt+1}] +{new_count} jobs → Tổng: {urls_after}/25")
                consecutive_no_new = 0
            else:
                consecutive_no_new += 1

            if urls_after >= 25:
                self.logger.info(f"✓ Đã đạt {urls_after} jobs. Dừng cuộn.")
                break

            reached_bottom = False
            if job_list_container != "window":
                reached_bottom = page.evaluate(f"""() => {{
                    const el = document.querySelector("{job_list_container}");
                    if (!el) return true;
                    return (el.scrollTop + el.clientHeight + 50) >= el.scrollHeight;
                }}""")

            if reached_bottom:
                self.logger.info(f"Chạm đáy container. Hiện có {urls_after} jobs.")
                if urls_after < 25:
                    self.logger.warning(f"⚠ Chỉ tìm được {urls_after} jobs (kỳ vọng 25). Chờ thêm để đảm bảo không miss job...")
                    
                    page.evaluate(f"""() => {{
                        const el = document.querySelector("{job_list_container}");
                        if (el) el.scrollTop -= 200;
                    }}""")
                    time.sleep(0.5)
                    page.evaluate(f"""() => {{
                        const el = document.querySelector("{job_list_container}");
                        if (el) el.scrollTop += 300;
                    }}""")
                    
                    try:
                        page.wait_for_function(f"""() => {{
                            const links = document.querySelectorAll('a.job-card-container__link');
                            return links.length > {len(collected_urls)};
                        }}""", timeout=3000)
                    except Exception:
                        pass
                    
                    extract_urls_from_page()
                    if len(collected_urls) > urls_after:
                        self.logger.info(f"Sau khi ép trigger: +{len(collected_urls) - urls_after} jobs nữa")
                        consecutive_no_new = 0
                    else:
                        break
                else:
                    break

            if consecutive_no_new >= max_consecutive and urls_after > 0:
                self.logger.info(f"Không có job mới sau {max_consecutive} lần cuộn liên tiếp. Dừng.")
                break

        self.logger.info(f"[Kết thúc cuộn] Thu thập {len(collected_urls)} URLs từ trang danh sách.")
        return list(collected_urls)

    def _collect_urls(self, pages: Optional[int] = None, keywords: Optional[List[str]] = None) -> list[str]:
        """Thu thập URL dựa trên keyword."""
        from playwright.sync_api import sync_playwright

        max_pages = self._resolve_pages(pages)
        all_urls: list[str] = []
        seen_urls: set[str] = set()
        
        # Nếu không truyền keyword, sẽ chạy 1 lần với URL mặc định
        search_keywords = keywords if keywords else [None]

        self.logger.info("Khởi tạo trình duyệt Playwright...")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )

            def block_media(route):
                if route.request.resource_type in ("image", "media", "font", "stylesheet"):
                    route.abort()
                else:
                    route.continue_()

            page = context.new_page()
            page.route("**/*", block_media)

            if self.username and self.password:
                self._perform_login(page, context)

            for kw in search_keywords:
                kw_label = kw if kw else "Mặc định"
                self.logger.info(f"=== Bắt đầu tìm kiếm Keyword: {kw_label} ===")
                
                page_num = 1
                while True:
                    page_label = f"{page_num}/{max_pages}" if max_pages is not None else f"{page_num}/AUTO"
                    page_url = self.get_list_page_url(page_num, keyword=kw)

                    self.logger.info(f"[Phase 1] [{kw_label}] Page {page_label} -> {page_url}")
                    
                    try:
                        page.goto(page_url, wait_until="domcontentloaded", timeout=45000)
                    except Exception as e:
                        self.logger.error(f"Lỗi tải trang: {e}")
                        page.screenshot(path=f"error_load_page_{page_num}.png")
                        break

                    current_url = page.url.lower()
                    if any(x in current_url for x in ['challenge', 'checkpoint', 'security-verification', 'authwall']):
                        self.logger.error("Bị chặn bởi màn hình checkpoint bảo mật của LinkedIn!")
                        page.screenshot(path="checkpoint_error.png")
                        break

                    try:
                        page.wait_for_selector(
                            "a.job-card-container__link, a.job-card-list__title--link",
                            timeout=25000
                        )
                    except Exception as wait_err:
                        self.logger.warning(f"Timeout chờ job cards trang {page_num}: {wait_err}")
                        page.screenshot(path=f"timeout_page_{page_num}.png")
                        break

                    scrolled_urls = self._scroll_job_list(page)

                    new_urls_count = 0
                    for u in scrolled_urls:
                        if u not in seen_urls:
                            seen_urls.add(u)
                            new_urls_count += 1
                            all_urls.append(u)

                    self.logger.info(
                        f"[Phase 1] [{kw_label}] Page {page_num}: Thu thập {len(scrolled_urls)} URLs "
                        f"(mới: {new_urls_count}, tổng: {len(all_urls)})"
                    )

                    if len(scrolled_urls) == 0 or new_urls_count == 0:
                        self.logger.info(f"[Phase 1] [{kw_label}] Không tìm thấy URL job mới nào. Dừng keyword này.")
                        break

                    if max_pages is not None and page_num >= max_pages:
                        self.logger.info(f"[Phase 1] [{kw_label}] Đạt giới hạn số trang {max_pages}. Dừng keyword này.")
                        break

                    has_next = self._check_next_page_exists(page)
                    if not has_next:
                        self.logger.info(f"[Phase 1] [{kw_label}] Không có nút trang tiếp theo khả dụng. Dừng keyword này.")
                        break

                    page_num += 1
                    delay = random.uniform(2.5, 4.5)
                    time.sleep(delay)

            browser.close()

        return all_urls

    def extract_job_urls(self, list_page_html: str) -> list[str]:
        raise NotImplementedError("Không sử dụng trong V2.")

    def parse_job_detail(self, detail_html: str, url: str) -> dict:
        raise NotImplementedError("parse_job_detail is not implemented for LinkedIn. LinkedIn scraper only runs in link-collection mode.")

    def save_links(self, links: list[str], date_str: Optional[str] = None) -> Path:
        super().save_links(links, date_str)

        date_str = date_str or get_date_str()
        links_dir = ensure_dir(self.output_dir / "links")
        csv_path = links_dir / f"{date_str}_linkedin_v2_links.csv"

        try:
            with csv_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["job_url"])
                for link in links:
                    writer.writerow([link])
            self.logger.info(f"[Phase 1] Saved {len(links)} links to CSV -> {csv_path}")
        except Exception as e:
            self.logger.error(f"Failed to save CSV links: {e}")

        return csv_path

    def run(
        self,
        pages: Optional[int] = None,
        existing_urls: Optional[set] = None,
        keywords: Optional[List[str]] = None
    ) -> list[str]:
        from src.utils import get_date_str as _gds
        from datetime import datetime as _dt

        pages_label = str(pages) if pages is not None else "AUTO (hết trang)"
        kw_label = ", ".join(keywords) if keywords else "Mặc định"
        
        self.logger.info(f"=== BẮT ĐẦU scraper [{self.source_name}] | pages={pages_label} | Keywords: {kw_label} ===")
        start_time = _dt.now()
        date_str   = _gds(start_time)

        self.logger.info("[Thu thập URL] Bắt đầu thu thập URL từ trang danh sách...")
        raw_urls = self._collect_urls(pages, keywords=keywords)
        urls     = self._deduplicate_urls(raw_urls, existing_urls)

        if not urls:
            self.logger.info("[Thu thập URL] Không có URL mới để cào. Kết thúc.")
            return []

        self.save_links(urls, date_str)
        elapsed = (_dt.now() - start_time).total_seconds()
        self.logger.info(f"=== XONG [{self.source_name}] | {len(urls)} URLs | {elapsed:.1f}s ===")
        return urls


if __name__ == "__main__":
    import argparse
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-15s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    parser = argparse.ArgumentParser(description="LinkedIn Playwright Scraper V2")
    parser.add_argument("--pages", type=int, default=None, help="Số lượng trang cần cào. Mặc định là AUTO.")
    parser.add_argument("--keywords", type=str, default=None, help="Các từ khóa tìm kiếm cách nhau bởi dấu phẩy (vd: 'Data Engineer, Data Analyst')")
    
    args = parser.parse_args()
    
    # Xử lý danh sách từ khóa
    search_keywords = None
    if args.keywords:
        search_keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]

    scraper = LinkedInScraperV2()
    scraper.run(pages=args.pages, keywords=search_keywords)
