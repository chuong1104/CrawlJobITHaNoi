from datetime import datetime
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from scrapling.parser import Adaptor

from src.extract.base_scraper import BaseScraper


class CareerVietScraper(BaseScraper):
	source_name = "careerviet"
	base_url = "https://careerviet.vn"
	batch_size = 10

	DEFAULT_START_URL = (
		"https://careerviet.vn/viec-lam/cntt-phan-mem-tai-ha-noi-c1l4-vi.html"
	)

	def __init__(self, start_url: str | None = None, **kwargs) -> None:
		super().__init__(**kwargs)
		self.start_url = self._clean_list_url(start_url or self.DEFAULT_START_URL)

	@staticmethod
	def _clean_list_url(url: str) -> str:
		parsed = urlparse(url)
		return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

	@staticmethod
	def _drop_tracking_query(url: str) -> str:
		parsed = urlparse(url)
		query = parse_qs(parsed.query, keep_blank_values=True)
		keep_keys = {"page"}
		filtered = {
			key: value
			for key, value in query.items()
			if key in keep_keys and value and value[0] != ""
		}
		new_query = urlencode(filtered, doseq=True)
		return urlunparse(
			(parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, "")
		)

	def _canonicalize_job_url(self, url: str) -> str:
		full_url = urljoin(self.base_url, (url or "").strip())
		return self._drop_tracking_query(full_url)

	@staticmethod
	def _build_paginated_url(base_url: str, page_num: int) -> str:
		if page_num <= 1:
			return base_url

		parsed = urlparse(base_url)
		path = parsed.path

		# Remove existing -trang-N- token if present.
		path = path.replace("-trang-2-", "-")
		for i in range(3, 500):
			token = f"-trang-{i}-"
			if token in path:
				path = path.replace(token, "-")

		if path.endswith("-vi.html"):
			path = path.replace("-vi.html", f"-trang-{page_num}-vi.html")

		return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))

	def get_list_page_url(self, page_num: int) -> str:
		return self._build_paginated_url(self.start_url, page_num)

	def get_next_page_url(
		self,
		list_page_html: str,
		page_num: int,
		current_url: str,
	) -> str | None:
		page = Adaptor(list_page_html)
		next_href = page.css("li.next-page a::attr(href)").get()
		if next_href:
			return urljoin(self.base_url, next_href)
		return self.get_list_page_url(page_num + 1)

	def extract_job_urls(self, list_page_html: str) -> list[str]:
		page = Adaptor(list_page_html)
		candidate_urls: list[str] = []

		candidate_urls.extend(page.css("a.job_link::attr(href)").getall())
		candidate_urls.extend(page.css("h2.job-name a::attr(href)").getall())

		links: list[str] = []
		seen: set[str] = set()

		for raw in candidate_urls:
			if not raw:
				continue
			canonical = self._canonicalize_job_url(raw)
			if "/tim-viec-lam/" not in canonical:
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

		title = self._first_text(page, ["h1.title::text", "h1.job-title::text", "h1::text"])
		company = self._first_text(
			page,
			[
				"a.employer-name::text",
				"h2.company-name::text",
				"a[href*='/cong-ty/']::text",
			],
		)
		salary = self._first_text(
			page,
			[
				"li.salary span::text",
				"div.salary p::text",
				"span.salary::text",
			],
		)
		location = self._first_text(
			page,
			[
				"li.location span::text",
				"div.location p::text",
				"span.location::text",
			],
		)
		deadline = self._first_text(
			page,
			[
				"li.deadline span::text",
				"div.expired-date::text",
				"span.deadline::text",
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
			"job_description": self._join_text(
				page, "section#job-description, div.job-description"
			),
			"requirements": self._join_text(
				page, "section#job-requirement, div.job-requirement"
			),
			"benefits": self._join_text(page, "section#job-benefit, div.job-benefit"),
			"job_deadline": deadline,
			"job_url": self._canonicalize_job_url(url),
			"source": self.source_name,
			"scraped_at": datetime.now().isoformat(),
		}


if __name__ == "__main__":
	scraper = CareerVietScraper()
	links = scraper.run_links_only()
	print(f"Total dedup links: {len(links)}")
