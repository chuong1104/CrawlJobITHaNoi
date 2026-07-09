from datetime import datetime
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from scrapling.parser import Adaptor

from src.extract.base_scraper import BaseScraper


class CareerVietScraper(BaseScraper):
	_block_media = BaseScraper._block_media
	source_name = "careerviet"
	base_url = "https://careerviet.vn"
	batch_size = 10

	DEFAULT_START_URL = (
		"https://careerviet.vn/viec-lam/cntt-phan-mem-tai-ha-noi-c1l4-vi.html"
	)

	def __init__(self, start_url: str | None = None, **kwargs) -> None:
		kwargs.setdefault("delay_range", (8.0, 15.0))
		kwargs.setdefault("max_retries", 5)
		super().__init__(**kwargs)
		self.start_url = self._clean_list_url(start_url or self.DEFAULT_START_URL)

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
		is_list_page = bool(page.css("a.job_link"))
		if not is_list_page:
			title_el = page.css("h1.title, h1.job-title, h1")
			company_el = page.css("a.employer.job-company-name, a.job-company-name, a.employer-name, a[class*='employer']")
			if not title_el and not company_el:
				return False
				
		return True

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

	@staticmethod
	def _get_li_field(page: Adaptor, keyword: str) -> str | None:
		"""
		CareerViet sidebar dùng pattern:
		  <li>
		    <strong><em class="fa fa-usd"></em>Lương</strong>
		    <p>30 Tr - 50 Tr VND</p>
		  </li>
		Tìm <li> có <strong> chứa keyword, trả về text của <p> bên trong.
		"""
		for li in page.css("li"):
			strong = li.css("strong")
			if not strong:
				continue
			strong_text = " ".join(
				t.strip() for t in strong.css("::text").getall() if t.strip()
			)
			if keyword.lower() in strong_text.lower():
				p_el = li.css("p")
				if p_el:
					parts = p_el.css("::text").getall()
					val = " ".join(p.strip() for p in parts if p.strip())
					return val or None
		return None

	@staticmethod
	def _get_section_text(page: Adaptor, h2_keyword: str) -> str | None:
		"""
		CareerViet dùng pattern:
		  <div class="detail-row ...">
		    <h2 class="detail-title">Mô tả Công việc</h2>
		    <div>...<p>...</p>...</div>
		  </div>
		Tìm h2 chứa keyword rồi lấy toàn bộ text trong div cha.
		"""
		for row in page.css("div.detail-row"):
			h2 = row.css("h2.detail-title")
			if not h2:
				continue
			h2_text = " ".join(t.strip() for t in h2.css("::text").getall() if t.strip())
			if h2_keyword.lower() in h2_text.lower():
				parts = row.css("::text").getall()
				# Bỏ qua dòng tiêu đề, lấy phần còn lại
				lines = [p.strip() for p in parts if p.strip() and p.strip() != h2_text]
				return "\n".join(lines) or None
		return None

	def parse_job_detail(self, detail_html: str, url: str) -> dict:
		page = Adaptor(detail_html)

		# ── Tên job ──────────────────────────────────────────────────────
		# <h1 class="title">Senior Data Engineer - TNTech - 3K040</h1>
		title = self._first_text(page, ["h1.title::text", "h1.job-title::text", "h1::text"])

		# ── Tên công ty ──────────────────────────────────────────────────
		# <a class="employer job-company-name" ...>Tập đoàn ROX (ROX Group)</a>
		company = self._first_text(
			page,
			[
				"a.employer.job-company-name::text",
				"a.job-company-name::text",
				"a.employer-name::text",
				"a[class*='employer']::text",
			],
		)

		# ── Địa chỉ ──────────────────────────────────────────────────────
		# <div class="job-detail__company--information-item company-address">
		#   <div class="company-value" ...>Thôn Gia Trung 1, ...</div>
		# </div>
		location_el = page.css(
			"div.job-detail__company--information-item.company-address div.company-value"
		)
		location: str | None = None
		if location_el:
			parts = location_el.css("::text").getall()
			location = " ".join(p.strip() for p in parts if p.strip()) or None
		# Fallback: lấy từ data-original-title attribute
		if not location:
			orig = page.css(
				"div.job-detail__company--information-item.company-address "
				"div.company-value::attr(data-original-title)"
			).get()
			if orig and orig.strip():
				location = orig.strip()

		# ── Lương ─────────────────────────────────────────────────────────
		# <li><strong><em class="fa fa-usd"></em>Lương</strong><p>30 Tr - 50 Tr VND</p></li>
		salary = self._get_li_field(page, "Lương")

		# ── Kinh nghiệm ───────────────────────────────────────────────────
		# <li><strong><em class="fa fa-briefcase"></em>Kinh nghiệm</strong><p>4 - 5 Năm</p></li>
		experience_level = self._get_li_field(page, "Kinh nghiệm")

		# ── Hạn ứng tuyển ─────────────────────────────────────────────────
		# <li><strong><em class="mdi mdi-calendar-check"></em><span>Hết hạn nộp</span></strong>
		#   <p style="text-align: left;">16/07/2026</p></li>
		job_deadline = self._get_li_field(page, "Hết hạn")
		if not job_deadline:
			job_deadline = self._get_li_field(page, "Hạn nộp")

		# ── Loại công việc ────────────────────────────────────────────────
		# <li><strong><em class="mdi mdi-briefcase-edit"> </em>Hình thức</strong>
		#   <p>Nhân viên chính thức</p></li>
		job_type = self._get_li_field(page, "Hình thức")

		# ── Cấp bậc ───────────────────────────────────────────────────────
		# <li><strong><em class="mdi mdi-account"></em>Cấp bậc</strong>
		#   <p>Nhân viên</p></li>
		job_position = self._get_li_field(page, "Cấp bậc")

		# ── Ngành nghề ────────────────────────────────────────────────────
		# <li><strong><em class="mdi mdi-briefcase"></em>Ngành nghề</strong>
		#   <p><a title="CNTT - Phần mềm" ...>CNTT - Phần mềm</a></p></li>
		job_industry = self._get_li_field(page, "Ngành nghề")

		# ── Mô tả công việc ───────────────────────────────────────────────
		# <div class="detail-row reset-bullet">
		#   <h2 class="detail-title">Mô tả Công việc</h2>
		#   <div><p>...</p></div>
		# </div>
		job_description = self._get_section_text(page, "Mô tả")

		# ── Yêu cầu công việc ─────────────────────────────────────────────
		# <div class="detail-row reset-bullet">
		#   <h2 class="detail-title">Yêu Cầu Công Việc</h2>
		# </div>
		requirements = self._get_section_text(page, "Yêu Cầu")

		# ── Phúc lợi ──────────────────────────────────────────────────────
		# <div class="detail-row">
		#   <h2 class="detail-title">Phúc lợi</h2>
		#   <ul class="welfare-list">
		#     <li><span class="fa fa-laptop"></span>Laptop</li>
		#     ...
		#   </ul>
		# </div>
		benefits: str | None = None
		benefits_parts: list[str] = []
		for li in page.css("ul.welfare-list li"):
			# Lấy text, bỏ qua text của icon <span class="fa ...">
			texts = [
				t.strip()
				for t in li.css("::text").getall()
				if t.strip()
			]
			if texts:
				benefits_parts.append(" ".join(texts))
		if benefits_parts:
			benefits = "\n".join(benefits_parts)
		# Fallback: lấy toàn bộ section Phúc lợi
		if not benefits:
			benefits = self._get_section_text(page, "Phúc lợi")

		# ── Thông tin công ty & Website ───────────────────────────────────
		# Bấm sang tab Tổng quan công ty → fetch trang employer riêng
		# <a data-href="#tab-2" href="/vi/nha-tuyen-dung/...">Tổng quan công ty</a>
		company_info: str | None = None
		company_website: str | None = None

		employer_href = page.css(
			"li#tabs-job-company a::attr(href), "
			"a[title='Tổng quan công ty']::attr(href)"
		).get()

		if employer_href:
			employer_url = urljoin(self.base_url, employer_href.strip())
			self.logger.info(f"Fetching employer page: {employer_url}")
			comp_html = self._fetch_html(employer_url)
			if comp_html:
				comp_page = Adaptor(comp_html)

				# Thông tin công ty: section "Giới thiệu về công ty"
				# <div class="intro-section intro-section-1">
				#   <h2 class="company-heading-title">Giới thiệu về công ty</h2>
				#   <div class="box-text more-less"><div class="main-text"><p>...</p></div></div>
				# </div>
				intro_section = comp_page.css(
					"div.intro-section div.main-text, div.intro-section .box-text"
				)
				if intro_section:
					parts = intro_section.css("::text").getall()
					lines = [p.strip() for p in parts if p.strip()]
					company_info = "\n".join(lines) or None

				# Fallback: div.content bên trong tab Tổng quan
				if not company_info:
					content_div = comp_page.css("div.content")
					if content_div:
						parts = content_div.css("::text").getall()
						lines = [p.strip() for p in parts if p.strip()]
						company_info = "\n".join(lines) or None

				# Website công ty:
				# <li><span class="mdi mdi-link"></span> Website: https://jobs.tntalent.vn/</li>
				for li in comp_page.css("li"):
					span = li.css("span.mdi-link, span.mdi.mdi-link")
					if span:
						texts = li.css("::text").getall()
						for t in texts:
							t = t.strip()
							if t.startswith("http"):
								company_website = t
								break
							# Dạng "Website: https://..."
							if "http" in t:
								# Tách phần URL
								idx = t.find("http")
								company_website = t[idx:].strip()
								break
						if company_website:
							break

				# Fallback: tìm link ngoài domain careerviet
				if not company_website:
					for a in comp_page.css("a[href]"):
						href = (a.css("::attr(href)").get() or "").strip()
						if href.startswith("http") and "careerviet.vn" not in href:
							company_website = href
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
			"job_url": self._canonicalize_job_url(url),
			"source": self.source_name,
			"scraped_at": datetime.now().isoformat(),
		}


if __name__ == "__main__":
	scraper = CareerVietScraper()
	links = scraper.run_links_only()
	print(f"Total dedup links: {len(links)}")
