"""
test_linkedin_full.py — Integration test: LinkedIn scraper collect + parse.

Usage:
    python tests/test_linkedin_full.py                   # parse 1 job (default)
    python tests/test_linkedin_full.py --all             # parse tất cả URLs
    python tests/test_linkedin_full.py --limit 5         # parse 5 jobs đầu
    python tests/test_linkedin_full.py --pages 2 --all   # collect 2 trang, parse hết
    python tests/test_linkedin_full.py --keyword "Python Developer" --limit 10
"""
import argparse
import json
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from src.extract.linkedin import LinkedInScraperV2

# Paths ưu tiên cho cookie/storage_state (data/auth/ là nơi chính)
AUTH_PATHS = [
    Path("data/auth/linkedin_storage_state.json"),
    Path("data/auth/linkedin_session.json"),
    Path("data/linkedin_session.json"),  # legacy fallback
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all",     action="store_true", help="Parse tất cả URLs (bỏ giới hạn)")
    parser.add_argument("--limit",   type=int, default=1, help="Số job parse tối đa (default: 1)")
    parser.add_argument("--pages",   type=int, default=1, help="Số trang collect (default: 1)")
    parser.add_argument("--keyword", type=str, default="Data Engineer", help="Keyword tìm kiếm")
    args = parser.parse_args()

    print("Initializing LinkedInScraperV2...")
    scraper = LinkedInScraperV2()

    # ── Phase 1: Collect URLs ──────────────────────────────────────────
    print(f"\n--- Phase 1: Collecting URLs ({args.pages} page(s), keyword='{args.keyword}') ---")
    urls = scraper._collect_urls(pages=args.pages, keywords=[args.keyword])
    print(f"Found {len(urls)} job URLs")
    if not urls:
        print("No URLs found. Exiting.")
        return

    # Xác định số job cần parse
    limit = len(urls) if args.all else args.limit
    target_urls = urls[:limit]

    # ── Phase 3: Parse details ─────────────────────────────────────────
    print(f"\n--- Phase 3: Parsing {limit}/{len(urls)} jobs ---")

    from patchright.sync_api import sync_playwright

    # Tìm file storage_state hoặc cookie phù hợp
    storage_state_path = None
    cookie_path = None
    for p in AUTH_PATHS:
        if p.exists():
            if "storage_state" in p.name:
                storage_state_path = str(p)
                print(f"Found storage_state: {p}")
            else:
                cookie_path = p
                print(f"Found cookie file: {p}")
            break

    jobs = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        # Dùng storage_state nếu có (tốt nhất: giữ đủ cookies + localStorage)
        if storage_state_path:
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                ),
                storage_state=storage_state_path,
            )
            print(f"Loaded storage_state from: {storage_state_path}")
        else:
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
            )
            # Load cookie thủ công nếu không có storage_state
            cookies = scraper._load_cookies()
            if cookies:
                context.add_cookies(cookies)
                print(f"Loaded {len(cookies)} cookies manually.")
            else:
                print("WARNING: No cookies found. May not be authenticated.")

        for i, url in enumerate(target_urls, 1):
            print(f"\n[{i:02d}/{limit}] {url}")
            try:
                parsed_job = scraper._fetch_job_detail_with_playwright(url, context)
                if parsed_job:
                    jobs.append(parsed_job)
                    print(f"  ✔  title    = {parsed_job.get('title')}")
                    print(f"     company  = {parsed_job.get('company')}")
                    print(f"     salary   = {parsed_job.get('salary')}")
                    print(f"     location = {parsed_job.get('location')}")
                else:
                    print("  ✖  parse failed (None returned)")
            except Exception as exc:
                print(f"  ✖  error: {type(exc).__name__}: {exc}")

        browser.close()

    # ── Summary + full JSON output ─────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  RESULT: {len(jobs)}/{limit} jobs parsed successfully")
    print(f"{'='*60}\n")
    print(json.dumps(jobs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
