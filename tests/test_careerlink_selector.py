"""
test_careerlink_selector.py — Test CSS selectors cho CareerLink.
Chạy: python tests/test_careerlink_selector.py
"""
import requests
from scrapling.parser import Adaptor

url = "https://www.careerlink.vn/tim-viec-lam-tai/ha-noi/HN/c/cntt-phan-mem/19"
headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

resp = requests.get(url, headers=headers)
html = resp.text
page = Adaptor(html)

print("--- 1. a.job-link.clickable-outside ---")
links1 = page.css("a.job-link.clickable-outside::attr(href)").getall()
print(f"Tìm thấy: {len(links1)} links")
if links1:
    print("Mẫu:", links1[:3])

print("\n--- 2. a.job-link ---")
links2 = page.css("a.job-link::attr(href)").getall()
print(f"Tìm thấy: {len(links2)} links")
if links2:
    print("Mẫu:", links2[:3])

print("\n--- 3. a[href*='/tim-viec-lam/'] ---")
all_links = page.css("a::attr(href)").getall()
job_links = [l for l in all_links if l and "/tim-viec-lam/" in l]
print(f"Tìm thấy: {len(job_links)}")
if job_links:
    print("Mẫu:", list(set(job_links))[:5])
