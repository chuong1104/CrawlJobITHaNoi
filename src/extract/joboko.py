from datetime import datetime
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from scrapling.parser import Adaptor

from src.extract.base_scraper import BaseScraper


class JobokoScraper(BaseScraper):
	source_name = "joboko"
	base_url = "https://vn.joboko.com"
	batch_size = 12

	DEFAULT_START_URL = "https://vn.joboko.com/jobs?l=2&ind=124"

	def __init__(self, start_url: str | None = None, **kwargs) -> None:
		super().__init__(**kwargs)
		self.start_url = self._canonicalize_list_url(start_url or self.DEFAULT_START_URL)

	@staticmethod
	def _canonicalize_list_url(url: str) -> str:
		parsed = urlparse(url)
		query = parse_qs(parsed.query, keep_blank_values=True)

		keep_keys = {"l", "ind", "p"}
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
		return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

	def _to_absolute_detail_url(self, url: str) -> str:
		full_url = urljoin(self.base_url, (url or "").strip())
		return self._canonicalize_detail_url(full_url)

	def get_list_page_url(self, page_num: int) -> str:
		parsed = urlparse(self.start_url)
		query = parse_qs(parsed.query, keep_blank_values=True)

		if page_num <= 1:
			query.pop("p", None)
		else:
			query["p"] = [str(page_num)]

		new_query = urlencode(query, doseq=True)
		return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", new_query, ""))

	def get_next_page_url(
		self,
		list_page_html: str,
		page_num: int,
		current_url: str,
	) -> str | None:
		page = Adaptor(list_page_html)
		next_href = page.css("div.nw-job-list__more a.btn.btn-nw-success-ol::attr(href)").get()
		if next_href:
			return urljoin(self.base_url, next_href)
		return self.get_list_page_url(page_num + 1)

	def extract_job_urls(self, list_page_html: str) -> list[str]:
		page = Adaptor(list_page_html)
		candidate_urls: list[str] = []

		candidate_urls.extend(page.css("h2.item-title a::attr(href)").getall())
		candidate_urls.extend(page.css("a.block-detail::attr(href)").getall())

		links: list[str] = []
		seen: set[str] = set()

		for raw in candidate_urls:
			if not raw:
				continue
			canonical = self._to_absolute_detail_url(raw)
			if "/viec-lam-" not in canonical:
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
				"div.company-info a::text",
				"a[href*='/cong-ty/']::text",
			],
		)
		salary = self._first_text(page, ["span.salary::text", "div.salary::text", "li.salary::text"])
		location = self._first_text(
			page,
			[
				"span.location::text",
				"div.location::text",
				"li.address::text",
			],
		)
		deadline = self._first_text(
			page,
			["span.deadline::text", "li.expired-date::text", "div.expired-date::text"],
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
			"job_description": self._join_text(page, "section.job-description, div.job-detail"),
			"requirements": self._join_text(page, "section.job-requirements, div.job-requirements"),
			"benefits": self._join_text(page, "section.job-benefits, div.job-benefits"),
			"job_deadline": deadline,
			"job_url": self._to_absolute_detail_url(url),
			"source": self.source_name,
			"scraped_at": datetime.now().isoformat(),
		}


if __name__ == "__main__":
	scraper = JobokoScraper()
	links = scraper.run_links_only()
	print(f"Total dedup links: {len(links)}")
