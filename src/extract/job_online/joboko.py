import os
from datetime import datetime
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from scrapling.parser import Adaptor

from src.extract.job_online.base_scraper import BaseScraper


class JobokoScraper(BaseScraper):

	_block_media = BaseScraper._block_media
	source_name = "joboko"
	base_url = "https://vn.joboko.com"
	batch_size = 12

	DEFAULT_START_URL = "https://vn.joboko.com/jobs?l=2&ind=30"

	def __init__(self, start_url: str | None = None, **kwargs) -> None:
		super().__init__(**kwargs)
		self.start_url = self._canonicalize_list_url(start_url or self.DEFAULT_START_URL)

	# ------------------------------------------------------------------
	# URL helpers
	# ------------------------------------------------------------------
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

	# ------------------------------------------------------------------
	# Pagination
	# ------------------------------------------------------------------
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

	# ------------------------------------------------------------------
	# Phase 1: Extract job URLs from list page
	# ------------------------------------------------------------------
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
	def _find_item_content(page: Adaptor, label_keyword: str) -> str | None:
		"""
		Tìm div.item chứa div.item-content có text label_keyword,
		trả về text trong <span class="fw-bold">.
		"""
		for item in page.css("div.item"):
			content = item.css("div.item-content")
			if not content:
				continue
			full_text = " ".join(
				t.strip() for t in content.css("::text").getall() if t.strip()
			).lower()
			if label_keyword.lower() in full_text:
				val = content.css("span.fw-bold::text").get()
				if val and val.strip():
					return val.strip()
		return None

	# ------------------------------------------------------------------
	# Phase 3: Parse job detail page
	# ------------------------------------------------------------------
	def parse_job_detail(self, detail_html: str, url: str) -> dict:
		page = Adaptor(detail_html)

		# ── Tên job ─────────────────────────────────────────────────────
		# <h1 class="fz-20 fw-bold text-capitalize nw-company-hero__title">
		#   <a href="...">Thực Tập Sinh Tuyển Dụng</a> Part Time/Full Time
		# </h1>
		title = None
		title_el = page.css("h1.nw-company-hero__title")
		if title_el:
			parts = title_el.css("::text").getall()
			title = " ".join(p.strip() for p in parts if p.strip()) or None

		# ── Tên công ty ─────────────────────────────────────────────────
		# <h2><a class="... nw-company-hero__text" href="/cong-ty-...">CÔNG TY CỔ PHẦN X-MEDIA</a></h2>
		company = None
		company_a = page.css("h2 a.nw-company-hero__text")
		if company_a:
			# Lấy text trực tiếp (bỏ qua SVG/button bên trong)
			parts = [
				t.strip()
				for t in company_a.css("::text").getall()
				if t.strip()
			]
			company = " ".join(parts) or None

		# ── Địa chỉ ─────────────────────────────────────────────────────
		# <div class="nw-sidebar-company__address">
		#   <span class="fz-13 fw-medium letter-spacing-1 c-text-2">Địa chỉ công ty: Số 48 Tố Hữu...</span>
		# </div>
		location = None
		addr_el = page.css("div.nw-sidebar-company__address span.c-text-2")
		if addr_el:
			raw = addr_el.css("::text").get() or ""
			# Bỏ prefix "Địa chỉ công ty: "
			location = raw.replace("Địa chỉ công ty:", "").strip() or None

		# ── Lương ────────────────────────────────────────────────────────
		# <div class="fz-15 ... item-content">Thu nhập: <span class="fw-bold">Thỏa thuận</span></div>
		salary = None
		for div in page.css("div.item-content"):
			texts = div.css("::text").getall()
			label = " ".join(t.strip() for t in texts if t.strip()).lower()
			if "thu nhập" in label or "mức lương" in label or "lương" in label:
				val = div.css("span.fw-bold::text").get()
				if val and val.strip():
					salary = val.strip()
				break

		# ── Kinh nghiệm ─────────────────────────────────────────────────
		# <div class="item"> → <div class="item-content">Kinh nghiệm: <span class="fw-bold">2 - 4 năm</span></div>
		experience = self._find_item_content(page, "kinh nghiệm")

		# ── Hạn ứng tuyển ────────────────────────────────────────────────
		# <div class="mt-1 fz-16">Hạn nộp: 17/07/2026</div>
		deadline = None
		for div in page.css("div.mt-1.fz-16"):
			raw = " ".join(t.strip() for t in div.css("::text").getall() if t.strip())
			if "hạn nộp" in raw.lower():
				deadline = raw.replace("Hạn nộp:", "").strip() or None
				break

		# ── Loại hình làm việc ───────────────────────────────────────────
		# <div class="item-content">Loại hình: <span class="fw-bold">Toàn thời gian</span></div>
		job_type = self._find_item_content(page, "loại hình")

		# ── Cấp bậc ─────────────────────────────────────────────────────
		# <div class="item-content">Chức vụ: <span class="fw-bold">Nhân viên</span></div>
		job_position = self._find_item_content(page, "chức vụ")

		# ── Ngành nghề / Tags kỹ năng ────────────────────────────────────
		# <div class="block-tags"><a ...>phần mềm</a><a ...>sql</a>...</div>
		job_industry = None
		tags = page.css("div.block-tags a::text").getall()
		if tags:
			job_industry = ", ".join(t.strip() for t in tags if t.strip()) or None

		# ── Mô tả công việc ──────────────────────────────────────────────
		# <div class="text-left job-desc"><ul><li>...</li></ul></div>
		job_description = self._get_block_text(page, "div.job-desc")

		# ── Kỹ năng / Yêu cầu công việc ─────────────────────────────────
		# <div class="text-left job-requirement"><ul><li>...</li></ul></div>
		requirements = self._get_block_text(page, "div.job-requirement")

		# ── Phúc lợi / Quyền lợi ────────────────────────────────────────
		# <div class="text-left job-benefit"><ul><li>...</li></ul></div>
		benefits = self._get_block_text(page, "div.job-benefit")

		# ── Thông tin công ty & Website ──────────────────────────────────
		# Vào trang công ty: <a href="/cong-ty-..."><span class="c-green">Xem trang công ty</span></a>
		company_info = None
		company_website = None

		company_page_url = None
		for a_el in page.css("a"):
			href = a_el.css("::attr(href)").get() or ""
			span_text = (a_el.css("span::text").get() or "").strip()
			if "xem trang công ty" in span_text.lower() and href.startswith("/cong-ty"):
				company_page_url = urljoin(self.base_url, href.strip())
				break

		# Fallback: lấy từ link <h2 a.nw-company-hero__text> nếu có href /cong-ty-
		if not company_page_url:
			company_href = page.css("h2 a.nw-company-hero__text::attr(href)").get() or ""
			if company_href.startswith("/cong-ty"):
				company_page_url = urljoin(self.base_url, company_href.strip())

		if company_page_url:
			self.logger.info(f"Fetching company page: {company_page_url}")
			comp_html = self._fetch_html(company_page_url)
			if comp_html:
				comp_page = Adaptor(comp_html)

				# Thông tin công ty: <div class="fz-15 nw-company-hero__detail nw-wysiwyg ns-body">
				desc_el = comp_page.css("div.nw-company-hero__detail.nw-wysiwyg")
				if desc_el:
					parts = desc_el.css("::text").getall()
					lines = [p.strip() for p in parts if p.strip()]
					company_info = "\n".join(lines) or None

				# Website công ty: tìm trong sidebar các link ngoài domain joboko
				for a in comp_page.css("div.nw-sidebar-company a[href]"):
					href = a.css("::attr(href)").get() or ""
					# Lấy link không phải nội bộ joboko
					if href.startswith("http") and "joboko.com" not in href:
						company_website = href.strip()
						break

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

	# ------------------------------------------------------------------
	# Convenience wrapper (backward-compat với DAG)
	# ------------------------------------------------------------------
	def collect_all_links(
		self,
		pages: int | None = None,
		existing_urls: set[str] | None = None,
	) -> list[str]:
		raw_urls = self._collect_urls(pages)
		return self._deduplicate_urls(raw_urls, existing_urls)


if __name__ == "__main__":
	start_url = os.getenv("JOBOKO_START_URL")
	scraper = JobokoScraper(start_url=start_url)
	links = scraper.run_links_only()
	print(f"Total dedup links: {len(links)}")
