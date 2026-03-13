import csv
import os
from jobsgo_company_crawler import crawl_company_detail, crawl_company_details_parallel, save_details_to_csv

INPUT_FILE = "job_scraper_de_project/data/company_url_list_1900.csv"
OUTPUT_FILE = "job_scraper_de_project/data/company_list_1900_recrawl.csv"

def main():
    # Đọc danh sách URL công ty đã cào
    company_list = []
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            company_list.append(row)

    # Cào lại chi tiết (lấy website đầy đủ)
    details = crawl_company_details_parallel(company_list, max_workers=10)

    # Ghi ra file mới
    save_details_to_csv(details, OUTPUT_FILE)
    print(f"Đã cào lại website và lưu vào {OUTPUT_FILE}")

if __name__ == "__main__":
    main()