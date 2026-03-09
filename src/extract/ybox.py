
import os
from urllib.parse import urljoin
from scrapling.parser import Adaptor
from src.extract.base_scraper import BaseScraper

class YboxScraper(BaseScraper):
	source_name = "ybox"
	base_url = "https://ybox.vn"
	batch_size = 10

	DEFAULT_START_URL = "https://ybox.vn/tuyen-dung-viec-lam-tai-ha-noi-tk-c1e2?keyword="

	def __init__(self, start_url: str | None = None, **kwargs) -> None:
		super().__init__(**kwargs)
		self.start_url = (start_url or self.DEFAULT_START_URL).split("?")[0]

	def get_list_page_url(self, page_num: int) -> str:
		if page_num <= 1:
			return self.start_url
		return f"{self.start_url}?page={page_num}"

	def get_next_page_url(self, list_page_html: str, page_num: int, current_url: str) -> str | None:
		page = Adaptor(list_page_html)
		# Ybox không có nút next rõ ràng, dùng query page
		return self.get_list_page_url(page_num + 1)

	def extract_job_urls(self, list_page_html: str) -> list[str]:
		page = Adaptor(list_page_html)
		hrefs = page.css("h2.post-title a.internal::attr(href)").getall()
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
		raise NotImplementedError("Implement parse_job_detail sau khi xong bước lấy link.")

if __name__ == "__main__":
	start_url = os.getenv("YBOX_START_URL")
	scraper = YboxScraper(start_url=start_url)
	links = scraper.run_links_only(pages=3)
	print(f"Total dedup links: {len(links)}")
