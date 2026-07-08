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

from bs4 import BeautifulSoup

from src.extract.job_online.base_scraper import BaseScraper
from src.utils import ensure_dir, get_date_str, generate_job_id


class LinkedInScraperV2(BaseScraper):
    source_name = "linkedin"
    base_url = "https://www.linkedin.com/jobs/search/?f_E=1%2C2%2C3&geoId=90010186"
    batch_size: int = 5

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("use_playwright", True)
        super().__init__(*args, **kwargs)
        self.username = os.getenv("LINKEDIN_USERNAME") or os.getenv("LINKEDIN_EMAIL")
        self.password = os.getenv("LINKEDIN_PASSWORD") or os.getenv("LINKEDIN_PASS")
        self.session_file = Path("data/linkedin_session.json")

    def _load_cookies(self) -> Optional[list[dict]]:
        """
        Tìm kiếm và load session cookies từ các file cấu hình.
        Hỗ trợ cả định dạng của Playwright (list of dict) và định dạng xuất ra từ Chrome Extension (dict chứa key 'cookies').
        """
        candidate_paths = [
            Path("data/linkedin_session.json"),
            Path("linkedin_session.json"),
        ]

        for path in candidate_paths:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    raw_cookies = []
                    if isinstance(data, list):
                        raw_cookies = data
                    elif isinstance(data, dict) and "cookies" in data:
                        raw_cookies = data["cookies"]
                    elif isinstance(data, dict):
                        # Dạng phẳng {name: value} từ curl_cffi
                        raw_cookies = [{"name": k, "value": v, "domain": ".linkedin.com", "path": "/"} for k, v in data.items()]
                    
                    # Convert to Playwright format and sanitize
                    playwright_cookies = []
                    for cookie in raw_cookies:
                        # Required fields
                        name = cookie.get("name")
                        value = cookie.get("value")
                        domain = cookie.get("domain")
                        if not name or not value or not domain:
                            continue
                            
                        formatted = {
                            "name": name,
                            "value": value,
                            "domain": domain,
                            "path": cookie.get("path", "/"),
                        }
                        
                        # Optional fields
                        if "secure" in cookie:
                            formatted["secure"] = bool(cookie["secure"])
                        if "httpOnly" in cookie:
                            formatted["httpOnly"] = bool(cookie["httpOnly"])
                        
                        # Handle expirationDate -> expires
                        expires = cookie.get("expires") or cookie.get("expirationDate")
                        if expires is not None:
                            try:
                                formatted["expires"] = float(expires)
                            except ValueError:
                                pass
                                
                        # Sanitize sameSite
                        same_site = cookie.get("sameSite")
                        if same_site:
                            same_site_lower = str(same_site).lower()
                            if "lax" in same_site_lower:
                                formatted["sameSite"] = "Lax"
                            elif "strict" in same_site_lower:
                                formatted["sameSite"] = "Strict"
                            elif "none" in same_site_lower or "no_restriction" in same_site_lower:
                                formatted["sameSite"] = "None"
                            # Skip if unspecified/invalid
                        
                        playwright_cookies.append(formatted)
                    
                    if playwright_cookies:
                        self.logger.info(f"Đã load thành công {len(playwright_cookies)} cookies từ {path}")
                        # Đồng bộ lưu lại bản định dạng chuẩn của Playwright để dùng sau này
                        # Tốt nhất lưu vào data/linkedin_session.json để được persist qua docker volume
                        standard_path = Path("data/linkedin_session.json")
                        try:
                            standard_path.parent.mkdir(parents=True, exist_ok=True)
                            with open(standard_path, "w", encoding="utf-8") as out_f:
                                json.dump(playwright_cookies, out_f, indent=2)
                            self.logger.info(f"Đã lưu cookie chuẩn Playwright vào {standard_path}")
                        except Exception as write_err:
                            self.logger.warning(f"Không thể ghi cookie chuẩn: {write_err}")
                            
                        return playwright_cookies
                except Exception as e:
                    self.logger.warning(f"Lỗi khi parse file cookie {path}: {e}")
        return None

    # ------------------------------------------------------------------
    # URL helpers
    # ------------------------------------------------------------------
    def get_list_page_url(self, page_num: int, keyword: Optional[str] = None) -> str:
        """Trả về URL phân trang LinkedIn. Hỗ trợ truyền keyword."""
        start = (page_num - 1) * 25

        parsed = urllib.parse.urlparse(self.base_url)
        query = urllib.parse.parse_qs(parsed.query)

        if keyword:
            query['keywords'] = [keyword]

        if start > 0:
            query['start'] = [str(start)]

        new_query = urllib.parse.urlencode(query, doseq=True)
        return urllib.parse.urlunparse(parsed._replace(query=new_query))

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------
    def _perform_login(self, page, context) -> bool:
        """Đăng nhập và tái sử dụng session cookie."""
        # Thử load session cũ
        cookies = self._load_cookies()
        if cookies:
            try:
                context.add_cookies(cookies)
                self.logger.info("Đã load session cookies từ file cấu hình.")

                page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
                
                # Cải thiện check đăng nhập: tìm avatar/menu của user đã login
                is_logged_in = False
                try:
                    page.wait_for_selector(".global-nav__me-photo, .global-nav__primary-items, #global-nav", timeout=5000)
                    is_logged_in = True
                except Exception:
                    pass

                if is_logged_in and ("feed" in page.url.lower() or "mynetwork" in page.url.lower()):
                    self.logger.info("Sử dụng session cũ thành công!")
                    return True
                else:
                    self.logger.info("Session cũ không hợp lệ hoặc đã hết hạn. Giữ lại cookie thiết bị và tiến hành đăng nhập bằng User/Pass...")
                    # KHÔNG context.clear_cookies() ở đây để giữ lại các cookie tracking (bcookie, lidc...)
                    # giúp LinkedIn nhận diện đây là thiết bị quen thuộc, giảm tỷ lệ dính Checkpoint/Captcha.
            except Exception as e:
                self.logger.warning(f"Lỗi load session: {e}")

        if not self.username or not self.password:
            self.logger.warning("Không tìm thấy thông tin tài khoản LinkedIn, cào không cần đăng nhập.")
            return False

        self.logger.info("Đang đăng nhập LinkedIn qua Playwright...")
        try:
            page.goto("https://www.linkedin.com/checkpoint/rm/sign-in-another-account", wait_until="domcontentloaded")
            page.wait_for_selector("#username", timeout=15000)

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

    # ------------------------------------------------------------------
    # Pagination helpers
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Job list scrolling
    # ------------------------------------------------------------------
    def _scroll_job_list(self, page) -> list[str]:
        """Cuộn danh sách job bên trái để tải hết job (virtual scrolling)."""
        self.logger.info("Bắt đầu tìm và cuộn danh sách job...")

        job_list_container = "#job-scraper-scroll-container"
        container_found = False

        for _ in range(15):
            container_found = page.evaluate("""() => {
                if (document.querySelector('#job-scraper-scroll-container')) return true;

                // Các container phổ biến của LinkedIn
                let commonContainers = [
                    '.jobs-search-results-list',
                    '.scaffold-layout__list',
                    '.scaffold-layout__list-container',
                    'div[aria-label="Search results"]'
                ];
                
                let scrollableEl = null;
                for (let sel of commonContainers) {
                    let el = document.querySelector(sel);
                    if (el && el.scrollHeight > el.clientHeight) {
                        scrollableEl = el;
                        break;
                    }
                }

                if (!scrollableEl) {
                    let card = document.querySelector('li.scaffold-layout__list-item, a.job-card-container__link, a.job-card-list__title--link, .job-card-container, a.base-card__full-link');
                    if (!card) return false;

                    let el = card.parentElement;
                    while (el && el !== document.body) {
                        const style = window.getComputedStyle(el);
                        if ((style.overflowY === 'auto' || style.overflowY === 'scroll') && el.scrollHeight > el.clientHeight) {
                            scrollableEl = el;
                            break;
                        }
                        el = el.parentElement;
                    }
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

                        job_id = None
                        
                        # Hỗ trợ /jobs/view/123456 hoặc /jobs/view/job-title-123456
                        m1 = re.search(r'/jobs/view/(?:.*?-)?(\d+)', href)
                        if m1:
                            job_id = m1.group(1)
                        else:
                            m2 = re.search(r'currentJobId=(\d+)', href)
                            if m2:
                                job_id = m2.group(1)
                            else:
                                m3 = re.search(r'jobId=(\d+)', href)
                                if m3:
                                    job_id = m3.group(1)
                        
                        if job_id:
                            collected_urls.add(f"https://www.linkedin.com/jobs/view/{job_id}/")
                        else:
                            self.logger.warning(f"URL không match regex: {href}")
                except (AttributeError, TypeError):
                    pass
                except KeyboardInterrupt:
                    raise

        extract_urls_from_page()
        self.logger.info(f"[Initial] Tìm thấy {len(collected_urls)} jobs trước cuộn")
        
        if len(collected_urls) == 0:
            # Ghi lại HTML để debug nếu không parse được link nào
            try:
                page.screenshot(path="debug_job_list_empty.png")
                links = page.query_selector_all("a.job-card-container__link, a.job-card-list__title--link, a.base-card__full-link")
                if links:
                    html_content = links[0].evaluate("el => el.outerHTML")
                    self.logger.warning(f"Ví dụ HTML của link không match:\n{html_content}")
            except Exception as e:
                self.logger.error(f"Lỗi khi debug HTML: {e}")

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

            try:
                page.wait_for_function(f"""() => {{
                    const links = document.querySelectorAll('a.job-card-container__link, a.job-card-list__title--link, a.base-card__full-link');
                    return links.length > {len(collected_urls)};
                }}""", timeout=1500)
            except Exception:
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
                            const links = document.querySelectorAll('a.job-card-container__link, a.job-card-list__title--link, a.base-card__full-link');
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

    # ------------------------------------------------------------------
    # Collect URLs (Phase 1)
    # ------------------------------------------------------------------
    def _collect_urls(self, pages: Optional[int] = None, keywords: Optional[List[str]] = None) -> list[str]:
        """Thu thập URL dựa trên keyword."""
        from patchright.sync_api import sync_playwright

        max_pages = self._resolve_pages(pages)
        all_urls: list[str] = []
        seen_urls: set[str] = set()

        search_keywords = keywords if keywords else [None]

        self.logger.info("Khởi tạo trình duyệt Playwright...")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
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
                            "a.job-card-container__link, a.job-card-list__title--link, a.base-card__full-link",
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

    # ------------------------------------------------------------------
    # Playwright: fetch job detail page
    # ------------------------------------------------------------------
    def _fetch_job_detail_with_playwright(self, url: str, context) -> Optional[dict]:
        """
        Mở trang chi tiết job bằng Playwright, bấm 'Xem thêm'/'Show more'
        để hiện toàn bộ mô tả, sau đó trả về dict job đã parse.
        """
        page = context.new_page()
        try:
            self.logger.info(f"[Phase 3] Fetching: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=45000)

            # Đợi tiêu đề job xuất hiện
            try:
                page.wait_for_selector(
                    "h1, h2, .jobs-unified-top-card__job-title, .top-card-layout__title, .topcard__title",
                    timeout=5000
                )
            except Exception:
                self.logger.warning(f"Timeout chờ tiêu đề job tại {url}")

            # Click nút "Xem thêm" / "Show more" để mở rộng mô tả
            show_more_selectors = [
                # LinkedIn authenticated job detail
                "button[aria-label*='more']",
                "button.jobs-description__footer-button",
                "button[data-tracking-control-name*='show-more']",
                # expandable text box button
                "button.inline-show-more-text__button",
                "button.show-more-less-html__button",
                "button.show-more-less-html__button--more",
                # XPaths
                "xpath=//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'show more')]",
                "xpath=//button[contains(., 'Xem thêm')]",
                "xpath=//button[contains(., 'Hiển thị thêm')]",
                "xpath=//button[contains(., 'more')]",
            ]
            for sel in show_more_selectors:
                try:
                    btn = page.query_selector(sel)
                    if btn and btn.is_visible():
                        btn.click()
                        time.sleep(0.8)
                        self.logger.debug(f"Clicked 'show more' with selector: {sel}")
                        break
                except Exception:
                    continue

            # Đợi thêm để JS render xong
            time.sleep(1.0)

            # Lấy company info (cần navigate sang trang công ty)
            company_info = None
            company_website = None
            company_url = None

            # Tìm link công ty
            try:
                co_link_el = page.query_selector(
                    "a.app-aware-link[href*='/company/'], "
                    "a[href*='/company/']"
                )
                if co_link_el:
                    company_url = co_link_el.get_attribute("href") or ""
                    if company_url.startswith("/"):
                        company_url = "https://www.linkedin.com" + company_url
            except Exception:
                pass

            if company_url:
                company_info, company_website = self._fetch_company_info(company_url, context)

            # Lấy toàn bộ HTML để parse
            html = page.content()
            job = self.parse_job_detail(html, url)
            if company_info:
                job["company_info"] = company_info
            if company_website:
                job["company_website"] = company_website

            return job

        except KeyboardInterrupt:
            raise
        except Exception as e:
            self.logger.error(f"Lỗi fetch chi tiết job {url}: {e}")
            return None
        finally:
            try:
                page.close()
            except Exception:
                pass

    def _fetch_company_info(self, company_url: str, context) -> tuple[Optional[str], Optional[str]]:
        """
        Điều hướng sang trang /about/ của công ty để lấy mô tả và website.
        Trả về (company_info_text, company_website).
        """
        about_url = re.sub(r'/life/?$', '/about/', company_url)
        about_url = re.sub(r'/(?:posts|jobs|people)?/?$', '/about/', about_url)
        if not about_url.endswith('/about/'):
            about_url = about_url.rstrip('/') + '/about/'

        page = context.new_page()
        try:
            page.goto(about_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(1.5)

            # Bấm "Hiển thị tất cả chi tiết" nếu có
            try:
                see_all_btn = page.query_selector(
                    "a[aria-label*='chi tiết'], "
                    "a[aria-label*='details'], "
                    "a.org-module-card__footer-hoverable"
                )
                if see_all_btn:
                    see_all_btn.click()
                    time.sleep(1.0)
            except Exception:
                pass

            html = page.content()
            soup = BeautifulSoup(html, "html.parser")

            company_info = None
            website = None

            # Lấy mô tả công ty
            desc_selectors = [
                "p.break-words.white-space-pre-wrap",
                "p[class*='break-words']",
                ".org-about-us-organization-description",
                ".org-about-module__description",
                "[data-test-id='about-us__description']",
            ]
            for sel in desc_selectors:
                el = soup.select_one(sel)
                if el:
                    company_info = el.get_text(separator="\n", strip=True)
                    if company_info:
                        break

            # Lấy website công ty
            website_selectors = [
                "span.link-without-visited-state",
                "a[href*='http'][data-tracking-control-name*='website']",
                ".org-about-us-organization-description__website a",
            ]
            for sel in website_selectors:
                el = soup.select_one(sel)
                if el:
                    text = el.get_text(strip=True)
                    if text.startswith("http"):
                        website = text
                        break
                    href = el.get("href", "")
                    if href.startswith("http"):
                        website = href
                        break

            return company_info, website

        except Exception as e:
            self.logger.warning(f"Không lấy được thông tin công ty từ {about_url}: {e}")
            return None, None
        finally:
            try:
                page.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Parse detail HTML (BeautifulSoup)
    # ------------------------------------------------------------------
    def parse_job_detail(self, detail_html: str, url: str) -> dict:
        """Parse HTML trang chi tiết job LinkedIn, tách các trường bằng BeautifulSoup + regex."""
        soup = BeautifulSoup(detail_html, "html.parser")

        # --- Tên job ---
        title = None
        title_selectors = [
            "h1.jobs-unified-top-card__job-title",
            "h1.top-card-layout__title",
            "h1",
        ]
        for sel in title_selectors:
            el = soup.select_one(sel)
            if el:
                title = el.get_text(strip=True)
                if title:
                    break

        # --- Tên công ty ---
        company = None
        company_selectors = [
            ".jobs-unified-top-card__company-name a",
            ".jobs-unified-top-card__company-name",
            ".topcard__org-name-link",
            "a[data-tracking-control-name*='company']",
            ".top-card-layout__card a",
        ]
        for sel in company_selectors:
            el = soup.select_one(sel)
            if el:
                company = el.get_text(strip=True)
                if company:
                    break

        # --- Địa chỉ ---
        location = None
        location_selectors = [
            ".jobs-unified-top-card__bullet",
            ".jobs-unified-top-card__workplace-type",
            ".topcard__flavor--bullet",
            "span[class*='_34c2f5bd']",
        ]
        for sel in location_selectors:
            elements = soup.select(sel)
            for el in elements:
                text = el.get_text(strip=True)
                # Lọc ra text có vẻ là địa chỉ (chứa dấu phẩy hoặc city/country)
                if text and (',' in text or any(kw in text.lower() for kw in
                             ['hanoi', 'hà nội', 'ho chi minh', 'hồ chí minh', 'vietnam', 'việt nam',
                              'district', 'quận', 'tây hồ', 'đống đa'])):
                    location = text
                    break
            if location:
                break

        # Fallback: lấy span đầu tiên có dạng địa chỉ
        if not location:
            for span in soup.find_all("span"):
                text = span.get_text(strip=True)
                if text and ',' in text and len(text) < 100:
                    if any(kw in text.lower() for kw in
                           ['hanoi', 'hà nội', 'ho chi', 'vietnam', 'việt']):
                        location = text
                        break

        # --- Loại công việc (On-site, Remote, Hybrid) ---
        job_type = None
        job_type_selectors = [
            ".jobs-unified-top-card__workplace-type",
            "span[class*='_3d4c77c2 e7046641']",
        ]
        workplace_keywords = {"on-site", "remote", "hybrid", "tại văn phòng", "làm việc từ xa", "kết hợp"}
        for sel in job_type_selectors:
            elements = soup.select(sel)
            for el in elements:
                text = el.get_text(strip=True).lower()
                if any(kw in text for kw in workplace_keywords):
                    job_type = el.get_text(strip=True)
                    break
            if job_type:
                break

        # --- Cấp bậc ---
        job_position = None
        seniority_keywords = {
            "thực tập", "intern", "entry level", "junior", "mid-senior",
            "senior", "director", "executive", "associate", "manager"
        }
        # Tìm trong các thẻ span có class ngắn
        for span in soup.find_all("span"):
            text = span.get_text(strip=True).lower()
            if any(kw in text for kw in seniority_keywords):
                job_position = span.get_text(strip=True)
                break

        # --- Mô tả công việc (raw text) ---
        description_text = None
        desc_selectors = [
            ".jobs-description__content",
            ".jobs-description-content__text",
            "#job-details",
            ".description__text",
            "[data-testid='expandable-text-box']",
            ".show-more-less-html__markup",
        ]
        for sel in desc_selectors:
            el = soup.select_one(sel)
            if el:
                description_text = el.get_text(separator="\n", strip=True)
                if description_text:
                    break

        # --- Lương (từ header card) ---
        salary = None
        salary_selectors = [
            ".jobs-unified-top-card__job-insight span",
            ".salary",
            "[class*='salary']",
        ]
        salary_patterns = [
            r'[\$\€\£][\d,\.]+(?:\s*[-–]\s*[\$\€\£]?[\d,\.]+)?(?:\s*/\s*(?:hr|hour|month|year|tháng|năm))?',
            r'\d+[\.,]\d+\s*(?:triệu|million|k|nghìn)\s*(?:VNĐ|VND|đ|USD)?',
            r'(?:lương|salary|mức lương|thu nhập)\s*:?\s*([^\n]{5,60})',
        ]
        for sel in salary_selectors:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(strip=True)
                for pat in salary_patterns:
                    m = re.search(pat, text, re.IGNORECASE)
                    if m:
                        salary = m.group(0).strip()
                        break
            if salary:
                break

        # --- Trích xuất từ mô tả ---
        experience = None
        deadline = None
        requirements = None
        benefits = None

        if description_text:
            experience = self._extract_experience(description_text)
            deadline = self._extract_deadline(description_text)
            requirements = self._extract_requirements(description_text)
            benefits = self._extract_benefits(description_text)

        # --- Lương từ mô tả (nếu chưa có) ---
        if not salary and description_text:
            salary = self._extract_salary_from_desc(description_text)
            
        # --- Job Type fallback từ mô tả (nếu chưa có) ---
        if not job_type and description_text:
            m = re.search(r'(?i)\b(full[- ]time|part[- ]time|contract|freelance|internship|remote|hybrid|on[- ]site|toàn thời gian|bán thời gian)\b', description_text[:1000])
            if m:
                job_type = m.group(1).title()

        return {
            "title": title,
            "company": company,
            "salary": salary,
            "location": location,
            "experience_level": experience,
            "job_type": job_type,
            "job_industry": None,
            "job_position": job_position,
            "job_description": description_text,
            "requirements": requirements,
            "benefits": benefits,
            "job_deadline": deadline,
            "company_info": None,      # Sẽ được điền bởi _fetch_job_detail_with_playwright
            "company_website": None,   # Sẽ được điền bởi _fetch_job_detail_with_playwright
            "job_url": url,
            "source": "linkedin",
            "scraped_at": datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------
    # Regex extraction helpers (bilingual VI + EN)
    # ------------------------------------------------------------------

    def _extract_experience(self, text: str) -> Optional[str]:
        """Trích xuất yêu cầu kinh nghiệm từ mô tả công việc."""
        patterns = [
            # Vietnamese
            r'(?:từ\s+|tối\s+thiểu\s+|ít\s+nhất\s+)?(\d+\s*[-–~]\s*\d+|\d+\+?)\s*năm(?:\s+kinh\s+nghiệm| \s+làm\s+việc)?',
            r'kinh\s+nghiệm\s*:?\s*(?:từ\s+|tối\s+thiểu\s+|ít\s+nhất\s+)?(\d+\s*[-–~]\s*\d+|\d+\+?)\s*năm?',
            r'(?:có|yêu\s+cầu)?\s*(?:ít\s+nhất|tối\s+thiểu)?\s*(\d+\s*[-–~]\s*\d+|\d+\+?)\s*năm\s+(?:kinh\s+nghiệm|làm\s+việc)',
            # English
            r'(\d+\s*[-–~]\s*\d+|\d+\+?)\s*years?(?:\s+of)?\s+(?:working\s+|relevant\s+)?experience',
            r'(?:minimum|at\s+least|min\.?)\s+(\d+)\s*\+?\s*years?(?:\s+of)?\s+(?:working\s+|relevant\s+)?experience',
            r'experience\s*:?\s*(?:minimum\s+)?(\d+\s*[-–~]\s*\d+|\d+\+?)\s*years?',
            r'(\d+)\+?\s*years?(?:\s+of)?\s+(?:relevant\s+)?experience',
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                snippet = m.group(0).strip()
                snippet = re.sub(r'\s+', ' ', snippet)
                return snippet
        return None

    def _extract_deadline(self, text: str) -> Optional[str]:
        """Trích xuất hạn nộp hồ sơ từ mô tả công việc."""
        patterns = [
            # Vietnamese: "Hạn nộp hồ sơ: 30/06/2026" or "Hạn ứng tuyển: ..."
            r'(?:hạn\s+(?:nộp\s+hồ\s+sơ|ứng\s+tuyển|apply)|deadline)\s*:?\s*([\d/\.\-]+(?:\s+\w+)?)',
            r'(?:nộp hồ sơ|ứng tuyển) trước\s+(?:ngày\s+)?([0-9]{1,2}[/\.\-][0-9]{1,2}[/\.\-][0-9]{2,4})',
            # English: "Apply by June 30, 2026" or "Deadline: 2026-06-30"
            r'(?:apply\s+by|deadline|closing\s+date|applications?\s+close(?:s)?(?:\s+on)?)\s*:?\s*'
            r'((?:\d{1,2}[/\.\-]\d{1,2}[/\.\-]\d{2,4})|(?:\w+\s+\d{1,2},?\s+\d{4}))',
            # Date formats: DD/MM/YYYY, YYYY-MM-DD
            r'(?:before|by|trước)\s+(\d{1,2}[/\.\-]\d{1,2}[/\.\-]\d{2,4})',
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None

    def _extract_requirements(self, text: str) -> Optional[str]:
        """
        Trích xuất phần Yêu cầu / Requirements từ mô tả.
        Giữ nguyên đoạn văn để không mất thông tin.
        """
        # Tìm header yêu cầu bằng tiếng Việt hoặc tiếng Anh
        vi_headers = [
            r'(?:\*\s*)?yêu\s+cầu\s*(?:công\s+việc|ứng\s+viên|kinh\s+nghiệm)?\s*:?',
            r'(?:\*\s*)?tiêu\s+chuẩn\s*(?:ứng\s+viên)?\s*:?',
            r'(?:\*\s*)?kỹ\s+năng\s*(?:yêu\s+cầu|cần\s+thiết)?\s*:?',
            r'(?:\*\s*)?chân\s+dung\s+ứng\s+viên\s*:?'
        ]
        en_headers = [
            r'(?:\*\s*)?(?:job\s+)?requirements?\s*:?',
            r'(?:\*\s*)?(?:basic\s+|minimum\s+|preferred\s+)?qualifications?\s*:?',
            r'(?:\*\s*)?what\s+(?:we|you)(?:\'ll)?\s+(?:need|look\s+for|require|bring)\s*:?',
            r'(?:\*\s*)?(?:required|essential|key)\s+skills?\s*:?',
            r'(?:\*\s*)?skills?\s+(?:and\s+)?(?:requirements?|qualifications?|experience)?\s*:?',
            r'(?:\*\s*)?your\s+(?:profile|background|skills)\s*:?',
            r'(?:\*\s*)?who\s+you\s+are\s*:?',
        ]

        all_headers = vi_headers + en_headers
        header_pattern = '|'.join(f'(?:{h})' for h in all_headers)

        # Tìm vị trí của header yêu cầu
        m_start = re.search(header_pattern, text, re.IGNORECASE)
        if not m_start:
            return None

        # Tìm vị trí của section tiếp theo (quyền lợi, phúc lợi, v.v.)
        next_section_patterns = [
            r'(?:\*\s*)?(?:quyền\s+lợi|phúc\s+lợi|chế\s+độ|đãi\s+ngộ)\s*:?',
            r'(?:\*\s*)?(?:benefits?|perks?|what\s+we\s+offer|compensation)\s*:?',
            r'(?:\*\s*)?(?:nộp\s+hồ\s+sơ|cách\s+apply|how\s+to\s+apply)\s*:?',
            r'(?:\*\s*)?(?:quá\s+trình\s+tuyển\s+dụng|interview\s+process)\s*:?',
        ]
        next_section_re = '|'.join(f'(?:{p})' for p in next_section_patterns)
        m_end = re.search(next_section_re, text[m_start.end():], re.IGNORECASE)

        if m_end:
            req_text = text[m_start.end(): m_start.end() + m_end.start()]
        else:
            # Lấy tối đa 2000 ký tự
            req_text = text[m_start.end(): m_start.end() + 2000]

        req_text = req_text.strip()
        return req_text if req_text else None

    def _extract_benefits(self, text: str) -> Optional[str]:
        """
        Trích xuất phần Quyền lợi / Benefits từ mô tả.
        """
        vi_headers = [
            r'(?:\*\s*)?quyền\s+lợi\s*(?:được\s+hưởng)?\s*:?',
            r'(?:\*\s*)?phúc\s+lợi\s*:?',
            r'(?:\*\s*)?chế\s+độ\s*(?:đãi\s+ngộ|làm\s+việc|phúc\s+lợi)?\s*:?',
            r'(?:\*\s*)?đãi\s+ngộ\s*:?',
            r'(?:\*\s*)?tại\s+sao\s+(?:chọn|nên\s+làm\s+việc\s+tại)\s+.*?:?',
        ]
        en_headers = [
            r'(?:\*\s*)?benefits?\s*:?',
            r'(?:\*\s*)?perks?(?:\s+and\s+benefits?)?\s*:?',
            r'(?:\*\s*)?what\s+(?:we|you)\s+offer\s*:?',
            r'(?:\*\s*)?compensation\s+(?:and\s+benefits?)?\s*:?',
            r'(?:\*\s*)?why\s+(?:join\s+us|you\'ll\s+love\s+working\s+here)\s*:?',
            r'(?:\*\s*)?what\'s\s+in\s+it\s+for\s+you\s*:?',
        ]

        all_headers = vi_headers + en_headers
        header_pattern = '|'.join(f'(?:{h})' for h in all_headers)

        m_start = re.search(header_pattern, text, re.IGNORECASE)
        if not m_start:
            return None

        # Tìm section tiếp theo
        next_section_patterns = [
            r'(?:\*\s*)?nộp\s+hồ\s+sơ\s*:?',
            r'(?:\*\s*)?cách\s+(?:nộp|apply)\s*:?',
            r'how\s+to\s+apply\s*:?',
            r'(?:\*\s*)?liên\s+hệ\s*:?',
            r'contact\s+us\s*:?',
        ]
        next_section_re = '|'.join(f'(?:{p})' for p in next_section_patterns)
        m_end = re.search(next_section_re, text[m_start.end():], re.IGNORECASE)

        if m_end:
            ben_text = text[m_start.end(): m_start.end() + m_end.start()]
        else:
            ben_text = text[m_start.end(): m_start.end() + 1500]

        ben_text = ben_text.strip()
        return ben_text if ben_text else None

    def _extract_salary_from_desc(self, text: str) -> Optional[str]:
        """Trích xuất thông tin lương từ mô tả công việc."""
        patterns = [
            # Vietnamese
            r'(?:lương|mức\s+lương|thu\s+nhập|thù\s+lao|mức\s+thu\s+nhập)\s*:?\s*([A-Za-z0-9\s,\.\-~]+(?:triệu|tr|triệu/tháng|vnd|vnđ|usd|\$))',
            r'(?:lương|mức\s+lương|thu\s+nhập|thù\s+lao)\s*[:\-]?\s*upto\s+[^\n]{2,30}',
            r'(?:lương|mức\s+lương|thu\s+nhập|thù\s+lao)\s*[:\-]?\s*(?:thỏa\s+thuận|cạnh\s+tranh|negotiable)',
            r'(?:\d+[\.,]\d+\s*[-–~]\s*\d+[\.,]\d+)\s*(?:triệu|million|tr|k)\s*(?:VNĐ|VND|đ|VND/tháng|usd)?',
            r'(?:\d+\s*[-–~]\s*\d+)\s*(?:triệu|million|tr|k)\s*(?:VNĐ|VND|đ|VND/tháng|usd)?',
            # English
            r'(?:salary|compensation|pay|remuneration)\s*[:\-]?\s*([^\n]{5,80})',
            r'[\$\€\£]\s*[\d,\.]+(?:\s*[-–~]\s*[\$\€\£]?\s*[\d,\.]+)?\s*(?:/\s*(?:hr|hour|month|year|yr|tháng|năm))?',
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                snippet = m.group(0).strip()
                # Loại bỏ header keyword
                snippet = re.sub(
                    r'^(?:lương|mức\s+lương|thu\s+nhập|thù\s+lao|mức\s+thu\s+nhập|salary|compensation|pay|remuneration)\s*[:\-]?\s*',
                    '', snippet, flags=re.IGNORECASE
                ).strip()
                if snippet:
                    return snippet
        return None

    # ------------------------------------------------------------------
    # Stub (not used in V2)
    # ------------------------------------------------------------------
    def extract_job_urls(self, list_page_html: str) -> list[str]:
        raise NotImplementedError("Không sử dụng trong V2.")

    # ------------------------------------------------------------------
    # Save links
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Main run (full pipeline: URL + detail scraping)
    # ------------------------------------------------------------------
    def run(
        self,
        pages: Optional[int] = None,
        existing_urls: Optional[set] = None,
        keywords: Optional[List[str]] = None,
    ) -> list[dict]:
        from src.utils import get_date_str as _gds
        from datetime import datetime as _dt
        from playwright.sync_api import sync_playwright

        pages_label = str(pages) if pages is not None else "AUTO (hết trang)"
        kw_label = ", ".join(keywords) if keywords else "Mặc định"

        self.logger.info(
            f"=== BẮT ĐẦU scraper [{self.source_name}] | pages={pages_label} | Keywords: {kw_label} ==="
        )
        start_time = _dt.now()
        date_str = _gds(start_time)

        # Phase 1: Thu thập URLs
        self.logger.info("[Phase 1] Bắt đầu thu thập URL từ trang danh sách...")
        raw_urls = self._collect_urls(pages, keywords=keywords)
        urls = self._deduplicate_urls(raw_urls, existing_urls)

        if not urls:
            self.logger.info("[Phase 1] Không có URL mới để cào. Kết thúc.")
            return []

        self.save_links(urls, date_str)

        # Phase 3: Fetch + parse chi tiết từng job
        self.logger.info(f"[Phase 3] Bắt đầu fetch chi tiết {len(urls)} jobs...")
        results: list[dict] = []

        with sync_playwright() as p:
            is_headless = os.getenv("SCRAPER_HEADLESS", "true").lower() == "true" or os.path.exists("/.dockerenv")
            browser = p.chromium.launch(
                headless=is_headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            )

            # Load session cookies
            cookies = self._load_cookies()
            if cookies:
                try:
                    context.add_cookies(cookies)
                except Exception as e:
                    self.logger.warning(f"Không load được session cho detail phase: {e}")

            for i, url in enumerate(urls, 1):
                self.logger.info(f"[Phase 3] ({i}/{len(urls)}) {url}")
                try:
                    job = self._fetch_job_detail_with_playwright(url, context)
                    if job:
                        job.setdefault("source", self.source_name)
                        job.setdefault("job_url", url)
                        job.setdefault("scraped_at", datetime.now().isoformat())
                        job.setdefault("job_id", generate_job_id(self.source_name, url))
                        results.append(job)
                        self.logger.info(f"[Phase 3] ✓ Parsed: {job.get('title', 'N/A')} @ {job.get('company', 'N/A')}")
                except KeyboardInterrupt:
                    self.logger.info("Bị ngắt bởi người dùng. Lưu kết quả hiện tại...")
                    break
                except Exception as e:
                    self.logger.error(f"[Phase 3] Lỗi xử lý {url}: {e}")

                # Delay giữa các request để tránh rate limit
                if i < len(urls):
                    delay = random.uniform(2.0, 4.0)
                    time.sleep(delay)

            browser.close()

        # Lưu kết quả
        if results:
            self.save_raw(results, date_str)

        elapsed = (_dt.now() - start_time).total_seconds()
        self.logger.info(
            f"=== XONG [{self.source_name}] | {len(results)} jobs | {elapsed:.1f}s ==="
        )
        return results


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
    parser.add_argument("--keywords", type=str, default=None,
                        help="Các từ khóa tìm kiếm cách nhau bởi dấu phẩy (vd: 'Data Engineer, Data Analyst')")

    args = parser.parse_args()

    search_keywords = None
    if args.keywords:
        search_keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]

    scraper = LinkedInScraperV2()
    scraper.run(pages=args.pages, keywords=search_keywords)
