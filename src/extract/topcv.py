
import os
from datetime import datetime
from urllib.parse import urljoin

from scrapling.parser import Adaptor

from src.extract.base_scraper import BaseScraper


class TopCVScraper(BaseScraper):

    _block_media = BaseScraper._block_media
    source_name = "topcv"
    base_url = "https://www.topcv.vn"
    batch_size = 5

    DEFAULT_START_URL = "https://www.topcv.vn/tim-viec-lam-data-science-tai-ha-noi-l1cr257cb261?type_keyword=1&sba=1&category_family=r257~b260_b261&locations=l1"

    def __init__(self, start_url: str | None = None, **kwargs) -> None:
        kwargs.setdefault("delay_range", (8.0, 15.0))
        kwargs.setdefault("max_retries", 5)
        super().__init__(**kwargs)
        self.start_url = start_url or self.DEFAULT_START_URL

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------
    def get_list_page_url(self, page_num: int) -> str:
        if page_num <= 1:
            return self.start_url
        if "?" in self.start_url:
            return f"{self.start_url}&page={page_num}"
        return f"{self.start_url}?page={page_num}"

    def get_next_page_url(self, list_page_html: str, page_num: int, current_url: str) -> str | None:
        page = Adaptor(list_page_html)
        next_href = page.css("ul.pagination li a[rel='next']::attr(data-href)").get()
        if next_href:
            return urljoin(self.base_url, next_href)
        return self.get_list_page_url(page_num + 1)

    def _is_valid_html(self, html: str, url: str) -> bool:
        """Kiểm tra xem trang có bị chặn hoặc lỗi không."""
        html_lower = html.lower()
        if "cf-browser-verification" in html_lower or "just a moment" in html_lower:
            return False
        if "429 too many requests" in html_lower or "mã lỗi: 429" in html_lower:
            return False
        if "503 service temporarily unavailable" in html_lower:
            return False
            
        # Kiểm tra chi tiết cấu trúc nếu là trang job
        if "/viec-lam/" in url or "/brand/" in url:
            page = Adaptor(html)
            title_el = page.css(
                "h1.box-header-job__title, h1.job-detail__info--title, "
                "h2.premium-job-basic-information__content--title, "
                "h1.job-title, h1.job-detail__title, h1.job-name, "
                ".box-header-job__title, .job-title h1, .job-detail-header h1, "
                "h2.job-title, h2.title, button[data-title], meta[property='og:title']"
            )
            company_el = page.css(
                "a.name[rel='nofollow'], a[href*='/cong-ty/'], "
                "h1.title, h2.company-name, h1.company-name, "
                ".company-name, .brand-name, .box-company-info"
            )
            if not title_el and not company_el:
                # Nếu trang detail nhưng không tìm thấy title hay company nào, rất có thể trang bị lỗi hoặc chưa load xong
                return False
        return True

    # ------------------------------------------------------------------
    # Phase 1: Extract job URLs from list page
    # ------------------------------------------------------------------
    def extract_job_urls(self, list_page_html: str) -> list[str]:
        page = Adaptor(list_page_html)
        # Bóc tách URL từ tiêu đề công việc (ưu tiên), logo, và các thẻ thẻ card việc làm
        href_selectors = [
            "h3.title a::attr(href)",
            ".title a::attr(href)",
            "a.job-title::attr(href)",
            ".job-item-search-result h3 a::attr(href)",
            ".job-item-search-result .title a::attr(href)",
            ".job-item-search-result a[href*='/viec-lam/']::attr(href)",
            ".job-item-search-result a[href*='/brand/']::attr(href)",
            ".job-item-search-result a::attr(href)",
            "div.title-block a::attr(href)",
            "div.body a::attr(href)",
            "div.avatar a::attr(href)",
            "a[data-job-id]::attr(href)",
            "a[href*='/viec-lam/']::attr(href)",
            "a[href*='/brand/']::attr(href)"
        ]
        hrefs: list[str] = []
        for sel in href_selectors:
            found = page.css(sel).getall()
            if found:
                hrefs.extend(found)

        links: list[str] = []
        seen: set[str] = set()
        for href in hrefs:
            if not href:
                continue
            full_url = urljoin(self.base_url, href).split("?")[0].split("#")[0]
            # Filter out non-job URLs like Toppy AI suggestions or company pages without jobs
            if "/viec-lam/" not in full_url and "/brand/" not in full_url:
                continue
            if "toppy" in full_url.lower():
                continue
            
            if full_url not in seen:
                seen.add(full_url)
                links.append(full_url)
        return links

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
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

    @staticmethod
    def _is_valid_content(text: str | None) -> bool:
        """Kiểm tra xem nội dung cào được có hợp lệ không (tránh lấy phải popup thông báo thành công)."""
        if not text:
            return False
        text_lower = text.lower()
        if "chúc mừng bạn đã ứng tuyển thành công" in text_lower or "ghi nhớ tên các công ty" in text_lower:
            return False
        if len(text.strip()) < 15:
            return False
        return True

    def _job_description_section(self, page: Adaptor, heading_keyword: str) -> str | None:
        """
        Tìm trong .job-description__item có <h3> chứa heading_keyword,
        hoặc trong .box-job-information-detail-item (TopCV V2 layout),
        hoặc trong .box-info / .job-detail-section có h2/h3 chứa heading_keyword.
        """
        # 1. Cấu trúc TopCV V2 layout (.box-job-information-detail-item)
        for item in page.css("div.box-job-information-detail-item"):
            header_text = ""
            for h_sel in [
                "h2.box-job-information-detail-item__title--title",
                ".box-job-information-detail-item__title h2",
                ".box-job-information-detail-item__title",
                "h2", "h3"
            ]:
                h_el = item.css(h_sel)
                if h_el:
                    header_text = "".join(h_el.css("::text").getall()).strip()
                    if header_text:
                        break
            if heading_keyword.lower() in header_text.lower():
                content_el = item.css("div.box-job-information-detail-item__text")
                if content_el:
                    txt = self._block_text(content_el)
                    if self._is_valid_content(txt):
                        return txt
                txt = self._block_text(item)
                if txt and header_text in txt:
                    txt = txt.replace(header_text, "", 1).strip()
                if self._is_valid_content(txt):
                    return txt

        # 2. Cấu trúc cũ .job-description__item
        for item in page.css("div.job-description__item"):
            h3 = item.css("h3::text").get() or ""
            if heading_keyword.lower() in h3.lower():
                content = item.css(".job-description__item--content")
                if content:
                    txt = self._block_text(content)
                    if self._is_valid_content(txt):
                        return txt

        # 3. Check in .box-info, .job-detail-section, .box-job-detail, etc.
        for item in page.css("div.box-info, div.job-detail-section, div.box-job-detail"):
            header_text = ""
            for h_sel in ["h2.title", "h2", "h3", ".title"]:
                h_el = item.css(h_sel)
                if h_el:
                    header_text = "".join(h_el.css("::text").getall()).strip()
                    if header_text:
                        break
            if heading_keyword.lower() in header_text.lower():
                content_el = item.css(".content-tab")
                if content_el:
                    txt = self._block_text(content_el)
                    if self._is_valid_content(txt):
                        return txt
                txt = self._block_text(item)
                if txt and header_text in txt:
                    txt = txt.replace(header_text, "", 1).strip()
                if self._is_valid_content(txt):
                    return txt
                    
        # Fallback for brand pages with custom container classes
        keyword_lower = heading_keyword.lower()
        if "mô tả" in keyword_lower:
            selectors = [".job-description", ".description", ".job-desc", ".desc", ".description-content"]
        elif "yêu cầu" in keyword_lower:
            selectors = [".job-requirement", ".requirement", ".job-req", ".req", ".requirement-content", ".candidate-requirements"]
        elif "quyền lợi" in keyword_lower or "phúc lợi" in keyword_lower:
            selectors = [".job-benefit", ".benefit", ".benefits", ".phuc-loi", ".quy-loi", ".benefit-content"]
        else:
            selectors = []
            
        for sel in selectors:
            el = page.css(sel)
            if el:
                txt = self._block_text(el)
                if self._is_valid_content(txt):
                    return txt.strip()
        return None

    def _find_info_by_label(self, page: Adaptor, label_keyword: str) -> str | None:
        """
        Tìm kiếm thông tin theo nhãn trên trang thường và trang brand.
        Thử các cấu trúc phổ biến nhất.
        """
        # 1. Thử cấu trúc trang thường (.job-detail__info--section-content)
        val = self._section_content(page, label_keyword)
        if val:
            return val
            
        # 1.5 Thử cấu trúc TopCV V2 layout (.box-header-job-list-info__item)
        for item in page.css("div.box-header-job-list-info__item"):
            lbl_el = item.css(".list-info__content__title::text").get()
            if lbl_el and label_keyword.lower() in lbl_el.lower():
                val_el = item.css(".list-info__content__desc")
                if val_el:
                    txt = " ".join("".join(val_el.css("::text").getall()).split())
                    if txt:
                        return txt

        # 2. Thử cấu trúc trang thường thứ hai (.box-general-group-info)
        val = self._box_general_info(page, label_keyword)
        if val:
            return val

        # 2.5 Thử cấu trúc general-information-data
        for item in page.css("div.general-information-data"):
            lbl_el = item.css(".general-information-data__label::text").get()
            if lbl_el and label_keyword.lower() in lbl_el.lower():
                val_el = item.css(".general-information-data__value::text").get()
                if val_el and val_el.strip():
                    return val_el.strip()

        # 3. Thử quét các container tổng quát thường gặp trên trang brand và v2 layout
        for container_sel in [
            "div.box-header-job-list-info__item",
            "div.box-job-information-address-and-time-list__item",
            "div.job-summary-item", "div.summary-item", "div.job-info-item", 
            "div.info-item", "div.detail-item", "div.box-item", "div.job-detail-item",
            "div.box-general-group-info"
        ]:
            for item in page.css(container_sel):
                # Thử tìm nhãn/tiêu đề
                title_text = ""
                for title_sel in [
                    ".list-info__content__title",
                    ".box-job-information-address-and-time-list__item--title",
                    ".summary-label", ".label", ".title", ".item-title", 
                    "span.text-muted", "div.text-muted", ".box-general-group-info-title"
                ]:
                    title_el = item.css(title_sel)
                    if title_el:
                        title_text = "".join(title_el.css("::text").getall()).strip()
                        break
                
                # Nếu không tìm thấy class tiêu đề, kiểm tra toàn bộ text xem có dấu hai chấm ko
                item_text = "".join(item.css("::text").getall()).strip()
                if not title_text and ":" in item_text:
                    title_text = item_text.split(":")[0]
                
                if label_keyword.lower() in title_text.lower():
                    # Thử tìm phần chứa giá trị
                    for value_sel in [
                        ".list-info__content__desc",
                        ".box-job-information-address-and-time-list__item--content",
                        ".summary-value", ".value", "strong", "span.text-dark", 
                        "div.text-dark", ".item-value", ".box-general-group-info-value"
                    ]:
                        value_el = item.css(value_sel)
                        if value_el:
                            val_text = " ".join("".join(value_el.css("::text").getall()).split())
                            if val_text:
                                return val_text
                    
                    # Nếu có dấu hai chấm, lấy phần phía sau
                    if ":" in item_text:
                        parts = item_text.split(":", 1)
                        if len(parts) > 1 and parts[1].strip():
                            return parts[1].strip()
        return None

    # ------------------------------------------------------------------
    # Phase 3: Parse job detail page
    # ------------------------------------------------------------------
    def parse_job_detail(self, detail_html: str, url: str) -> dict:
        page = Adaptor(detail_html)

        # ── Tên job ─────────────────────────────────────────────────────
        title = None
        title_selectors = [
            "h1.box-header-job__title",
            ".box-header-job__title",
            "h1.job-detail__info--title",
            ".job-detail__info--title",
            "h2.premium-job-basic-information__content--title",
            "h1.job-title",
            "h1.job-detail__title",
            "h1.job-name",
            ".job-title h1",
            ".job-detail-header h1",
            ".job-header h1",
            ".box-header-job h1",
            "h2.job-title",
            "h2.title"
        ]

        # 1. Thử các selector h1/h2 tiêu đề phổ biến
        for sel in title_selectors:
            el = page.css(sel)
            if not el:
                continue
            # Lấy toàn bộ text của thẻ, ưu tiên loại bỏ các phần tử icon / tooltip / badge
            parts = el.css(":not(.icon-verified-employer):not(.icon-verified-employer-tooltip):not(.badge)::text").getall()
            if not parts:
                parts = el.css("::text").getall()
            raw_text = " ".join("".join(parts).split()).strip()
            if not raw_text:
                continue

            # Kiểm tra xem có phải tiêu đề section bị bắt nhầm không
            if raw_text.lower() in [
                "tổng quan", "địa điểm làm việc", "mô tả công việc", "yêu cầu ứng viên", 
                "quyền lợi được hưởng", "quyền lợi ứng viên", "giới thiệu", "thông tin công ty",
                "gửi tôi việc làm tương tự", "việc làm liên quan", "thông tin"
            ]:
                continue

            title = raw_text
            break

        # 2. Fallback cực kỳ chuẩn xác từ data-title trên TopCV (luôn có trong nút Lưu tin)
        if not title:
            for attr_sel in [
                "button.btn-save-job::attr(data-title)",
                "button.btn-save::attr(data-title)",
                "button.btn-unsave::attr(data-title)",
                "button[data-title]::attr(data-title)",
                "button[data-keyword]::attr(data-keyword)",
                ".btn-save-job::attr(data-title)"
            ]:
                val = page.css(attr_sel).get()
                if val and val.strip():
                    val_clean = " ".join(val.split()).strip()
                    if val_clean.lower() not in ["lưu tin", "đã lưu"]:
                        title = val_clean
                        break

        # 3. Fallback từ thẻ meta og:title hoặc title của trang HTML
        if not title:
            for meta_sel in [
                "meta[property='og:title']::attr(content)",
                "meta[name='title']::attr(content)",
                "title::text"
            ]:
                meta_val = page.css(meta_sel).get()
                if meta_val and meta_val.strip():
                    t = meta_val.strip()
                    if t.lower().startswith("tuyển dụng "):
                        t = t[11:].strip()
                    if " tại " in t.lower():
                        t = t[:t.lower().find(" tại ")].strip()
                    for sep in [" - TopCV", " | TopCV", " – TopCV"]:
                        if sep.lower() in t.lower():
                            t = t[:t.lower().find(sep.lower())].strip()
                    if t and len(t) > 3:
                        title = t
                        break

        # 4. Làm sạch noise ở cuối tiêu đề nếu có
        if title:
            for noise in [
                "tóm tắt", "địa điểm làm việc", "mô tả công việc", "yêu cầu ứng viên", 
                "quyền lợi được hưởng", "thời gian làm việc", "gửi tôi việc làm tương tự",
                "nhà tuyển dụng đã được xác thực"
            ]:
                if f" {noise}" in title.lower():
                    idx = title.lower().find(f" {noise}")
                    title = title[:idx].strip()
                elif noise in title.lower() and title.lower().endswith(noise):
                    idx = title.lower().rfind(noise)
                    title = title[:idx].strip()
            
            # Chỉ loại bỏ nếu chuỗi chỉ vỏn vẹn là banner Toppy AI
            if title and title.lower() in ["toppy ai", "trợ lý toppy ai", "toppy ai gợi ý việc làm"]:
                title = None

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
                "div.box-company-info a.name::text",
                "div.box-company-info__detail a.name::text",
                "div.box-company-info a[href*='/cong-ty/']::text",
                "div.job-detail__company--information a.name::text",
                "a[href*='/cong-ty/']::text",
                "div.brand-info h1.name::text",
                "h1.title::text",  # Thường là tên công ty trên trang brand
                "h2.company-name::text",
                "h1.company-name::text",
                "div.company-name::text",
                "span.company-name::text",
                ".company-name::text",
                ".brand-name::text"
            ]:
                val = page.css(sel).get()
                if val and val.strip():
                    company = val.strip()
                    break

        # Nếu cả title và company đều không cào được, có khả năng cao trang bị chặn/lỗi tải trang
        if not title and not company:
            raise ValueError(f"Không thể cào dữ liệu cho job này (trang có thể bị chặn/lỗi): {url}")

        # ── Địa chỉ ─────────────────────────────────────────────────────
        # <div class="job-detail__company--information-item company-address">
        #   <div class="company-value">...</div>
        # </div>
        location = None
        # V2 layout address list item
        for item in page.css("div.box-job-information-address-and-time-list__item"):
            t_el = item.css(".box-job-information-address-and-time-list__item--title::text").get() or ""
            if "địa điểm" in t_el.lower() or "nơi làm việc" in t_el.lower():
                c_el = item.css(".box-job-information-address-and-time-list__item--content")
                if c_el:
                    txt = self._block_text(c_el)
                    if txt:
                        lines = [l.strip() for l in txt.split("\n") if l.strip()]
                        location = "\n".join(lines)
                        break

        if not location:
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
        if not location:
            # Fallback cho trang brand và v2 layout header: quét nhãn địa điểm
            for label in ["địa điểm", "địa chỉ", "nơi làm việc"]:
                val = self._find_info_by_label(page, label)
                if val:
                    location = val
                    break
        if not location:
            # Fallback for box-address / job-address divs
            for sel in [
                ".box-address div:not(.title)",
                ".box-address",
                ".job-address",
                ".address-list",
                ".brand-address",
                ".company-address",
                ".office-address",
                ".work-address",
                ".contact-address",
                "div.address",
                ".location-item",
                ".job-location"
            ]:
                el = page.css(sel)
                if el:
                    txt = self._block_text(el)
                    if txt:
                        lines = [l.strip() for l in txt.split("\n") if l.strip()]
                        cleaned_lines = []
                        for line in lines:
                            if "địa điểm làm việc" in line.lower() or "địa chỉ làm việc" in line.lower():
                                continue
                            if "(đã được cập nhật" in line.lower() or "danh mục hành chính" in line.lower():
                                continue
                            cleaned_lines.append(line)
                        if cleaned_lines:
                            location = "\n".join(cleaned_lines)
                            break

        # ── Lương ────────────────────────────────────────────────────────
        salary = self._find_info_by_label(page, "mức lương") or self._find_info_by_label(page, "lương") or self._find_info_by_label(page, "thu nhập")
        if not salary:
            for sel in [
                ".box-header-job__salary--title::text",
                ".box-header-job__salary span::text",
                ".box-header-job__salary::text",
                "div.salary::text",
                ".salary::text",
                ".job-salary::text",
                ".salary-value::text",
                ".salary-amount::text",
                ".job-detail__info--section-content-value::text",
                ".salary_value::text",
                ".job-salary-value::text"
            ]:
                s = page.css(sel).get()
                if s and s.strip():
                    salary = s.strip()
                    break

        # ── Kinh nghiệm ──────────────────────────────────────────────────
        experience_level = self._find_info_by_label(page, "kinh nghiệm")

        # ── Hạn ứng tuyển ────────────────────────────────────────────────
        job_deadline = None
        deadline_el = page.css("div.job-detail__info--deadline-date")
        if deadline_el:
            job_deadline = deadline_el.css("::text").get()
            if job_deadline:
                job_deadline = job_deadline.strip() or None
        if not job_deadline:
            # Fallback cho trang brand và v2 layout header
            job_deadline = self._find_info_by_label(page, "hạn nộp") or self._find_info_by_label(page, "hạn ứng tuyển")
        if not job_deadline:
            # Fallback for span.deadline or .box-applied-cv
            for sel in [
                ".box-applied-cv span.date::text",
                ".box-applied-cv .date::text",
                "span.deadline", ".deadline", ".job-deadline"
            ]:
                el = page.css(sel)
                if el:
                    parts = el.css("::text").getall()
                    t = " ".join(p.strip() for p in parts if p.strip())
                    if t:
                        job_deadline = t
                        break

        # ── Loại hình làm việc ───────────────────────────────────────────
        job_type = self._find_info_by_label(page, "loại hình") or self._find_info_by_label(page, "loại hình làm việc") or self._find_info_by_label(page, "hình thức") or self._find_info_by_label(page, "hình thức làm việc")
        if not job_type:
            # Check thời gian làm việc in V2 layout
            for item in page.css("div.box-job-information-address-and-time-list__item"):
                t_el = item.css(".box-job-information-address-and-time-list__item--title::text").get() or ""
                if "thời gian" in t_el.lower():
                    c_el = item.css(".box-job-information-address-and-time-list__item--content")
                    if c_el:
                        txt = self._block_text(c_el)
                        if txt:
                            job_type = txt.replace("\n", " ").strip()
                            break

        # ── Cấp bậc ──────────────────────────────────────────────────────
        job_position = self._find_info_by_label(page, "cấp bậc")

        # ── Ngành nghề ───────────────────────────────────────────────────
        job_industry = None
        # Ưu tiên nhóm tag "Chuyên môn" của TopCV V2 layout
        for group in page.css("div.job-tags div.job-tags__group"):
            g_title = group.css(".job-tags__group-name::text").get() or ""
            if "chuyên môn" in g_title.lower() or "ngành" in g_title.lower():
                tags = [t.strip() for t in group.css(".job-tags__group-list-tag a::text").getall() if t and t.strip()]
                if tags:
                    job_industry = ", ".join(tags)
                    break

        if not job_industry:
            for sel in [
                "div.box-category-tags a.box-category-tag",
                "div.box-category-tags a",
                "div.job-tags a.link",
                "div.job-tags a",
                "div.tags a",
                ".category-tags a"
            ]:
                industry_tags = page.css(sel)
                if industry_tags:
                    tags = [t.css("::text").get() for t in industry_tags if t.css("::text").get()]
                    tags = [t.strip() for t in tags if t and t.strip()]
                    if tags:
                        job_industry = ", ".join(tags) if tags else None
                        break

        # Trích xuất kinh nghiệm từ tags ngành nghề nếu bị thiếu ở khung thông tin chính
        if not experience_level and job_industry:
            for tag in job_industry.split(","):
                tag_clean = tag.strip()
                if "kinh nghiệm" in tag_clean.lower() or "yêu cầu kinh nghiệm" in tag_clean.lower() or "kn" in tag_clean.lower():
                    experience_level = tag_clean
                    break

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
        company_info = None
        company_info_parts = []
        for sel in [
            "div.company-info div.content",
            "div.company-info .content",
            "div.brand-info .content",
            ".company-info",
            ".brand-info",
            ".about-company",
            ".about-us",
            ".description__content",
            ".benefits-box"
        ]:
            for el in page.css(sel):
                txt = self._block_text(el)
                if txt and txt.strip() and len(txt.strip()) > 30:
                    cleaned_txt = txt.strip()
                    if cleaned_txt not in company_info_parts:
                        company_info_parts.append(cleaned_txt)
        if company_info_parts:
            company_info = "\n\n".join(company_info_parts)

        # ── Website công ty ──────────────────────────────────────────────
        company_website = None
        website_el = page.css("a.box-company-info__item--text")
        if website_el:
            company_website = website_el.css("::attr(href)").get()
            if company_website:
                company_website = company_website.strip() or None
        if not company_website:
            # Fallback: tìm link bên ngoài (không phải topcv.vn) trong khu vực thông tin công ty
            for container_sel in [
                "div.company-info a", "div.brand-info a", "div.company-detail a", 
                ".sidebar a", ".website a", "div.footer-info-content a", ".footer-info-content a"
            ]:
                for a_el in page.css(container_sel):
                    href = a_el.css("::attr(href)").get() or ""
                    if href.startswith("http") and "topcv.vn" not in href:
                        company_website = href.strip()
                        break
                if company_website:
                    break
        if not company_website:
            # Fallback sang URL trang công ty trên TopCV nếu không có website riêng
            for sel in [
                "div.box-company-info a.name::attr(href)",
                "div.box-company-info__detail a.name::attr(href)",
                "a.name[rel='nofollow']::attr(href)",
                "a.box-company-info__image::attr(href)",
                "a[href*='/cong-ty/']::attr(href)"
            ]:
                comp_link = page.css(sel).get()
                if comp_link and comp_link.strip():
                    company_website = urljoin(self.base_url, comp_link.strip())
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
            "job_url": url.split("?")[0].split("#")[0],
            "source": self.source_name,
            "scraped_at": datetime.now().isoformat(),
        }


if __name__ == "__main__":
    import json
    
    start_url = os.getenv("TOPCV_START_URL")
    scraper = TopCVScraper(start_url=start_url)
    
    print("Đang cào dữ liệu trang đầu tiên...")
    # Scrape data for 1 page
    jobs = scraper.run(pages=1)
    
    if jobs:
        import os
        os.makedirs("data", exist_ok=True)
        output_file = "data/topcv_sample_output.jsonl"
        with open(output_file, "w", encoding="utf-8") as f:
            for job in jobs:
                f.write(json.dumps(job, ensure_ascii=False) + "\n")
        print(f"\n Cào thành công {len(jobs)} jobs. Đã lưu toàn bộ dữ liệu vào file {output_file}")
    else:
        print("Không có data nào được cào.")
