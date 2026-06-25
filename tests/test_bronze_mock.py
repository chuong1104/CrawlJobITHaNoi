"""
test_bronze_mock.py — Unit test: BronzeManager với mock data (không cần network).
Chạy: python tests/test_bronze_mock.py
"""
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

from src.storage.bronze_manager import BronzeManager
from src.config import DATA_BRONZE_DIR

if __name__ == "__main__":
    print("Testing BronzeManager with MOCK data")

    mock_records = [
        # Valid record
        {
            "title": "Data Engineer",
            "company_name": "Tech Corp",
            "source": "topcv",
            "url": "http://topcv.vn/job/123",
            "salary_raw": "1000 - 2000 USD",
            "location_raw": "Hanoi",
            "skills_raw": "Python, SQL",
        },
        # Invalid record (missing title)
        {
            "company_name": "Bad Corp",
            "source": "topcv",
            "url": "http://topcv.vn/job/999",
        },
    ]

    manager = BronzeManager(local_bronze_dir=DATA_BRONZE_DIR, s3_bucket="jobit-bronze")
    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")
    num_valid, num_rejected = manager.append_local_batch(
        source="topcv",
        date_str=date_str,
        records=mock_records,
    )
    success = manager.finalize_and_upload(
        source="topcv",
        date_str=date_str,
        total_scraped=len(mock_records),
        total_validated=num_valid,
        total_rejected=num_rejected,
        scrape_duration_seconds=1.5,
    )
    print(f"BronzeManager processing success: {success}")
