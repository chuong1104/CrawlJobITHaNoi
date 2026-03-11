import os
import csv
import time
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "https://jobsgo.vn"
START_URL = f"{BASE_URL}/cong-ty.html"
OUTPUT_LIST_FILE = "job_scraper_de_project/data/company_url_list_jobsgo.csv"
OUTPUT_DETAIL_FILE = "job_scraper_de_project/data/company_list_jobsgo.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_company_links(page_url):
    resp = requests.get(page_url, headers=HEADERS)
    soup = BeautifulSoup(resp.text, "html.parser")
    companies = []
    for a in soup.select("a.grid-item[href*='/tuyen-dung/']"):
        name = a.get("title") or a.select_one("h3").text.strip()
        href = urljoin(BASE_URL, a.get("href"))
        companies.append({
            "company_name": name,
            "company_url": href
        })
    return companies, soup
def crawl_company_detail(detail_url):
    resp = requests.get(detail_url, headers=HEADERS)
    soup = BeautifulSoup(resp.text, "html.parser")
    # Website chính thức
    website = None
    web_tag = soup.select_one("span a[rel='nofollow'][target='_blank']")
    if web_tag:
        website = web_tag.get("href")
    else:
        web_span = soup.select_one("span.text-truncate.me-3.d-flex.align-items-center.item-info.mb-1")
        if web_span:
            website = web_span.text.strip()
    # Địa chỉ
    address = None
    addr_li = soup.select_one("li.d-flex.align-items-start.gap-2")
    if addr_li:
        addr_span = addr_li.select_one("span")
        if addr_span:
            address = addr_span.text.strip()
    else:
        addr_span2 = soup.select_one("span[style*='white-space: normal']")
        if addr_span2:
            address = addr_span2.text.strip()
    return website, address

def get_next_page_url(soup):
    next_li = soup.select_one("ul.pagination li.next a")
    if next_li:
        return urljoin(BASE_URL, next_li.get("href"))
    return None

def crawl_company_url_list():
    all_companies = []
    page_url = START_URL
    seen_urls = set()
    page_num = 1
    while page_url:
        print(f"Crawling page {page_num}: {page_url}")
        companies, soup = get_company_links(page_url)
        for c in companies:
            if c["company_url"] not in seen_urls:
                seen_urls.add(c["company_url"])
                all_companies.append(c)
        next_url = get_next_page_url(soup)
        if next_url and next_url != page_url:
            page_url = next_url
            page_num += 1
            time.sleep(1.5)
        else:
            break
    return all_companies

def crawl_company_details_parallel(company_list, max_workers=10):
    results = []
    def fetch_detail(c):
        website, address = crawl_company_detail(c["company_url"])
        c["website"] = website
        c["address"] = address
        return c
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_company = {executor.submit(fetch_detail, c): c for c in company_list}
        for future in as_completed(future_to_company):
            try:
                result = future.result()
                results.append(result)
            except Exception as exc:
                print(f"Error fetching detail: {exc}")
    return results

def save_url_list_to_csv(companies, filename):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["company_name", "company_url"])
        writer.writeheader()
        for c in companies:
            writer.writerow(c)

def save_details_to_csv(companies, filename):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["company_name", "company_url", "website", "address"])
        writer.writeheader()
        for c in companies:
            writer.writerow(c)

if __name__ == "__main__":
    # Bước 1: Cào danh sách URL công ty
    company_list = crawl_company_url_list()
    print(f"Total company URLs: {len(company_list)}")
    save_url_list_to_csv(company_list, OUTPUT_LIST_FILE)
    print(f"Saved URL list to {OUTPUT_LIST_FILE}")

    # Bước 2: Cào chi tiết song song
    details = crawl_company_details_parallel(company_list, max_workers=10)
    print(f"Total company details: {len(details)}")
    save_details_to_csv(details, OUTPUT_DETAIL_FILE)
    print(f"Saved details to {OUTPUT_DETAIL_FILE}")
