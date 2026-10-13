import os
from datetime import datetime
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from scrapling.parser import Adaptor

from src.extract.base_scraper import BaseScraper


class JobokoScraper(BaseScraper):

	_block_media = BaseScraper._block_media
	source_name = "joboko"
	base_url = "https://vn.joboko.com"
	batch_size = 12

	DEFAULT_START_URL = "https://vn.joboko.com/jobs?l=2&ind=30"

	def __init__(self, start_url: str | None = None, **kwargs) -> None:
		kwargs.setdefault("delay_range", (3.0, 6.0))
		kwargs.setdefault("max_retries", 2)
		super().__init__(**kwargs)
		self.start_url = self._canonicalize_list_url(start_url or self.DEFAULT_START_URL)
		self._company_cache: dict[str, tuple[str | None, str | None]] = {}

	def _is_valid_html(self, html: str, url: str) -> bool:
		"""Kiểm tra xem trang có bị chặn hoặc lỗi không."""
		if not html or len(html.strip()) < 200:
			return False
		html_lower = html.lower()
		if "cf-browser-verification" in html_lower or "just a moment" in html_lower or "challenges.cloudflare.com" in html_lower:
			return False
		if "429 too many requests" in html_lower or "mã lỗi: 429" in html_lower:
			return False
		if "503 service temporarily unavailable" in html_lower:
			return False

		page = Adaptor(html)
		is_list_page = bool(page.css("h2.item-title a, a.block-detail, div.nw-job-list"))
		if not is_list_page:
			if "/cong-ty" in url:
				return bool(page.css("h1, h2, div.nw-company-hero, div.nw-sidebar-company, title"))
			has_detail_content = bool(page.css("h1, h2, title, div.job-desc, div.job-requirement, div.nw-company-hero, div.item-content"))
			if not has_detail_content:
				return False
				
		return True

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
		title = None
		for sel in [
			"h1.nw-company-hero__title",
			"h1.fz-20",
			"h1.job-title",
			"h1.title",
			"div.nw-company-hero h1",
			"div.job-detail h1",
			"h1",
		]:
			title_el = page.css(sel)
			if title_el:
				parts = title_el.css("::text").getall()
				title = " ".join(p.strip() for p in parts if p.strip()) or None
				if title:
					break

		if not title:
			page_title = page.css("title::text").get() or ""
			if " - " in page_title:
				title = page_title.split(" - ")[0].strip()
			elif "|" in page_title:
				title = page_title.split("|")[0].strip()
			elif page_title:
				title = page_title.strip()

		# ── Tên công ty ─────────────────────────────────────────────────
		company = None
		for sel in [
			"h2 a.nw-company-hero__text",
			"h2.nw-company-hero__text",
			"a.nw-company-hero__text",
			"div.nw-sidebar-company a[href*='/cong-ty']",
			"h2 a",
			"a[href*='/cong-ty-']",
			"div.company-name",
		]:
			company_el = page.css(sel)
			if company_el:
				parts = [
					t.strip()
					for t in company_el.css("::text").getall()
					if t.strip()
				]
				company = " ".join(parts) or None
				if company:
					break

		# ── Địa chỉ ─────────────────────────────────────────────────────
		location = None
		for sel in [
			"div.nw-sidebar-company__address span.c-text-2",
			"div.nw-sidebar-company__address",
			"div.item:has(div.item-content) span.fw-bold",
		]:
			addr_el = page.css(sel)
			if addr_el:
				raw = " ".join(t.strip() for t in addr_el.css("::text").getall() if t.strip())
				location = raw.replace("Địa chỉ công ty:", "").replace("Địa chỉ:", "").strip() or None
				if location:
					break

		# ── Lương ────────────────────────────────────────────────────────
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
		experience = self._find_item_content(page, "kinh nghiệm")

		# ── Hạn ứng tuyển ────────────────────────────────────────────────
		deadline = None
		for div in page.css("div.mt-1.fz-16"):
			raw = " ".join(t.strip() for t in div.css("::text").getall() if t.strip())
			if "hạn nộp" in raw.lower():
				deadline = raw.replace("Hạn nộp:", "").strip() or None
				break

		# ── Loại hình làm việc ───────────────────────────────────────────
		job_type = self._find_item_content(page, "loại hình")

		# ── Cấp bậc ─────────────────────────────────────────────────────
		job_position = self._find_item_content(page, "chức vụ")

		# ── Ngành nghề / Tags kỹ năng ────────────────────────────────────
		job_industry = None
		tags = page.css("div.block-tags a::text").getall()
		if tags:
			job_industry = ", ".join(t.strip() for t in tags if t.strip()) or None

		# ── Mô tả công việc ──────────────────────────────────────────────
		job_description = (
			self._get_block_text(page, "div.job-desc") or
			self._get_block_text(page, "div.job-description") or
			self._get_block_text(page, "div.content-desc")
		)

		# ── Kỹ năng / Yêu cầu công việc ─────────────────────────────────
		requirements = (
			self._get_block_text(page, "div.job-requirement") or
			self._get_block_text(page, "div.job-requirements") or
			self._get_block_text(page, "div.requirements")
		)

		# ── Phúc lợi / Quyền lợi ────────────────────────────────────────
		benefits = (
			self._get_block_text(page, "div.job-benefit") or
			self._get_block_text(page, "div.job-benefits") or
			self._get_block_text(page, "div.benefits")
		)

		# ── Thông tin công ty & Website ──────────────────────────────────
		company_info = None
		company_website = None

		company_page_url = None
		for a_el in page.css("a"):
			href = a_el.css("::attr(href)").get() or ""
			span_text = (a_el.css("span::text").get() or "").strip()
			if "xem trang công ty" in span_text.lower() and href.startswith("/cong-ty"):
				company_page_url = urljoin(self.base_url, href.strip())
				break

		if not company_page_url:
			company_href = page.css("h2 a.nw-company-hero__text::attr(href)").get() or ""
			if company_href.startswith("/cong-ty"):
				company_page_url = urljoin(self.base_url, company_href.strip())

		if company_page_url:
			if company_page_url in self._company_cache:
				company_info, company_website = self._company_cache[company_page_url]
			else:
				self.logger.info(f"Fetching company page: {company_page_url}")
				comp_html = self._fetch_html(company_page_url)
				if comp_html:
					comp_page = Adaptor(comp_html)
					desc_el = comp_page.css("div.nw-company-hero__detail.nw-wysiwyg, div.company-desc, div.company-info")
					if desc_el:
						parts = desc_el.css("::text").getall()
						lines = [p.strip() for p in parts if p.strip()]
						company_info = "\n".join(lines) or None

					for a in comp_page.css("div.nw-sidebar-company a[href], a[href*='http']"):
						href = a.css("::attr(href)").get() or ""
						if href.startswith("http") and "joboko.com" not in href:
							company_website = href.strip()
							break
				self._company_cache[company_page_url] = (company_info, company_website)

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
		raw_urls = self._collect_urls(pages, existing_urls=existing_urls)
		return self._deduplicate_urls(raw_urls, existing_urls)


if __name__ == "__main__":
	start_url = os.getenv("JOBOKO_START_URL")
	scraper = JobokoScraper(start_url=start_url)
	links = scraper.run_links_only()
	print(f"Total dedup links: {len(links)}")
