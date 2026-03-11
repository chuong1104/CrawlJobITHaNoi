from datetime import datetime
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from scrapling.parser import Adaptor

from src.extract.job_online.base_scraper import BaseScraper


class Job123Scraper(BaseScraper):
		
	_block_media = BaseScraper._block_media
	source_name = "job123"
	base_url = "https://123job.vn"
	batch_size = 10

	DEFAULT_START_URL = (
		"https://123job.vn/tuyen-dung?s=0&jt=0&sort=new&type_keyword=0&cityId=1&q=&l=H%C3%A0+N%E1%BB%99i&city="
		
	)

	def __init__(self, start_url: str | None = None, **kwargs) -> None:
		super().__init__(**kwargs)
		self.start_url = self._canonicalize_list_url(start_url or self.DEFAULT_START_URL)

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
		query = parse_qs(parsed.query, keep_blank_values=True)

		# Keep codePosition only, because it can be part of portal routing.
		keep_keys = {"codePosition"}
		filtered = {
			key: value
			for key, value in query.items()
			if key in keep_keys and value and value[0] != ""
		}
		new_query = urlencode(filtered, doseq=True)
		return urlunparse(
			(parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, "")
		)

	def _to_absolute_detail_url(self, url: str) -> str:
		full_url = urljoin(self.base_url, (url or "").strip())
		return self._canonicalize_detail_url(full_url)

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
		next_href = page.css("ul.pagination-listing li a[aria-label='Next']::attr(href)").get()
		if next_href:
			return urljoin(self.base_url, next_href)
		return self.get_list_page_url(page_num + 1)

	def extract_job_urls(self, list_page_html: str) -> list[str]:
		page = Adaptor(list_page_html)
		candidate_urls: list[str] = []

		candidate_urls.extend(page.css("h2.job__list-item-title a::attr(href)").getall())
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

	@staticmethod
	def _join_text(page: Adaptor, selector: str) -> str | None:
		parts = page.css(f"{selector} ::text").getall()
		text = " ".join(p.strip() for p in parts if p and p.strip())
		return text or None

	@staticmethod
	def _first_text(page: Adaptor, selectors: list[str]) -> str | None:
		for selector in selectors:
			value = page.css(selector).get()
			if value and value.strip():
				return value.strip()
		return None

	def parse_job_detail(self, detail_html: str, url: str) -> dict:
		page = Adaptor(detail_html)

		title = self._first_text(page, ["h1::text", "h1.job-title::text"])
		company = self._first_text(
			page,
			[
				"a.company-name::text",
				"div.job-company a::text",
				"a[href*='/cong-ty/']::text",
			],
		)
		salary = self._first_text(
			page,
			[
				"div.job-salary::text",
				"span.salary::text",
				"li.salary span::text",
			],
		)
		location = self._first_text(
			page,
			[
				"div.job-location::text",
				"span.job-address::text",
				"li.location span::text",
			],
		)
		deadline = self._first_text(
			page,
			[
				"div.job-expired::text",
				"span.deadline::text",
				"li.deadline span::text",
			],
		)

		return {
			"title": title,
			"company": company,
			"salary": salary,
			"location": location,
			"job_type": None,
			"experience_level": None,
			"education_level": None,
			"job_industry": None,
			"job_position": None,
			"job_description": self._join_text(page, "section.job-description, div.job-content"),
			"requirements": self._join_text(
				page, "section.job-requirement, div.job-requirements"
			),
			"benefits": self._join_text(page, "section.job-benefit, div.job-benefits"),
			"job_deadline": deadline,
			"job_url": self._to_absolute_detail_url(url),
			"source": self.source_name,
			"scraped_at": datetime.now().isoformat(),
		}


if __name__ == "__main__":
	scraper = Job123Scraper()
	links = scraper.run_links_only()
	print(f"Total dedup links: {len(links)}")
