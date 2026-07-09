from src.extract.topcv import TopCVScraper

if __name__ == "__main__":
    print("Running TopCV Scraper...")
    scraper = TopCVScraper()
    jobs = scraper.run(pages=1)
    print(f"Scraped {len(jobs)} jobs")
