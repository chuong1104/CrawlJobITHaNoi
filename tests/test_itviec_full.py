"""
test_itviec_full.py — Integration test: ITViec login + fetch + parse.
Chạy: python tests/test_itviec_full.py
"""
import json
import sys

from dotenv import load_dotenv
load_dotenv()

from src.extract.itviec import ITViecScraper


def main():
    print("Initializing ITViecScraper...")
    scraper = ITViecScraper()

    print("\n--- Phase 0: Login ---")
    logged_in = scraper._perform_login()
    print(f"Login success: {logged_in}")

    print("\n--- Phase 1: Collecting URLs (Page 1) ---")
    urls = scraper.extract_job_urls(scraper._fetch_html(scraper.get_list_page_url(1)))
    print(f"Found {len(urls)} job URLs")
    if not urls:
        print("No URLs found. Exiting.")
        return

    test_url = urls[0]
    print(f"\nDetail URL: {test_url}")
    detail_html = scraper._fetch_html(test_url)
    if not detail_html:
        print("Failed to fetch detail HTML.")
        return

    print("\n--- Phase 3: Parsing ---")
    parsed_job = scraper.parse_job_detail(detail_html, test_url)
    print(json.dumps(parsed_job, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
