from datetime import datetime
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from scrapling.parser import Adaptor

from src.extract.job_online.base_scraper import BaseScraper


class ITViecScraper(BaseScraper):
		
	_block_media = BaseScraper._block_media
	source_name = "itviec"
	base_url = "https://itviec.com"
	batch_size = 15

	# URL list canh theo khu vuc Ha Noi de phu hop du lieu mau ban da xac nhan.
	DEFAULT_START_URL = "https://itviec.com/it-jobs/ha-noi"

	def __init__(self, start_url: str | None = None, **kwargs) -> None:
		super().__init__(**kwargs)
		self.start_url = self._clean_list_url(start_url or self.DEFAULT_START_URL)

	@staticmethod
	def _clean_list_url(url: str) -> str:
		"""Bo query tracking dong de co list URL on dinh."""
		parsed = urlparse(url)
		return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

	@staticmethod
	def _drop_tracking_query(url: str) -> str:
		"""Loai bo query tracking va query dong khong phuc vu dedup."""
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
		"""
		Dua URL ve dang canonical:
		- relative -> absolute
		- bo query tracking (lab_feature, click_source, job_selected...)
		- doi /it-jobs/<slug>/content?... -> /it-jobs/<slug>
		"""
		full_url = urljoin(self.base_url, (url or "").strip())
		full_url = self._drop_tracking_query(full_url)

		parsed = urlparse(full_url)
		path = parsed.path
		if path.endswith("/content"):
			path = path[: -len("/content")]

		return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))

	def get_list_page_url(self, page_num: int) -> str:
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
		next_href = page.css("div.page.next a[rel='next']::attr(href)").get() or page.css(
			"a[rel='next']::attr(href)"
		).get()
		if next_href:
			return urljoin(self.base_url, next_href)
		return self.get_list_page_url(page_num + 1)

	def extract_job_urls(self, list_page_html: str) -> list[str]:
		page = Adaptor(list_page_html)

		candidate_urls: list[str] = []

		# Uu tien attr tren card list.
		candidate_urls.extend(
			page.css("div.job-card::attr(data-search--job-selection-job-url-value)").getall()
		)

		# Fallback tu data-url trong title h3.
		candidate_urls.extend(page.css("h3[data-url]::attr(data-url)").getall())

		# Fallback tu anchor detail trong selected preview panel.
		candidate_urls.extend(
			page.css(
				"a[data-controller='utm-tracking'][target='_blank'][href*='/it-jobs/']::attr(href)"
			).getall()
		)

		links: list[str] = []
		seen: set[str] = set()

		for raw in candidate_urls:
			if not raw:
				continue
			canonical = self._canonicalize_job_url(raw)
			if "/it-jobs/" not in canonical:
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

	def parse_job_detail(self, detail_html: str, url: str) -> dict:
		page = Adaptor(detail_html)

		# Salary can be hidden by login wall.
		salary_raw = page.css("span.ips-2.fw-500::text").get()
		if salary_raw and "sign in" in salary_raw.lower():
			salary = None
		else:
			salary = salary_raw.strip() if salary_raw else None

		title = page.css("h1[class*='text-it-black']::text").get()
		if title:
			title = title.strip()

		company = page.css("a[href*='/companies/'][class*='normal-text']::text").get()
		if company:
			company = company.strip()

		location = page.css("div.d-inline-block.text-dark-grey::text").get()
		if location:
			location = location.strip()

		industry = page.css("div.d-inline-flex.text-wrap::text").get()
		if industry:
			industry = industry.strip()

		return {
			"title": title,
			"company": company,
			"salary": salary,
			"location": location,
			"job_type": None,
			"experience_level": None,
			"education_level": None,
			"job_industry": industry,
			"job_position": None,
			"job_description": self._join_text(page, "section.job-description"),
			"requirements": self._join_text(page, "section.job-experiences"),
			"benefits": self._join_text(page, "section.job-why-love-working"),
			"job_deadline": None,
			"job_url": self._canonicalize_job_url(url),
			"source": self.source_name,
			"scraped_at": datetime.now().isoformat(),
		}


if __name__ == "__main__":
	scraper = ITViecScraper()
	links = scraper.run_links_only()
	print(f"Total dedup links: {len(links)}")
