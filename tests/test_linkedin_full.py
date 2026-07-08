"""
test_linkedin_full.py — Integration test: LinkedIn scraper collect + parse.
Chạy: python tests/test_linkedin_full.py
"""
import json
import sys

from dotenv import load_dotenv
load_dotenv()

from src.extract.job_online.linkedin import LinkedInScraperV2


def main():
    print("Initializing LinkedInScraperV2...")
    scraper = LinkedInScraperV2()

    print("\n--- Phase 1: Collecting URLs (1 page, keyword=Data Engineer) ---")
    urls = scraper._collect_urls(pages=1, keywords=["Data Engineer"])
    print(f"Found {len(urls)} job URLs")
    if not urls:
        print("No URLs found. Exiting.")
        return

    test_url = urls[0]
    print(f"\nDetail URL: {test_url}")

    from patchright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
        )

        cookies = scraper._load_cookies()
        if cookies:
            context.add_cookies(cookies)
            print("Loaded session cookies.")

        print("\n--- Phase 3: Parsing ---")
        parsed_job = scraper._fetch_job_detail_with_playwright(test_url, context)
        print(json.dumps(parsed_job, ensure_ascii=False, indent=2))
        browser.close()


if __name__ == "__main__":
    main()
