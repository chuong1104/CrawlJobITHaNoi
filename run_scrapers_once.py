"""Run scraper modules once in sequence.

Usage:
    python run_scrapers_once.py
    python run_scrapers_once.py --pages 3
    python run_scrapers_once.py --mode full --pages 2
"""

from __future__ import annotations

import argparse
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
from src.extract.job_online.ybox import YboxScraper


@dataclass
class RunnerItem:
    name: str
    factory: Callable[[], object]


RUNNERS: list[RunnerItem] = [
    RunnerItem("careerlink", CareerLinkScraper),
    RunnerItem("careerviet", CareerVietScraper),
    RunnerItem("itviec", ITViecScraper),
    RunnerItem("job123", Job123Scraper),
    RunnerItem("joboko", JobokoScraper),
    RunnerItem("jobsgo", JobsGoScraper),
    RunnerItem("topcv", TopCVScraper),
    RunnerItem("vietnamworks", VietnamWorksScraper),
    RunnerItem("ybox", YboxScraper),
]


def _run_links_only(scraper: object, pages: int | None) -> int:
    links = scraper.run_links_only(pages=pages)
    return len(links)


def _run_full(scraper: object, pages: int | None) -> int:
    records = scraper.run(pages=pages)
    return len(records)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all configured scrapers one time.")
    parser.add_argument(
        "--mode",
        choices=["links", "full"],
        default="links",
        help="links: run run_links_only; full: run full scrape/parse pipeline.",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=None,
        help="Number of list pages per scraper. Omit to use AUTO mode until stop condition.",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop immediately when one scraper fails.",
    )
    args = parser.parse_args()

    run_fn = _run_links_only if args.mode == "links" else _run_full

    success = 0
    failed = 0

    print(f"Start run mode={args.mode}, pages={args.pages}")
    for item in RUNNERS:
        print(f"\n=== [{item.name}] START ===")
        try:
            scraper = item.factory()

            # CareerLink currently does not implement parse_job_detail.
            if args.mode == "full" and item.name == "careerlink":
                raise NotImplementedError(
                    "careerlink.parse_job_detail() is not implemented yet. "
                    "Use --mode links or implement detail parser first."
                )

            count = run_fn(scraper, args.pages)
            print(f"=== [{item.name}] DONE | total={count} ===")
            success += 1
        except Exception as exc:
            failed += 1
            print(f"=== [{item.name}] FAILED | {exc} ===")
            traceback.print_exc()
            if args.stop_on_error:
                print("Stop because --stop-on-error is enabled.")
                break

    print("\n--- SUMMARY ---")
    print(f"Success: {success}")
    print(f"Failed : {failed}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())