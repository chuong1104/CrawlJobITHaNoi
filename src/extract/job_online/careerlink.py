import os
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
        self.start_url = (start_url or self.DEFAULT_START_URL).split("?")[0]

    def get_list_page_url(self, page_num: int) -> str:
        # Page 1 không cần query ?page=1
        if page_num <= 1:
            return self.start_url
        return f"{self.start_url}?page={page_num}"

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

    def parse_job_detail(self, detail_html: str, url: str) -> dict:
        # Tạm để đó, vì bạn đang làm bước lấy link trước
        raise NotImplementedError("Implement parse_job_detail sau khi xong bước lấy link.")

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
