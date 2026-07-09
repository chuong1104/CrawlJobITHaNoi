"""
test_bronze_live.py — Integration test: chạy TopCV scraper thật với BronzeManager.
Chạy: python tests/test_bronze_live.py
"""
import logging
import sys

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

from src.extract.topcv import TopCVScraper

if __name__ == "__main__":
    print("Testing TopCVScraper with BronzeManager")
    scraper = TopCVScraper(max_retries=1)
    results = scraper.run(pages=1)
    print(f"Total results scraped: {len(results)}")
