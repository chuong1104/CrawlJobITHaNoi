from datetime import datetime
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from scrapling.parser import Adaptor

from src.extract.job_online.base_scraper import BaseScraper


class JobsGoScraper(BaseScraper):

	_block_media = BaseScraper._block_media
	source_name = "jobsgo"
	base_url = "https://jobsgo.vn"
	batch_size = 12

	DEFAULT_START_URL = "https://jobsgo.vn/viec-lam-tai-ha-noi.html"

	def __init__(self, start_url: str | None = None, **kwargs) -> None:
		kwargs.setdefault("delay_range", (8.0, 15.0))
		kwargs.setdefault("max_retries", 5)
		kwargs.setdefault("use_playwright", True)
		super().__init__(**kwargs)
		self.start_url = self._canonicalize_list_url(start_url or self.DEFAULT_START_URL)

	def _is_valid_html(self, html: str, url: str) -> bool:
		"""Kiểm tra xem trang có bị chặn hoặc lỗi không."""
		html_lower = html.lower()
		if "cf-browser-verification" in html_lower or "just a moment" in html_lower:
			return False
		if "429 too many requests" in html_lower or "mã lỗi: 429" in html_lower:
			return False
		if "503 service temporarily unavailable" in html_lower:
			return False

		page = Adaptor(html)
		is_list_page = bool(page.css("div.card.job-card a.text-decoration-none, h3.job-title a"))
		if not is_list_page:
			title_el = page.css("h1.job-title")
			company_el = page.css("h6.fw-semibold.mb-1.text-dark")
			if not title_el and not company_el:
				return False
				
		return True

	# ------------------------------------------------------------------
	# URL helpers
	# ------------------------------------------------------------------
	@staticmethod
	def _canonicalize_list_url(url: str) -> str:
		parsed = urlparse(url)
		query = parse_qs(parsed.query, keep_blank_values=True)

		keep_keys = {"page"}
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
		next_href = page.css("li.next a::attr(href)").get() or page.css(
			"ul.pagination li.next a::attr(href)"
		).get()
		if next_href:
			return urljoin(self.base_url, next_href)
		return self.get_list_page_url(page_num + 1)

	# ------------------------------------------------------------------
	# Phase 1: Extract job URLs from list page
	# ------------------------------------------------------------------
	def extract_job_urls(self, list_page_html: str) -> list[str]:
		page = Adaptor(list_page_html)
		candidate_urls: list[str] = []

		candidate_urls.extend(
			page.css("div.card.job-card a.text-decoration-none::attr(href)").getall()
		)
		candidate_urls.extend(page.css("h3.job-title a::attr(href)").getall())

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
	def _get_block_text(page: Adaptor, selector: str) -> str | None:
		"""Lấy toàn bộ inner text (multi-line) của một block section."""
		el = page.css(selector)
		if not el:
			return None
		parts = el.css("::text").getall()
		lines = [p.strip() for p in parts if p and p.strip()]
		return "\n".join(lines) or None

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

	@staticmethod
	def _find_section_text(page: Adaptor, heading_keyword: str) -> str | None:
		"""
		Tìm <h3 class="section-title"> chứa keyword, lấy nội dung div/ul tiếp theo.
		"""
		for h3 in page.css("h3.section-title"):
			h3_text = "".join(h3.css("::text").getall()).strip().lower()
			if heading_keyword.lower() in h3_text:
				# Lấy element ngay sau h3 (thường là div hoặc ul chứa <li>)
				sibling = h3.css("+ div") or h3.css("+ ul")
				if sibling:
					parts = sibling.css("::text").getall()
					lines = [p.strip() for p in parts if p and p.strip()]
					return "\n".join(lines) or None
		return None

	# ------------------------------------------------------------------
	# Phase 3: Parse job detail page
	# ------------------------------------------------------------------
	def parse_job_detail(self, detail_html: str, url: str) -> dict:
		page = Adaptor(detail_html)

		# ── Tên job ─────────────────────────────────────────────────────
		# <h1 class="job-title mb-2 mb-sm-3 fs-4">Business Development Intern</h1>
		title_el = page.css("h1.job-title")
		title = None
		if title_el:
			parts = title_el.css("::text").getall()
			title = " ".join(p.strip() for p in parts if p.strip()) or None

		# ── Tên công ty ─────────────────────────────────────────────────
		# <h6 class="fw-semibold mb-1 text-dark">Công Ty TNHH Gzone Media Việt Nam</h6>
		company_el = page.css("h6.fw-semibold.mb-1.text-dark")
		company = None
		if company_el:
			parts = company_el.css("::text").getall()
			company = " ".join(p.strip() for p in parts if p.strip()) or None

		# ── Địa chỉ ─────────────────────────────────────────────────────
		# <div class="list-place"> → <strong> → <a> (tỉnh/thành) + <span> (chi tiết)
		location = None
		list_place = page.css("div.list-place")
		if list_place:
			# Lấy tên tỉnh/thành từ <strong> <a>
			province = list_place.css("strong a::text").get()
			# Lấy địa chỉ chi tiết từ .location-extra đầu tiên (không có d-none)
			detail_span = list_place.css(
				".location-extra:not(.d-none) span::text"
			).get()
			if detail_span:
				detail_span = detail_span.strip()
			if province and detail_span:
				location = f"{detail_span}"
			elif province:
				location = province.strip()
			elif detail_span:
				location = detail_span

		# ── Lương ────────────────────────────────────────────────────────
		# <li> chứa icon pb-heroicons-banknotes → <strong> text
		salary = None
		for li in page.css("li.col-6, li.col-md-3"):
			if li.css("i.pb-heroicons-banknotes"):
				salary = li.css("strong::text").get()
				if salary:
					salary = salary.strip() or None
				break

		# ── Kinh nghiệm ─────────────────────────────────────────────────
		# <li> chứa icon pb-heroicons-square-3-stack-3d → <strong> text
		experience = None
		for li in page.css("li.col-6, li.col-md-3"):
			if li.css("i.pb-heroicons-square-3-stack-3d"):
				experience = li.css("strong::text").get()
				if experience:
					experience = experience.strip() or None
				break

		# ── Hạn ứng tuyển ────────────────────────────────────────────────
		# <p><span class="text-muted">Hạn nộp hồ sơ:</span><strong>28/06/2026...</strong></p>
		deadline = None
		for p_el in page.css("p"):
			label = p_el.css("span.text-muted::text").get() or ""
			if "hạn nộp" in label.lower():
				deadline = p_el.css("strong::text").get()
				if deadline:
					deadline = deadline.strip() or None
				break

		# ── Loại hình làm việc ───────────────────────────────────────────
		# <div class="col-12 d-flex align-items-center"> chứa icon pb-heroicons-cube
		job_type = None
		for div in page.css("div.col-12.d-flex.align-items-center"):
			if div.css("i.pb-heroicons-cube"):
				job_type = div.css("strong::text").get()
				if job_type:
					job_type = job_type.strip() or None
				break

		# ── Cấp bậc ─────────────────────────────────────────────────────
		# <div class="col-12 d-flex align-items-center"> chứa icon pb-heroicons-user
		job_position = None
		for div in page.css("div.col-12.d-flex.align-items-center"):
			if div.css("i.pb-heroicons-user"):
				job_position = div.css("strong::text").get()
				if job_position:
					job_position = job_position.strip() or None
				break

		# ── Ngành nghề ───────────────────────────────────────────────────
		# <div class="d-flex align-items-start my-4"> chứa icon pb-heroicons-squares-2x2
		job_industry = None
		for div in page.css("div.d-flex.align-items-start.my-4"):
			if div.css("i.pb-heroicons-squares-2x2"):
				links_text = div.css("strong a::text").getall()
				if links_text:
					job_industry = ", ".join(t.strip() for t in links_text if t.strip()) or None
				break

		# ── Mô tả công việc ──────────────────────────────────────────────
		# <h3 class="section-title">Mô tả công việc:</h3> → <div><ul><li>...</li></ul></div>
		job_description = self._find_section_text(page, "mô tả công việc")

		# ── Kỹ năng / Yêu cầu công việc ─────────────────────────────────
		# <h3 class="section-title">Yêu cầu công việc:</h3> → <div><ul><li>...</li></ul></div>
		requirements = self._find_section_text(page, "yêu cầu công việc")

		# ── Phúc lợi / Quyền lợi ────────────────────────────────────────
		# <h3 class="section-title">Quyền lợi được hưởng:</h3> → <div><ul><li>...</li></ul></div>
		benefits = self._find_section_text(page, "quyền lợi")

		# ── Thông tin công ty & Website ──────────────────────────────────
		# Cần vào trang công ty để lấy thông tin chi tiết:
		# <a href="https://jobsgo.vn/tuyen-dung/...html">Xem thông tin công ty</a>
		company_info = None
		company_website = None

		company_page_url = None
		for a_el in page.css("a.text-muted.text-decoration-none.fw-medium"):
			href = a_el.css("::attr(href)").get() or ""
			if "/tuyen-dung/" in href:
				company_page_url = urljoin(self.base_url, href.strip())
				break

		if company_page_url:
			self.logger.info(f"Fetching company page: {company_page_url}")
			comp_html = self._fetch_html(company_page_url)
			if comp_html:
				comp_page = Adaptor(comp_html)

				# Tìm nút "Xem thêm" rồi lấy #company-description
				# (HTML đã render sẵn nội dung dù có d-none trên nút)
				desc_el = comp_page.css("div#company-description")
				if desc_el:
					parts = desc_el.css("::text").getall()
					lines = [p.strip() for p in parts if p.strip()]
					company_info = "\n".join(lines) or None

				# Website: <li> chứa icon pb-heroicons-globe-alt → <a>
				for li in comp_page.css("li.d-flex.align-items-start.gap-2"):
					if li.css("i.pb-heroicons-globe-alt"):
						href = li.css("a::attr(href)").get()
						if href:
							company_website = href.strip() or None
						if not company_website:
							company_website = li.css("a::text").get()
							if company_website:
								company_website = company_website.strip() or None
						break

		# Fallback: lấy company_info từ trang chi tiết nếu có
		if not company_info:
			desc_el = page.css("div#company-description")
			if desc_el:
				parts = desc_el.css("::text").getall()
				lines = [p.strip() for p in parts if p.strip()]
				company_info = "\n".join(lines) or None

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


if __name__ == "__main__":
	scraper = JobsGoScraper()
	links = scraper.run_links_only()
	print(f"Total dedup links: {len(links)}")
