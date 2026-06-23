
import os
from datetime import datetime
from urllib.parse import urljoin

from scrapling.parser import Adaptor

from src.extract.job_online.base_scraper import BaseScraper


class TopCVScraper(BaseScraper):

    _block_media = BaseScraper._block_media
    source_name = "topcv"
    base_url = "https://www.topcv.vn"
    batch_size = 10

    DEFAULT_START_URL = (
        "https://www.topcv.vn/tim-viec-lam-data-science-tai-ha-noi-l1cr257cb261"
        "?type_keyword=1&sba=1&category_family=r257~b260_b261&locations=l1"
    )

    def __init__(self, start_url: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.start_url = (start_url or self.DEFAULT_START_URL).split("?")[0]

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------
    def get_list_page_url(self, page_num: int) -> str:
        if page_num <= 1:
            return self.start_url
        return f"{self.start_url}?page={page_num}"

    def get_next_page_url(self, list_page_html: str, page_num: int, current_url: str) -> str | None:
        page = Adaptor(list_page_html)
        next_href = page.css("ul.pagination li a[rel='next']::attr(data-href)").get()
        if next_href:
            return urljoin(self.base_url, next_href)
        return self.get_list_page_url(page_num + 1)

    # ------------------------------------------------------------------
    # Phase 1: Extract job URLs from list page
    # ------------------------------------------------------------------
    def extract_job_urls(self, list_page_html: str) -> list[str]:
        page = Adaptor(list_page_html)
        hrefs = page.css("div.avatar a::attr(href)").getall()
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
    def _clean_texts(elements) -> str | None:
        """Join all ::text nodes, strip whitespace, return None if empty."""
        parts = elements.css("::text").getall() if elements else []
        text = " ".join(p.strip() for p in parts if p and p.strip())
        return text or None

    @staticmethod
    def _block_text(elements) -> str | None:
        """Multi-line inner text from a block element."""
        parts = elements.css("::text").getall() if elements else []
        lines = [p.strip() for p in parts if p and p.strip()]
        return "\n".join(lines) or None

    def _section_content(self, page: Adaptor, label_keyword: str) -> str | None:
        """
        Tìm trong .job-detail__info--section-content có title chứa label_keyword,
        trả về text của .job-detail__info--section-content-value.
        """
        for section in page.css("div.job-detail__info--section-content"):
            title = section.css(".job-detail__info--section-content-title::text").get() or ""
            if label_keyword.lower() in title.lower():
                val = section.css(".job-detail__info--section-content-value::text").get()
                if val and val.strip():
                    return val.strip()
        return None

    def _box_general_info(self, page: Adaptor, label_keyword: str) -> str | None:
        """
        Tìm trong .box-general-group-info có title chứa label_keyword,
        trả về text của .box-general-group-info-value.
        """
        for box in page.css("div.box-general-group-info"):
            title = box.css(".box-general-group-info-title::text").get() or ""
            if label_keyword.lower() in title.lower():
                val = box.css(".box-general-group-info-value::text").get()
                if val and val.strip():
                    return val.strip()
        return None

    def _job_description_section(self, page: Adaptor, heading_keyword: str) -> str | None:
        """
        Tìm trong .job-description__item có <h3> chứa heading_keyword,
        trả về block text của .job-description__item--content.
        """
        for item in page.css("div.job-description__item"):
            h3 = item.css("h3::text").get() or ""
            if heading_keyword.lower() in h3.lower():
                content = item.css(".job-description__item--content")
                if content:
                    return self._block_text(content)
        return None

    # ------------------------------------------------------------------
    # Phase 3: Parse job detail page
    # ------------------------------------------------------------------
    def parse_job_detail(self, detail_html: str, url: str) -> dict:
        page = Adaptor(detail_html)

        # ── Tên job ─────────────────────────────────────────────────────
        # <h1 class="job-detail__info--title">
        #   <a class="text-highlight">Tên job</a>
        # </h1>
        title = None
        title_el = page.css("h1.job-detail__info--title")
        if title_el:
            # Lấy text của thẻ <a class="text-highlight"> trước
            a_text = title_el.css("a.text-highlight::text").get()
            if a_text and a_text.strip():
                title = a_text.strip()
            else:
                # Fallback: toàn bộ text của h1 (bỏ phần lương trong ngoặc nếu có)
                parts = title_el.css("::text").getall()
                title = " ".join(p.strip() for p in parts if p.strip()) or None

        # ── Tên công ty ─────────────────────────────────────────────────
        # <a rel="nofollow" class="name" href="...">CÔNG TY...</a>
        company = None
        company_el = page.css("a.name[rel='nofollow']")
        if company_el:
            company = company_el.css("::text").get()
            if company:
                company = company.strip() or None
        if not company:
            # Fallback: link cong-ty trong job-detail
            for sel in [
                "div.job-detail__company--information a.name::text",
                "a[href*='/cong-ty/']::text",
            ]:
                val = page.css(sel).get()
                if val and val.strip():
                    company = val.strip()
                    break

        # ── Địa chỉ ─────────────────────────────────────────────────────
        # <div class="job-detail__company--information-item company-address">
        #   <div class="company-value">...</div>
        # </div>
        location = None
        addr_el = page.css("div.company-address div.company-value")
        if addr_el:
            location = addr_el.css("::text").get()
            if location:
                location = location.strip() or None
        if not location:
            # Fallback: data-original-title trên company-address
            location = page.css(
                "div.company-address div.company-value::attr(data-original-title)"
            ).get()

        # ── Lương ────────────────────────────────────────────────────────
        # <div class="job-detail__info--section-content">
        #   <div class="...title">Mức lương</div>
        #   <div class="...value">12 - 20 triệu</div>
        # </div>
        salary = self._section_content(page, "mức lương")

        # ── Kinh nghiệm ──────────────────────────────────────────────────
        # Same pattern, title = "Kinh nghiệm"
        experience_level = self._section_content(page, "kinh nghiệm")

        # ── Hạn ứng tuyển ────────────────────────────────────────────────
        # <div class="job-detail__info--deadline-date">31/07/2026</div>
        job_deadline = None
        deadline_el = page.css("div.job-detail__info--deadline-date")
        if deadline_el:
            job_deadline = deadline_el.css("::text").get()
            if job_deadline:
                job_deadline = job_deadline.strip() or None

        # ── Loại hình làm việc ───────────────────────────────────────────
        # <div class="box-general-group-info">
        #   <div class="...title">Loại hình làm việc</div>
        #   <div class="...value">Toàn thời gian</div>
        # </div>
        job_type = self._box_general_info(page, "loại hình làm việc")

        # ── Cấp bậc ──────────────────────────────────────────────────────
        job_position = self._box_general_info(page, "cấp bậc")

        # ── Ngành nghề ───────────────────────────────────────────────────
        # <div class="box-category-tags">
        #   <a class="box-category-tag">...</a>
        # </div>
        job_industry = None
        industry_tags = page.css("div.box-category-tags a.box-category-tag")
        if industry_tags:
            tags = [t.css("::text").get() for t in industry_tags if t.css("::text").get()]
            tags = [t.strip() for t in tags if t and t.strip()]
            job_industry = ", ".join(tags) if tags else None

        # ── Mô tả công việc ──────────────────────────────────────────────
        # <div class="job-description__item">
        #   <h3> Mô tả công việc </h3>
        #   <div class="job-description__item--content">...</div>
        # </div>
        job_description = self._job_description_section(page, "mô tả công việc")

        # ── Yêu cầu ứng viên ─────────────────────────────────────────────
        # Heading: "Yêu cầu ứng viên"
        requirements = self._job_description_section(page, "yêu cầu ứng viên")
        if not requirements:
            requirements = self._job_description_section(page, "yêu cầu")

        # ── Phúc lợi / Quyền lợi ────────────────────────────────────────
        # Heading: "Quyền lợi"
        benefits = self._job_description_section(page, "quyền lợi")
        if not benefits:
            benefits = self._job_description_section(page, "phúc lợi")

        # ── Thông tin công ty ────────────────────────────────────────────
        # <div class="company-info">
        #   <h2 class="title">Giới thiệu công ty</h2>
        #   <div class="box-body"><div class="content">...</div></div>
        # </div>
        company_info = None
        company_info_el = page.css("div.company-info div.content")
        if company_info_el:
            company_info = self._block_text(company_info_el)

        # ── Website công ty ──────────────────────────────────────────────
        # <a class="box-company-info__item--text" href="https://...">https://...</a>
        company_website = None
        website_el = page.css("a.box-company-info__item--text")
        if website_el:
            company_website = website_el.css("::attr(href)").get()
            if company_website:
                company_website = company_website.strip() or None
        if not company_website:
            # Fallback: tìm link bên ngoài (không phải topcv.vn) trong khu vực thông tin công ty
            for a_el in page.css("div.company-info a"):
                href = a_el.css("::attr(href)").get() or ""
                if href.startswith("http") and "topcv.vn" not in href:
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
            "job_deadline": job_deadline,
            "company_info": company_info,
            "company_website": company_website,
            "job_url": url.split("#")[0],
            "source": self.source_name,
            "scraped_at": datetime.now().isoformat(),
        }


if __name__ == "__main__":
    start_url = os.getenv("TOPCV_START_URL")
    scraper = TopCVScraper(start_url=start_url)
    links = scraper.run_links_only(pages=None)
    print(f"Total dedup links: {len(links)}")
