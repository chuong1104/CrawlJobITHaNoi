import os
from datetime import datetime
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from scrapling.parser import Adaptor

from src.extract.job_online.base_scraper import BaseScraper


class Job123Scraper(BaseScraper):

    _block_media = BaseScraper._block_media
    source_name = "123job"
    base_url = "https://123job.vn"
    batch_size = 10

    # URL tìm việc IT phần mềm tại Hà Nội, sắp xếp mới nhất
    DEFAULT_START_URL = (
        "https://123job.vn/tuyen-dung?cat=IT+ph%E1%BA%A7n+m%E1%BB%81m"
        "&sort=new&cityId=1&l=H%C3%A0+N%E1%BB%99i"
    )

    def __init__(self, start_url: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.start_url = self._canonicalize_list_url(start_url or self.DEFAULT_START_URL)

    # ------------------------------------------------------------------
    # URL helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _canonicalize_list_url(url: str) -> str:
        parsed = urlparse(url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        keep_keys = {"cat", "l", "sort", "cityId", "page"}
        filtered = {
            key: value
            for key, value in query.items()
            if key in keep_keys and value and value[0] != ""
        }
        new_query = urlencode(filtered, doseq=True)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", new_query, ""))

    @staticmethod
    def _canonicalize_detail_url(url: str) -> str:
        parsed = urlparse(url)
        # Chỉ giữ path, bỏ query params không cần thiết
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

    def _to_absolute_detail_url(self, url: str) -> str:
        full_url = urljoin(self.base_url, (url or "").strip())
        return self._canonicalize_detail_url(full_url)

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------
    def get_list_page_url(self, page_num: int) -> str:
        parsed = urlparse(self.start_url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        if page_num <= 1:
            query.pop("page", None)
        else:
            query["page"] = [str(page_num)]
        new_query = urlencode(query, doseq=True)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", new_query, ""))

    def get_next_page_url(
        self,
        list_page_html: str,
        page_num: int,
        current_url: str,
    ) -> str | None:
        page = Adaptor(list_page_html)
        # Thử tìm nút Next trong pagination
        next_href = page.css("ul.pagination-listing li a[aria-label='Next']::attr(href)").get()
        if not next_href:
            next_href = page.css("a.next-page::attr(href)").get()
        if next_href:
            return urljoin(self.base_url, next_href)
        return self.get_list_page_url(page_num + 1)

    # ------------------------------------------------------------------
    # Phase 1: Extract job URLs from list page
    # ------------------------------------------------------------------
    def extract_job_urls(self, list_page_html: str) -> list[str]:
        page = Adaptor(list_page_html)
        candidate_urls: list[str] = []

        # Selector chính xác của 123job list page
        candidate_urls.extend(page.css("h2.job__list-item-title a::attr(href)").getall())
        # Fallback: mọi link có /viec-lam/ trong href
        candidate_urls.extend(page.css("a[href*='/viec-lam/']::attr(href)").getall())

        links: list[str] = []
        seen: set[str] = set()
        for raw in candidate_urls:
            if not raw:
                continue
            canonical = self._to_absolute_detail_url(raw)
            if "/viec-lam/" not in canonical:
                continue
            if canonical not in seen:
                seen.add(canonical)
                links.append(canonical)

        return links

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _get_text(page: Adaptor, selector: str) -> str | None:
        """Lấy text từ selector đầu tiên khớp, strip whitespace."""
        el = page.css(selector)
        if not el:
            return None
        parts = el.css("::text").getall()
        text = " ".join(p.strip() for p in parts if p and p.strip())
        return text or None

    @staticmethod
    def _get_block_text(page: Adaptor, selector: str) -> str | None:
        """Lấy toàn bộ inner text (multi-line) của một block section."""
        el = page.css(selector)
        if not el:
            return None
        parts = el.css("::text").getall()
        lines = [p.strip() for p in parts if p and p.strip()]
        return "\n".join(lines) or None

    @staticmethod
    def _find_attr_item(page: Adaptor, icon_class: str) -> str | None:
        """
        Tìm .attr-item chứa icon với class `icon_class`,
        trả về text trong .text-attr (hoặc .value span).
        """
        for item in page.css("div.attr-item"):
            icon = item.css(f"i.{icon_class}")
            if icon:
                # Thử .text-attr trước (dạng mới)
                val = item.css(".text-attr::text").get()
                if val and val.strip():
                    return val.strip()
                # Fallback: .value span
                val = item.css(".value span::text").get()
                if val and val.strip():
                    return val.strip()
        return None

    # ------------------------------------------------------------------
    # Phase 3: Parse job detail page
    # ------------------------------------------------------------------
    def parse_job_detail(self, detail_html: str, url: str) -> dict:
        page = Adaptor(detail_html)

        # ── Tên job ─────────────────────────────────────────────────────
        # <h1 class="js-job job-title"><strong>...</strong></h1>
        title_el = page.css("h1.job-title")
        if not title_el:
            title_el = page.css("h1.js-job")
        title = None
        if title_el:
            parts = title_el.css("::text").getall()
            title = " ".join(p.strip() for p in parts if p.strip()) or None

        # ── Tên công ty ─────────────────────────────────────────────────
        # <div class="d-flex justify-between"><span class="text-normal">CÔNG TY...</span></div>
        company = None
        company_el = page.css("div.d-flex.justify-between span.text-normal")
        if company_el:
            company = company_el.css("::text").get()
            if company:
                company = company.strip() or None
        if not company:
            # Fallback: link công ty
            for sel in [
                "a[href*='/company/']::text",
                "a[href*='/cong-ty/']::text",
                "p.company-name::text",
            ]:
                val = page.css(sel).get()
                if val and val.strip():
                    company = val.strip()
                    break

        # ── Địa chỉ ─────────────────────────────────────────────────────
        # attr-item với icon la-map-marker, value trong .value span
        location = self._find_attr_item(page, "la-map-marker")
        if not location:
            # Fallback: tìm trực tiếp
            for item in page.css("div.attr-item"):
                label = item.css(".text span:not(.icon-attr-header)::text").get()
                if label and "địa điểm" in label.lower():
                    val = item.css(".value span::text").get()
                    if val and val.strip():
                        location = val.strip()
                        break

        # ── Lương ────────────────────────────────────────────────────────
        # attr-item với icon la-money
        salary = self._find_attr_item(page, "la-money")

        # ── Kinh nghiệm ─────────────────────────────────────────────────
        # <div class="d-flex align-items-center mb-2">
        #   <i class="cli-suitcase-simple ..."></i>
        #   <span>2 - 5 năm kinh nghiệm</span>
        # </div>
        experience = None
        for item_div in page.css("div.d-flex.align-items-center.mb-2"):
            icon = item_div.css("i.cli-suitcase-simple")
            if icon:
                span_text = item_div.css("span::text").get()
                if span_text and span_text.strip():
                    experience = span_text.strip()
                break

        # ── Hạn ứng tuyển ────────────────────────────────────────────────
        # attr-item với icon la-clock-o, value trong .text-attr
        deadline = self._find_attr_item(page, "la-clock-o")
        if not deadline:
            for item in page.css("div.attr-item"):
                label_div = item.css(".name-attr::text").get()
                if label_div and "hạn nộp" in label_div.lower():
                    val = item.css(".text-attr::text").get()
                    if val and val.strip():
                        deadline = val.strip()
                        break

        # ── Cấp bậc ──────────────────────────────────────────────────────
        # attr-item với icon la-arrow-up
        job_position = self._find_attr_item(page, "la-arrow-up")
        if not job_position:
            for item in page.css("div.attr-item"):
                label_div = item.css(".name-attr::text").get()
                if label_div and "cấp bậc" in label_div.lower():
                    val = item.css(".text-attr::text").get()
                    if val and val.strip():
                        job_position = val.strip()
                        break

        # ── Hình thức làm việc ───────────────────────────────────────────
        # attr-item với icon la-briefcase
        job_type = self._find_attr_item(page, "la-briefcase")
        if not job_type:
            for item in page.css("div.attr-item"):
                label_div = item.css(".name-attr::text").get()
                if label_div and "hình thức" in label_div.lower():
                    val = item.css(".text-attr::text").get()
                    if val and val.strip():
                        job_type = val.strip()
                        break

        # ── Ngành nghề ───────────────────────────────────────────────────
        # attr-item với icon la-bookmark
        job_industry = self._find_attr_item(page, "la-bookmark")
        if not job_industry:
            for item in page.css("div.attr-item"):
                label_div = item.css(".name-attr::text").get()
                if label_div and "ngành nghề" in label_div.lower():
                    val = item.css(".text-attr::text").get()
                    if val and val.strip():
                        job_industry = val.strip()
                        break

        # ── Mô tả công việc ──────────────────────────────────────────────
        job_description = None
        for group in page.css("div.content-group"):
            heading = group.css("h2.content-group__title::text").get() or ""
            if "mô tả" in heading.lower():
                job_description = self._get_block_text(group, ".content-group__content")
                break
        if not job_description:
            job_description = self._get_block_text(page, "div.content-group:first-of-type .content-group__content")

        # ── Phúc lợi / Quyền lợi ────────────────────────────────────────
        benefits = None
        for group in page.css("div.content-group"):
            heading = group.css("h2.content-group__title::text").get() or ""
            if "quyền lợi" in heading.lower() or "phúc lợi" in heading.lower():
                benefits = self._get_block_text(group, ".content-group__content")
                break

        # ── Kỹ năng / Yêu cầu ───────────────────────────────────────────
        requirements = None
        for group in page.css("div.content-group"):
            heading = group.css("h2.content-group__title::text").get() or ""
            if "yêu cầu" in heading.lower() or "kỹ năng" in heading.lower():
                requirements = self._get_block_text(group, ".content-group__content")
                break

        # ── Fallback trích xuất thông minh từ mô tả nếu bị rỗng ───────────
        if job_description:
            # Nếu requirements rỗng, thử tìm phần "YÊU CẦU" trong text mô tả
            if not requirements:
                req_parts = []
                started = False
                for line in job_description.split("\n"):
                    if "yêu cầu" in line.lower() or "yêu cầu công việc" in line.lower():
                        started = True
                        continue
                    if started:
                        if "quyền lợi" in line.lower() or "phúc lợi" in line.lower() or "mô tả công việc" in line.lower():
                            break
                        req_parts.append(line)
                if req_parts:
                    requirements = "\n".join(req_parts).strip()

            # Nếu benefits rỗng, thử tìm phần "QUYỀN LỢI" hoặc "PHÚC LỢI" trong mô tả
            if not benefits:
                ben_parts = []
                started = False
                for line in job_description.split("\n"):
                    if "quyền lợi" in line.lower() or "phúc lợi" in line.lower() or "chế độ" in line.lower():
                        started = True
                        continue
                    if started:
                        if "yêu cầu" in line.lower() or "mô tả công việc" in line.lower():
                            break
                        ben_parts.append(line)
                if ben_parts:
                    benefits = "\n".join(ben_parts).strip()

        # ── Thông tin công ty & Website từ trang công ty riêng biệt ────────
        company_info = None
        company_website = None

        company_url_raw = page.css("div.company-url a::attr(href)").get()
        if company_url_raw:
            company_url = urljoin(self.base_url, company_url_raw.strip())
            self.logger.info(f"Fetching company page for info: {company_url}")
            comp_html = self._fetch_html(company_url)
            if comp_html:
                comp_page = Adaptor(comp_html)
                # Lấy thông tin giới thiệu công ty ở introduce-left
                company_info = self._get_block_text(comp_page, "div.introduce-left .introduce-content")
                if not company_info:
                    company_info = self._get_block_text(comp_page, "div.introduce-content")
                if not company_info:
                    company_info = self._get_block_text(comp_page, ".content-wrap")

                # Lấy website công ty ở trang công ty
                for intro_item in comp_page.css("div.introduce-item"):
                    label = intro_item.css(".item-text::text").get() or ""
                    if "website" in label.lower():
                        val = intro_item.css(".item-value::text").get()
                        if val and val.strip() and val.strip().lower() != "đang cập nhật":
                            company_website = val.strip()
                        if not company_website:
                            href = intro_item.css(".item-value a::attr(href)").get()
                            if href:
                                company_website = href.strip()
                        break

        # Fallback lấy trên trang chi tiết công việc nếu trang công ty không có hoặc fetch lỗi
        if not company_info:
            company_info = self._get_block_text(page, "div.introduce-left .introduce-content")
            if not company_info:
                company_info = self._get_block_text(page, "div.introduce-content")

        if not company_website:
            for intro_item in page.css("div.introduce-item"):
                label = intro_item.css(".item-text::text").get() or ""
                if "website" in label.lower():
                    val = intro_item.css(".item-value::text").get()
                    if val and val.strip() and val.strip().lower() != "đang cập nhật":
                        company_website = val.strip()
                    if not company_website:
                        href = intro_item.css(".item-value a::attr(href)").get()
                        if href:
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
            "job_url": self._to_absolute_detail_url(url),
            "source": self.source_name,
            "scraped_at": datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------
    # Convenience wrapper (backward-compat với DAG)
    # ------------------------------------------------------------------
    def collect_all_links(
        self,
        pages: int | None = None,
        existing_urls: set[str] | None = None,
    ) -> list[str]:
        raw_urls = self._collect_urls(pages)
        return self._deduplicate_urls(raw_urls, existing_urls)


if __name__ == "__main__":
    start_url = os.getenv("JOB123_START_URL")
    scraper = Job123Scraper(start_url=start_url)
    links = scraper.run_links_only()
    print(f"Total dedup links: {len(links)}")
