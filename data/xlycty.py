import pandas as pd
import httpx
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import quote
import re
import random

# =========================
# CONFIG
# =========================
INPUT_FILE = "D:\\JobITVN\\job_scraper_de_project\\data\\company_list_1900_recrawl.csv"
OUTPUT_FILE = "D:\\JobITVN\\job_scraper_de_project\\data\\output.csv"

CONCURRENCY = 50
TIMEOUT = 10

KEYWORDS = [
    "tuyển dụng", "việc làm", "ứng tuyển",
    "career", "job", "vacancy", "hiring",
    "recruitment", "join us"
]

SOFT_404 = [
    "not found", "404", "không tồn tại",
    "page not found", "error"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# =========================
# UTILS
# =========================
def is_job_page(html):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text().lower()

    if any(err in text for err in SOFT_404):
        return False

    return any(k in text for k in KEYWORDS)


def extract_links(html):
    return re.findall(r'https://[^\s"]+', html)


def search_google(company):
    query = quote(f"{company} tuyển dụng")
    url = f"https://www.google.com/search?q={query}"

    try:
        r = httpx.get(url, headers=HEADERS, timeout=10)
        return r.text
    except:
        return ""


def find_best_link(company):
    html = search_google(company)
    links = extract_links(html)

    for link in links:
        if any(x in link.lower() for x in ["career", "tuyen-dung", "jobs"]):
            return link

    return None


# =========================
# ASYNC CHECK
# =========================
async def check_url(client, url):
    try:
        resp = await client.get(url, timeout=TIMEOUT, follow_redirects=True)

        html = resp.text[:5000]  # giới hạn để nhanh hơn

        return {
            "url": url,
            "status_code": resp.status_code,
            "html": html
        }

    except Exception:
        return {
            "url": url,
            "status_code": None,
            "html": ""
        }


async def run_batch(urls):
    results = []

    limits = httpx.Limits(max_connections=CONCURRENCY)

    async with httpx.AsyncClient(limits=limits, headers=HEADERS) as client:
        tasks = [check_url(client, url) for url in urls]

        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)

    return results


# =========================
# MAIN PIPELINE
# =========================
async def main():
    print("📥 Reading CSV...")
    df = pd.read_csv(INPUT_FILE)

    urls = df["website"].fillna("").tolist()
    companies = df.get("company", [""] * len(urls))

    print(f"🚀 Processing {len(urls)} URLs...")

    results = await run_batch(urls)

    output = []

    for i, res in enumerate(results):
        url = res["url"]
        status = res["status_code"]
        html = res["html"]
        company = companies[i] if i < len(companies) else ""

        # ===== classify =====
        if status != 200:
            state = "invalid"
        else:
            if is_job_page(html):
                state = "valid"
            else:
                state = "needs_review"

        new_url = ""

        # ===== auto find new link =====
        if state == "invalid":
            new_url = find_best_link(company)

        output.append({
            "company": company,
            "website": url,
            "http_code": status,
            "status": state,
            "new_url": new_url
        })

        if i % 100 == 0:
            print(f"Processed {i}/{len(results)}")

    print("💾 Saving output...")
    out_df = pd.DataFrame(output)
    out_df.to_csv(OUTPUT_FILE, index=False)

    print("✅ Done!")


# =========================
# ENTRY POINT
# =========================
if __name__ == "__main__":
    asyncio.run(main())
