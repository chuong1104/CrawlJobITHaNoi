import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv()

from src.extract.job_online.linkedin import LinkedInScraperV2

def main():
    print("Initializing LinkedInScraperV2...")
    # By default, use_playwright is True, headless is True in base scraper, but in linkedin.py it uses headless=False in _collect_urls if we look closely, wait, let me check linkedin.py again.
    scraper = LinkedInScraperV2()
    
    print("\n--- Phase 1: Collecting URLs (Testing with 1 page and Data Engineer keyword) ---")
    urls = scraper._collect_urls(pages=1, keywords=["Data Engineer"])
    print(f"Found {len(urls)} job URLs on page 1.")
    if not urls:
        print("No job URLs found. Exiting.")
        return
        
    test_url = urls[0]
    print(f"\nSelected first URL for detail test: {test_url}")
    
    # Phase 3
    print(f"Fetching job detail: {test_url}")
    from patchright.sync_api import sync_playwright
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        
        # Load session cookies
        cookies = scraper._load_cookies()
        if cookies:
            context.add_cookies(cookies)
            print("Loaded session cookies into Playwright context.")
        
        print("\n--- Phase 3: Parsing Detail HTML ---")
        parsed_job = scraper._fetch_job_detail_with_playwright(test_url, context)
        
        print("\nParsed job details:")
        import json
        print(json.dumps(parsed_job, ensure_ascii=False, indent=2))
        
        browser.close()

if __name__ == "__main__":
    main()
