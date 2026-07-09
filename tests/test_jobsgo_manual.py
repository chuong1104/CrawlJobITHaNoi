"""
test_jobsgo_manual.py — Integration test: JobsGo fetch list + parse first job detail.
Chạy: docker compose exec airflow python tests/test_jobsgo_manual.py
"""
import json
import sys
import logging

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

from src.extract.jobsgo import JobsGoScraper
from scrapling import StealthyFetcher, DynamicFetcher


def test_fetcher(use_playwright: bool):
    print(f"\n--- Testing with use_playwright = {use_playwright} ---")
    scraper = JobsGoScraper(use_playwright=use_playwright)
    
    # Override standard _do_fetch to prints status or just use Scrapling directly
    url = scraper.get_list_page_url(1)
    print(f"Fetching list page: {url}")
    
    # Try fetching HTML
    html = scraper._fetch_html(url)
    if not html:
        print(f"FAILED to fetch HTML using use_playwright={use_playwright}")
        return False
        
    print(f"SUCCESS: HTML fetched. Length: {len(html)}")
    
    # Verify if valid html
    is_valid = scraper._is_valid_html(html, url)
    print(f"Is valid HTML? {is_valid}")
    if not is_valid:
        print("HTML content seems blocked (Cloudflare or error).")
        # Print a snippet of HTML
        print("HTML Snippet:")
        print(html[:1000])
        return False
        
    urls = scraper.extract_job_urls(html)
    print(f"Found {len(urls)} job URLs")
    if not urls:
        print("No URLs extracted.")
        return False
        
    print(f"Extracted URLs: {urls[:3]}")
    
    # Let's try fetching the first detail URL
    test_url = urls[0]
    print(f"Fetching detail URL: {test_url}")
    detail_html = scraper._fetch_html(test_url)
    if not detail_html:
        print("FAILED to fetch detail page.")
        return False
        
    print(f"SUCCESS: Detail HTML fetched. Length: {len(detail_html)}")
    is_detail_valid = scraper._is_valid_html(detail_html, test_url)
    print(f"Is valid detail HTML? {is_detail_valid}")
    if not is_detail_valid:
        print("Detail HTML Snippet:")
        print(detail_html[:1000])
        return False
        
    parsed_job = scraper.parse_job_detail(detail_html, test_url)
    print("Parsed job details:")
    print(json.dumps(parsed_job, ensure_ascii=False, indent=2))
    return True


def main():
    # Try Fetcher (use_playwright=False) first as it uses curl_cffi to bypass Cloudflare
    success = test_fetcher(use_playwright=False)
    if not success:
        print("Fetcher failed. Now trying DynamicFetcher (use_playwright=True)...")
        test_fetcher(use_playwright=True)


if __name__ == "__main__":
    main()

