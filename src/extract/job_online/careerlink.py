import os
from datetime import datetime
from urllib.parse import urljoin

from scrapling.parser import Adaptor

from src.extract.job_online.base_scraper import BaseScraper


class CareerLinkScraper(BaseScraper):

    source_name = "careerlink"
    base_url = "https://www.careerlink.vn"
    batch_size = 10

    # Start URL bạn chọn thủ công theo bộ lọc
    DEFAULT_START_URL = (
        "https://www.careerlink.vn/tim-viec-lam-tai/ha-noi/HN/c/cntt-phan-mem/19?career_levels=I%2CN%2CL%2CT&experience_levels=A%2CB"
    )
    # Use BaseScraper._block_media for resource blocking
    _block_media = BaseScraper._block_media

    def __init__(self, start_url: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.start_url = start_url or self.DEFAULT_START_URL

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------
    def get_list_page_url(self, page_num: int) -> str:
        # Page 1 không cần query page=1
        if page_num <= 1:
            return self.start_url
        
        from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
        parsed = urlparse(self.start_url)
        query_params = parse_qsl(parsed.query)
        
        # Cập nhật hoặc chèn thêm tham số page
        query_dict = dict(query_params)
        query_dict["page"] = str(page_num)
        
        new_query = urlencode(query_dict)
        return urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment)
        )

    def get_next_page_url(
        self,
        list_page_html: str,
        page_num: int,
        current_url: str,
    ) -> str | None:
        page = Adaptor(list_page_html)
        next_href = page.css("li.next a::attr(href)").get() or page.css(
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
        hrefs = page.css("a.job-link.clickable-outside::attr(href)").getall()

        # Chuẩn hóa thành absolute URL + loại trùng tại chỗ
        links: list[str] = []
        seen: set[str] = set()
        for href in hrefs:
            if not href:
                continue
            full_url = urljoin(self.base_url, href).split("#")[0]
            if full_url not in seen:
                seen.add(full_url)
                links.append(full_url)

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
    def _get_inner_html(page: Adaptor, selector: str) -> str | None:
        """Lấy toàn bộ inner text (plain) của một block section."""
        el = page.css(selector)
        if not el:
            return None
        parts = el.css("::text").getall()
        lines = [p.strip() for p in parts if p and p.strip()]
        return "\n".join(lines) or None

    # ------------------------------------------------------------------
    # Phase 3: Parse job detail page
    # ------------------------------------------------------------------
    def parse_job_detail(self, detail_html: str, url: str) -> dict:
        page = Adaptor(detail_html)

        # ── Tên job ────────────────────────────────────────────────────
        title_el = page.css("h1.job-title")
        title = title_el.css("::text").get()
        if title:
            title = title.strip()

        # ── Tên công ty ────────────────────────────────────────────────
        company_el = page.css("p.org-name a span")
        company = company_el.css("::text").get() if company_el else None
        if not company:
            # fallback: lấy text trực tiếp trong <a>
            company_a = page.css("p.org-name a")
            company = company_a.css("::text").get() if company_a else None
        if company:
            company = company.strip()

        # ── Địa chỉ ────────────────────────────────────────────────────
        location_parts: list[str] = []
        for office_div in page.css("#job-offices .d-flex.align-items-center"):
            parts = office_div.css("span ::text").getall()
            text = " ".join(p.strip() for p in parts if p and p.strip())
            if text:
                location_parts.append(text)
        location = " | ".join(location_parts) if location_parts else None

        # ── Lương ──────────────────────────────────────────────────────
        salary_el = page.css("#job-salary span.text-primary")
        salary = salary_el.css("::text").get() if salary_el else None
        if salary:
            salary = salary.strip()

        # ── Kinh nghiệm ────────────────────────────────────────────────
        # Icon cli-suitcase-simple nằm trong div.d-flex.align-items-center
        # Lấy span text sau icon đó (không có id riêng)
        experience = None
        for item_div in page.css("div.d-flex.align-items-center.mb-2"):
            icon = item_div.css("i.cli-suitcase-simple")
            if icon:
                span_text = item_div.css("span::text").get()
                if span_text:
                    experience = span_text.strip()
                break

        # ── Hạn ứng tuyển ──────────────────────────────────────────────
        deadline = None
        date_div = page.css("#job-date")
        if date_div:
            # Lấy text ngày đăng tuyển (dd-MM-yyyy)
            date_texts = date_div.css(".date-from span ::text").getall()
            date_texts = [t.strip() for t in date_texts if t.strip()]
            # Lọc lấy phần chứa ngày (dạng dd-MM-yyyy)
            for t in date_texts:
                if len(t) == 10 and t.count("-") == 2:
                    deadline = t
                    break
            # Nếu không tách được → lấy toàn bộ text .date-from
            if not deadline:
                deadline = " ".join(date_texts) or None

        # ── Mô tả công việc ────────────────────────────────────────────
        job_description = self._get_inner_html(
            page, "#section-job-description .rich-text-content"
        )

        # ── Phúc lợi ───────────────────────────────────────────────────
        benefits_parts: list[str] = []
        for benefit_item in page.css("#section-job-benefits .job-benefit-item span"):
            t = benefit_item.css("::text").get()
            if t and t.strip():
                benefits_parts.append(t.strip())
        benefits = "\n".join(benefits_parts) if benefits_parts else None

        # Fallback: lấy text thô trong section
        if not benefits:
            benefits = self._get_inner_html(page, "#section-job-benefits")

        # ── Kỹ năng / Yêu cầu ─────────────────────────────────────────
        requirements = self._get_inner_html(
            page, "#section-job-skills .rich-text-content, #section-job-skills .raw-content"
        )

        # ── Loại công việc ─────────────────────────────────────────────
        job_type = None
        for summary_item in page.css(".job-summary-item"):
            label = summary_item.css(".summary-label::text").get()
            if label and "loại công việc" in label.lower():
                val = summary_item.css(".font-weight-bolder::text").get()
                job_type = val.strip() if val else None
                break

        # ── Cấp bậc ────────────────────────────────────────────────────
        job_position = None
        for summary_item in page.css(".job-summary-item"):
            label = summary_item.css(".summary-label::text").get()
            if label and "cấp bậc" in label.lower():
                val = summary_item.css(".font-weight-bolder::text").get()
                job_position = val.strip() if val else None
                break

        # ── Ngành nghề ─────────────────────────────────────────────────
        job_industry = None
        for summary_item in page.css(".job-summary-item"):
            label = summary_item.css(".summary-label::text").get()
            if label and "ngành nghề" in label.lower():
                val = summary_item.css(".font-weight-bolder a span::text").get()
                if not val:
                    val = summary_item.css(".font-weight-bolder::text").get()
                job_industry = val.strip() if val else None
                break

        # ── Thông tin công ty ──────────────────────────────────────────
        company_info = self._get_inner_html(
            page, ".company-profile .rich-text-content"
        )

        # ── Website công ty ────────────────────────────────────────────
        company_website_el = page.css(".mr-3.d-flex.align-items-start a[href]")
        company_website = None
        if company_website_el:
            company_website = company_website_el.css("::attr(href)").get()
            if not company_website:
                company_website = company_website_el.css("::text").get()
            if company_website:
                company_website = company_website.strip()

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

    # ------------------------------------------------------------------
    # Convenience wrapper (giữ backward-compat với DAG cũ)
    # ------------------------------------------------------------------
    def collect_all_links(
        self,
        pages: int | None = None,
        existing_urls: set[str] | None = None,
    ) -> list[str]:
        raw_urls = self._collect_urls(pages)
        return self._deduplicate_urls(raw_urls, existing_urls)


if __name__ == "__main__":
    # Optional override for local/manual runs.
    start_url = os.getenv("CAREERLINK_START_URL")
    scraper = CareerLinkScraper(start_url=start_url)
    links = scraper.run_links_only()
    print(f"Total dedup links: {len(links)}")
