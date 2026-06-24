"""
run_scrapers.py — Chạy tất cả scrapers một lần (manual trigger hoặc từ Airflow).

Usage:
    python scripts/run_scrapers.py --mode full --workers 4
    python scripts/run_scrapers.py --mode links --pages 3
"""
import argparse
import concurrent.futures
import traceback
from dataclasses import dataclass
from typing import Callable

from src.extract.job_online.careerlink import CareerLinkScraper
from src.extract.job_online.careerviet import CareerVietScraper
from src.extract.job_online.itviec import ITViecScraper
from src.extract.job_online.job_123 import Job123Scraper
from src.extract.job_online.joboko import JobokoScraper
from src.extract.job_online.jobsgo import JobsGoScraper
from src.extract.job_online.topcv import TopCVScraper
from src.extract.job_online.vietnamworks import VietnamWorksScraper
from src.extract.job_online.linkedin import LinkedInScraperV2


@dataclass
class RunnerItem:
    name: str
    factory: Callable[[], object]


RUNNERS: list[RunnerItem] = [
    RunnerItem("careerlink",   CareerLinkScraper),
    RunnerItem("careerviet",   CareerVietScraper),
    RunnerItem("itviec",       ITViecScraper),
    RunnerItem("job123",       Job123Scraper),
    RunnerItem("joboko",       JobokoScraper),
    RunnerItem("jobsgo",       JobsGoScraper),
    RunnerItem("topcv",        TopCVScraper),
    RunnerItem("vietnamworks", VietnamWorksScraper),
    RunnerItem("linkedin",     LinkedInScraperV2),
]


def _run_links_only(scraper: object, pages: int | None) -> int:
    links = scraper.run_links_only(pages=pages)
    return len(links)


def _run_full(scraper: object, pages: int | None) -> int:
    records = scraper.run(pages=pages)
    return len(records)


def _run_single_scraper(
    item: RunnerItem,
    run_fn: Callable,
    pages: int | None,
) -> tuple[str, bool, int, Exception | None]:
    print(f"\n=== [{item.name}] START ===")
    try:
        scraper = item.factory()
        count = run_fn(scraper, pages)
        print(f"=== [{item.name}] DONE | total={count} ===")
        return (item.name, True, count, None)
    except Exception as exc:
        err_msg = traceback.format_exc()
        print(f"=== [{item.name}] FAILED | {exc} ===\n{err_msg}")
        return (item.name, False, 0, exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all configured scrapers one time.")
    parser.add_argument(
        "--mode",
        choices=["links", "full"],
        default="links",
        help="links: chỉ cào URLs; full: cào + parse toàn bộ.",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=None,
        help="Số trang danh sách mỗi scraper. Bỏ trống để AUTO.",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Dừng ngay khi một scraper lỗi.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Số scrapers chạy song song. Mặc định: 4.",
    )
    args = parser.parse_args()

    run_fn = _run_links_only if args.mode == "links" else _run_full
    success = 0
    failed = 0

    print(f"Start: mode={args.mode}, pages={args.pages}, workers={args.workers}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(_run_single_scraper, item, run_fn, args.pages): item
            for item in RUNNERS
        }
        for future in concurrent.futures.as_completed(futures):
            item = futures[future]
            try:
                name, is_success, count, exc = future.result()
                if is_success:
                    success += 1
                else:
                    failed += 1
                    if args.stop_on_error:
                        print("Stopping due to --stop-on-error.")
                        for f in futures:
                            f.cancel()
                        break
            except Exception as exc:
                failed += 1
                print(f"Unexpected error retrieving result for {item.name}: {exc}")
                if args.stop_on_error:
                    for f in futures:
                        f.cancel()
                    break

    print(f"\n--- SUMMARY ---\nSuccess: {success}\nFailed : {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
