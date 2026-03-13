import os
import csv
import time
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "https://1900.com.vn"
START_URL = f"{BASE_URL}/cong-ty?locId=3"
OUTPUT_LIST_FILE = "job_scraper_de_project/data/company_url_list_1900.csv"
OUTPUT_DETAIL_FILE = "job_scraper_de_project/data/company_list_1900.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_company_links(page_url):
    resp = requests.get(page_url, headers=HEADERS)
    soup = BeautifulSoup(resp.text, "html.parser")
    companies = []
    for div in soup.select("div.align-items-center.mb-xsm"):
        a = div.select_one("a[href*='/tong-quan/']")
        if a:
            href = a.get("href")
            href = urljoin(BASE_URL, href)
            name_tag = a.select_one("h2.employer-short-name")
            name = name_tag.text.strip() if name_tag else ""
            rating_tag = div.select_one("span.rating b")
            rating = rating_tag.text.strip() if rating_tag else ""
            companies.append({
                "company_name": name,
                "company_url": href,
                "rating": rating
            })
    return companies, soup
def crawl_company_detail(detail_url):
    resp = requests.get(detail_url, headers=HEADERS)
    soup = BeautifulSoup(resp.text, "html.parser")
    # Tên công ty
    name = ""
    name_tag = soup.select_one("h1.company-detail-name.mb-1 span")
    if name_tag:
        name = name_tag.text.strip()
    # Rating
    rating = ""
    rating_tag = soup.select_one("h1.company-detail-name.mb-1 span.rating")
    if rating_tag:
        rating = rating_tag.text.strip().replace("★", "").strip()
    # Thông tin tổng quan
    overview = {}
    for li in soup.select("ul.company-details li.d-flex"):
        label = li.select_one("label")
        if not label:
            continue
        label_text = label.text.strip().replace(":", "")
        value = ""
        a_tag = li.select_one("a")
        span_tag = li.select_one("span")
        if label_text == "Website" and a_tag:
            value = a_tag.get("href").strip()  # Lấy href thay vì text
        elif a_tag:
            value = a_tag.text.strip()
        elif span_tag:
            value = span_tag.text.strip()
        overview[label_text] = value
    # Website
    website = overview.get("Website", "")
    # Địa chỉ
    address = overview.get("Trụ sở", "")
    # Ngành
    business_sector = overview.get("Ngành", "")
    # Quy mô
    scale = overview.get("Quy mô", "")
    # Doanh thu
    revenue = overview.get("Doanh thu", "")
    # Loại hình DN
    company_type = overview.get("Loại hình DN", "")
    # Thành lập
    founded_year = overview.get("Thành lập", "")
    # Giới thiệu
    description = ""
    desc_tag = soup.select_one("div.employer-des.text-justify.mt-15.mb-15.td-content")
    if desc_tag:
        desc_span = desc_tag.select_one("span.font-weight-bold")
        desc_p = desc_tag.select_one("p")
        if desc_p:
            description = desc_p.text.strip()
    # Địa chỉ chi tiết
    address_detail = ""
    desc_div = soup.select_one("div.desc")
    if desc_div:
        address_detail = desc_div.text.strip()
        if address_detail:
            address = address_detail
    return {
        "company_name": name,
        "website": website,
        "address": address,
        "business_sector": business_sector,
        "scale": scale,
        "revenue": revenue,
        "company_type": company_type,
        "founded_year": founded_year,
        "rating": rating,
        "description": description,
        "detail_url": detail_url
    }

def get_next_page_url(soup, current_page):
    # Tìm trang tiếp theo dựa vào số trang
    pag_ul = soup.select_one("ul.pagination")
    if not pag_ul:
        return None
    next_page = current_page + 1
    next_a = pag_ul.select_one(f"a.page-link[href*='page={next_page}']")
    if next_a:
        return urljoin(BASE_URL, next_a.get("href"))
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
        next_url = get_next_page_url(soup, page_num)
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
        detail = crawl_company_detail(c["company_url"])
        # Gộp rating từ list nếu chưa có
        if not detail.get("rating") and c.get("rating"):
            detail["rating"] = c["rating"]
        return detail
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
        writer = csv.DictWriter(f, fieldnames=["company_name", "company_url", "rating"])
        writer.writeheader()
        for c in companies:
            writer.writerow(c)

def save_details_to_csv(companies, filename):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "company_name", "website", "address", "business_sector", "scale", "revenue", "company_type", "founded_year", "rating", "description", "detail_url"
        ])
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
