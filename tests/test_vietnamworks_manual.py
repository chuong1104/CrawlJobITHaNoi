import json
import sys
import logging

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

from src.extract.vietnamworks import VietnamWorksScraper
from scrapling import Fetcher

def test_fetcher():
    print("\n--- Testing VietnamWorks Scraper ---")
    scraper = VietnamWorksScraper()
    
    url = scraper.start_url
    print(f"Start URL: {url}")
    
    # VietnamWorks uses Playwright to collect links, let's test if we can run it.
    # We will test the _collect_urls phase for 1 page.
    print("Collecting links (this uses Playwright)...")
    try:
        urls = scraper._collect_urls(pages=1)
        print(f"Found {len(urls)} job URLs")
        if not urls:
            print("No URLs extracted.")
            return False
            
        print(f"Extracted URLs: {urls[:3]}")
        
        # Test fetching and parsing the first detail URL
        test_url = urls[0]
        print(f"Fetching detail URL: {test_url}")
        detail_html = scraper._fetch_html(test_url)
        if not detail_html:
            print("FAILED to fetch detail page.")
            return False
            
        print(f"SUCCESS: Detail HTML fetched. Length: {len(detail_html)}")
        is_detail_valid = scraper._is_valid_html(detail_html, test_url)
        print(f"Is valid detail HTML? {is_detail_valid}")
        
        parsed_job = scraper.parse_job_detail(detail_html, test_url)
        print("Parsed job details:")
        print(json.dumps(parsed_job, ensure_ascii=False, indent=2))
        return True
        
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    test_fetcher()

if __name__ == "__main__":
    main()
