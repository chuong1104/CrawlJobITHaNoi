#!/bin/bash
# Script để cào tất cả các web, mỗi web 1 trang đầu để test qua Docker Container (Airflow)

set -e

# cd về thư mục gốc của project
cd "$(dirname "$0")/.."

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  CÀO TẤT CẢ CÁC WEBSITE (TEST 1 TRANG ĐẦU) QUA DOCKER"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Kiểm tra xem Docker có đang chạy không
if ! docker compose ps | grep -q airflow; then
    echo " Lỗi: Airflow container chưa chạy. Bạn cần chạy 'docker compose up -d' trước."
    exit 1
fi

echo "0. Đảm bảo S3 buckets đã sẵn sàng..."
docker compose exec airflow awslocal s3 mb s3://jobit-bronze 2>/dev/null || true

if [ "$1" == "--reset" ]; then
    echo " Xoá trạng thái cũ, bắt đầu cào lại từ đầu..."
    docker compose exec airflow bash -c "rm -f /opt/airflow/tests/.scrapers_state.txt"
else
    echo " Chế độ Resume đang bật. Thêm tham số '--reset' để chạy lại từ đầu."
fi

echo "1. Chạy tất cả các scraper (giới hạn 1 trang)..."
docker compose exec airflow bash -c "
cd /opt/airflow
export PYTHONPATH=/opt/airflow
python -c \"
import time
import sys
import os
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.extract.topcv import TopCVScraper
from src.extract.itviec import ITViecScraper
from src.extract.careerviet import CareerVietScraper
from src.extract.joboko import JobokoScraper
from src.extract.jobsgo import JobsGoScraper
from src.extract.vietnamworks import VietnamWorksScraper
from src.extract.job_123 import Job123Scraper
from src.extract.linkedin import LinkedInScraperV2

scrapers = [
    ('TopCV', TopCVScraper),
    ('ITViec', ITViecScraper),
    ('CareerViet', CareerVietScraper),
    ('Joboko', JobokoScraper),
    ('JobsGo', JobsGoScraper),
    ('VietnamWorks', VietnamWorksScraper),
    ('123Job', Job123Scraper),
    ('LinkedIn', LinkedInScraperV2),
]

state_file = '/opt/airflow/tests/.scrapers_state.txt'
completed = set()
if os.path.exists(state_file):
    with open(state_file, 'r') as f:
        completed = set(f.read().splitlines())

print('\nBắt đầu quá trình cào dữ liệu...')

def run_scraper(name, scraper_class):
    print(f'Bắt đầu cào {name} (1 trang)...')
    scraper = scraper_class()
    jobs = scraper.run(pages=1)
    return len(jobs)

with ThreadPoolExecutor(max_workers=5) as executor:
    futures = {}
    for name, scraper_class in scrapers:
        if name in completed:
            print(f' Bỏ qua {name} (đã chạy thành công trước đó)')
            continue
        futures[executor.submit(run_scraper, name, scraper_class)] = name
        
    for future in as_completed(futures):
        name = futures[future]
        print(f'\n========================================')
        try:
            job_count = future.result()
            print(f' {name}: Đã cào và lưu {job_count} jobs vào Bronze.')
            with open(state_file, 'a') as f:
                f.write(name + '\\n')
        except Exception as exc:
            print(f' {name}: Lỗi khi cào dữ liệu: {exc}')
            traceback.print_exc()
\"
"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   Hoàn tất quá trình cào dữ liệu cho tất cả các web!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
