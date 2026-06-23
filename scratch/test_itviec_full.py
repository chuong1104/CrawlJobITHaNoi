import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv()

from src.extract.job_online.itviec import ITViecScraper

def main():
    print("Initializing ITViecScraper...")
    scraper = ITViecScraper()
    
    # 1. Login
    print("\n--- Phase 0: Login ---")
    logged_in = scraper._perform_login()
    print(f"Login success status: {logged_in}")

    # 2. Collect URLs (only 1 page for testing)
    print("\n--- Phase 1: Collecting URLs (Page 1 only) ---")
    urls = scraper.extract_job_urls(scraper._fetch_html(scraper.get_list_page_url(1)))
    print(f"Found {len(urls)} job URLs on page 1.")
    if not urls:
        print("No job URLs found. Exiting.")
        return
        
    test_url = urls[0]
    print(f"\nSelected first URL for detail test: {test_url}")
    
    # 3. Fetch and parse detail page.
    print(f"Fetching job detail: {test_url}")
    detail_html = scraper._fetch_html(test_url)
    
    if not detail_html:
        print("Failed to fetch detail HTML.")
        return

    print("\n--- Phase 3: Parsing Detail HTML ---")
    parsed_job = scraper.parse_job_detail(detail_html, test_url)
    
    print("\nParsed job details:")
    import json
    print(json.dumps(parsed_job, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
