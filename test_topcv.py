import requests
from src.extract.job_online.topcv import TopCVScraper

url = "https://www.topcv.vn/viec-lam/data-scientist/2147404.html"
scraper = TopCVScraper()

# Download html
html = requests.get(url).text
with open("test.html", "w") as f:
    f.write(html)

data = scraper.parse_job_detail(html, url)
print("Extracted Title:", data.get("title"))
print("Extracted Company:", data.get("company"))
