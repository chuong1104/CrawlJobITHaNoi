"""
test_123job_selector.py — Test nhanh Job123Scraper: fetch 1 trang + 1 job detail.
Chạy: python tests/test_123job_selector.py
"""
import sys

from scrapling import StealthyFetcher
from src.extract.job_123 import Job123Scraper

# ── Bước 1: Fetch trang danh sách ─────────────────────────────────────────
LIST_URL = Job123Scraper.DEFAULT_START_URL
print(f"\n[1] Fetching list page: {LIST_URL}")

scraper = Job123Scraper()
list_page = StealthyFetcher.fetch(LIST_URL, block_resources=True, network_idle=False)
list_html = scraper._adaptor_to_html(list_page)

if not list_html:
    print("ERROR: không fetch được trang danh sách!")
    sys.exit(1)

urls = scraper.extract_job_urls(list_html)
print(f"[1] Tìm thấy {len(urls)} job URLs")
for u in urls[:5]:
    print(f"    {u}")

if not urls:
    print("ERROR: không có URL nào!")
    sys.exit(1)

# ── Bước 2: Fetch + parse chi tiết job đầu tiên ───────────────────────────
test_url = urls[0]
print(f"\n[2] Fetching detail: {test_url}")

detail_page = StealthyFetcher.fetch(test_url, block_resources=True, network_idle=False)
detail_html = scraper._adaptor_to_html(detail_page)

if not detail_html:
    print("ERROR: không fetch được trang chi tiết!")
    sys.exit(1)

result = scraper.parse_job_detail(detail_html, test_url)

print("\n[2] Kết quả parse:")
for key, val in result.items():
    if val and len(str(val)) > 120:
        print(f"  {key:20s}: {str(val)[:120]}...")
    else:
        print(f"  {key:20s}: {val}")

REQUIRED = ["title", "company", "location", "salary", "deadline", "job_description"]
missing = [f for f in REQUIRED if not result.get("job_" + f.replace("job_", "")) and not result.get(f)]
if missing:
    print(f"\n⚠  Các field có thể bị None: {missing}")
else:
    print("\n✅ Tất cả field quan trọng đều có dữ liệu!")
