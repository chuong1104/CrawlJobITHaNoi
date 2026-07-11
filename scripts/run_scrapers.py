"""
run_scrapers.py — Chạy tất cả scrapers một lần (manual trigger hoặc từ Airflow).

Usage:
    python scripts/run_scrapers.py --mode full --workers 4
    python scripts/run_scrapers.py --mode links --pages 3
"""
import argparse
import concurrent.futures
import logging
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Callable
from datetime import datetime

# Đảm bảo thư mục gốc của project luôn có trong sys.path
# khi script được chạy trực tiếp (e.g., python /opt/airflow/scripts/run_scrapers.py)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Suppress noisy 3rd-party logs trước khi import bất cứ thứ gì khác
from src.utils import suppress_noisy_loggers, setup_logger, fmt_duration

suppress_noisy_loggers()

from src.extract.careerviet import CareerVietScraper
from src.extract.itviec import ITViecScraper
from src.extract.job_123 import Job123Scraper
from src.extract.joboko import JobokoScraper
from src.extract.jobsgo import JobsGoScraper
from src.extract.topcv import TopCVScraper
from src.extract.vietnamworks import VietnamWorksScraper
from src.extract.linkedin import LinkedInScraperV2


# ---------------------------------------------------------------------------
# ANSI helpers (inline để không phụ thuộc vào thư viện)
# ---------------------------------------------------------------------------
_R = "\033[0m"
_B = "\033[1m"
_D = "\033[2m"
_G = "\033[32m"
_Y = "\033[33m"
_RD = "\033[31m"
_C = "\033[36m"
_M = "\033[35m"
_W = "\033[97m"
_BG_DARK = "\033[48;5;234m"

log = setup_logger("run_scrapers")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class RunnerItem:
    name: str
    factory: Callable[[], object]


@dataclass
class ScraperResult:
    name: str
    success: bool
    count: int
    elapsed: float
    error: str = ""


RUNNERS: list[RunnerItem] = [
    RunnerItem("careerviet",   CareerVietScraper),
    RunnerItem("itviec",       ITViecScraper),
    RunnerItem("job123",       Job123Scraper),
    RunnerItem("joboko",       JobokoScraper),
    RunnerItem("jobsgo",       JobsGoScraper),
    RunnerItem("topcv",        TopCVScraper),
    RunnerItem("vietnamworks", VietnamWorksScraper),
    RunnerItem("linkedin",     LinkedInScraperV2),
]


# ---------------------------------------------------------------------------
# Print helpers
# ---------------------------------------------------------------------------
def _print_banner(mode: str, pages: int | None, workers: int) -> None:
    width = 60
    pages_str = str(pages) if pages else "AUTO"
    print()
    print(f"{_B}{_C}{'━' * width}{_R}")
    print(f"{_B}{_C}{'  JOB SCRAPER PIPELINE':^{width}}{_R}")
    print(f"{_B}{_C}{'━' * width}{_R}")
    print(f"  {_D}Started   {_R}{_W}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{_R}")
    print(f"  {_D}Mode      {_R}{_Y}{mode.upper()}{_R}")
    print(f"  {_D}Pages     {_R}{_W}{pages_str}{_R}")
    print(f"  {_D}Workers   {_R}{_W}{workers}{_R}")
    print(f"  {_D}Scrapers  {_R}{_W}{len(RUNNERS)}{_R}")
    print(f"{_C}{'─' * width}{_R}")
    print()


def _print_scraper_start(name: str, index: int, total: int) -> None:
    print(f"  {_D}[{index:02d}/{total}]{_R}  {_C} {_B}{name:<14}{_R}  {_D}starting...{_R}")


def _print_scraper_done(result: ScraperResult, index: int, total: int) -> None:
    if result.success:
        status = f"{_G} DONE{_R}"
        detail = f"{_G}{result.count:>4} records{_R}  {_D}{fmt_duration(result.elapsed)}{_R}"
    else:
        status = f"{_RD} FAIL{_R}"
        err_short = result.error[:50].replace("\n", " ") if result.error else "unknown"
        detail = f"{_RD}{err_short}{_R}"
    print(f"  {_D}[{index:02d}/{total}]{_R}  {status} {_B}{result.name:<14}{_R}  {detail}")


def _print_summary(results: list[ScraperResult], total_elapsed: float) -> None:
    width = 60
    success_results = [r for r in results if r.success]
    failed_results  = [r for r in results if not r.success]
    total_records   = sum(r.count for r in success_results)

    print()
    print(f"{_B}{_C}{'━' * width}{_R}")
    print(f"{_B}{_C}{'  PIPELINE SUMMARY':^{width}}{_R}")
    print(f"{_B}{_C}{'━' * width}{_R}")

    # Stats row
    print(
        f"  {_D}Total time  {_R}{_W}{fmt_duration(total_elapsed):<10}{_R}  "
        f"{_D}Records  {_R}{_G}{_B}{total_records}{_R}"
    )
    print(
        f"  {_D}Scrapers    {_R}{_G} {len(success_results)} succeeded{_R}  "
        f"{_RD} {len(failed_results)} failed{_R}"
    )
    print(f"{_C}{'─' * width}{_R}")

    # Per-scraper table
    print(f"  {_D}{'SCRAPER':<14}  {'STATUS':<8}  {'RECORDS':>7}  {'TIME':>8}  ERROR{_R}")
    print(f"  {_D}{'─'*14}  {'─'*8}  {'─'*7}  {'─'*8}  {'─'*20}{_R}")

    for r in sorted(results, key=lambda x: x.name):
        if r.success:
            status_col = f"{_G} ok{_R}"
            count_col  = f"{_G}{r.count:>7}{_R}"
            err_col    = ""
        else:
            status_col = f"{_RD} fail{_R}"
            count_col  = f"{_D}{'—':>7}{_R}"
            err_col    = f"{_RD}{r.error[:30].replace(chr(10), ' ')}{_R}" if r.error else ""

        time_col = f"{_D}{fmt_duration(r.elapsed):>8}{_R}"
        print(f"  {_B}{r.name:<14}{_R}  {status_col:<8}  {count_col}  {time_col}  {err_col}")

    print(f"{_C}{'━' * width}{_R}")

    if failed_results:
        print(f"\n  {_Y}  Failed scrapers:{_R}")
        for r in failed_results:
            print(f"  {_RD}  • {r.name}{_R}: {r.error[:120]}")
        print()


# ---------------------------------------------------------------------------
# Runner logic
# ---------------------------------------------------------------------------
def _run_links_only(scraper: object, pages: int | None) -> int:
    links = scraper.run_links_only(pages=pages)
    return len(links)


def _run_full(scraper: object, pages: int | None) -> int:
    records = scraper.run(pages=pages)
    return len(records)


def _run_single_scraper(
    item: RunnerItem,
    run_fn: Callable,
    run_type: str,
    global_pages: int | None,
    index: int,
    total: int,
) -> ScraperResult:
    _print_scraper_start(item.name, index, total)
    t0 = time.monotonic()

    # Xác định số trang (pages) tự động dựa trên cờ của từng scraper
    flag_path = f"/opt/airflow/data/historical/.historical_done_{item.name}"
    is_historical_run = False

    if run_type == "auto":
        if os.path.exists(flag_path):
            pages = 10
        else:
            pages = 40
            is_historical_run = True
    elif run_type == "historical":
        pages = 40
        is_historical_run = True
    elif run_type == "incremental":
        pages = 10
    else:
        pages = global_pages
    try:
        scraper = item.factory()
        count = run_fn(scraper, pages)
        elapsed = time.monotonic() - t0
        result = ScraperResult(item.name, True, count, elapsed)

        # Nếu cào historical thành công, ghi lại cờ cho riêng web này
        if is_historical_run and result.success:
            try:
                os.makedirs(os.path.dirname(flag_path), exist_ok=True)
                with open(flag_path, "w") as f:
                    f.write(datetime.now().isoformat())
            except Exception as e:
                log.warning(f"Không thể tạo cờ {flag_path}: {e}")

    except Exception as exc:
        elapsed = time.monotonic() - t0
        err_msg = f"{type(exc).__name__}: {exc}"
        # Log full traceback ở DEBUG level để không spam terminal
        log.debug(f"[{item.name}] Full traceback:\n{traceback.format_exc()}")
        result = ScraperResult(item.name, False, 0, elapsed, err_msg)

    _print_scraper_done(result, index, total)
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
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
        "--run-type",
        choices=["auto", "historical", "incremental", "custom"],
        default="auto",
        help="auto: tự động historical/incremental; historical: cào 40 trang; incremental: cào 10 trang; custom: dùng --pages.",
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
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Hiển thị DEBUG logs (bao gồm traceback chi tiết).",
    )
    parser.add_argument(
        "--scrapers",
        type=str,
        default=None,
        help="Danh sách các scrapers cần chạy, cách nhau bằng dấu phẩy (vd: topcv,itviec). Mặc định chạy tất cả.",
    )
    parser.add_argument(
        "--exclude",
        type=str,
        default=None,
        help="Danh sách các scrapers loại trừ, cách nhau bằng dấu phẩy (vd: linkedin).",
    )
    args = parser.parse_args()

    # Xử lý logic run-type display trong banner (các logic pages detail đã dời vào _run_single_scraper)
    pages = args.pages

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        log.setLevel(logging.DEBUG)

    # Lọc scrapers theo tham số include/exclude
    selected_scrapers = RUNNERS
    if args.scrapers:
        include_names = [s.strip().lower() for s in args.scrapers.split(",")]
        selected_scrapers = [r for r in selected_scrapers if r.name in include_names]
    
    if args.exclude:
        exclude_names = [s.strip().lower() for s in args.exclude.split(",")]
        selected_scrapers = [r for r in selected_scrapers if r.name not in exclude_names]

    if not selected_scrapers:
        log.error("Không có scraper nào được chọn để chạy.")
        return 1

    # Thay đổi banner hiển thị số lượng scraper được chọn thực tế
    width = 60
    pages_str = str(pages) if pages else "AUTO"
    print()
    print(f"{_B}{_C}{'━' * width}{_R}")
    print(f"{_B}{_C}{'  JOB SCRAPER PIPELINE':^{width}}{_R}")
    print(f"{_B}{_C}{'━' * width}{_R}")
    print(f"  {_D}Started   {_R}{_W}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{_R}")
    print(f"  {_D}Mode      {_R}{_Y}{args.mode.upper()}{_R}")
    print(f"  {_D}Pages     {_R}{_W}{pages_str}{_R}")
    print(f"  {_D}Workers   {_R}{_W}{args.workers}{_R}")
    print(f"  {_D}Scrapers  {_R}{_W}{len(selected_scrapers)}{_R}")
    print(f"{_C}{'─' * width}{_R}")
    print()

    run_fn = _run_links_only if args.mode == "links" else _run_full
    results: list[ScraperResult] = []
    total = len(selected_scrapers)
    t_start = time.monotonic()

    # Gán index cho mỗi runner để hiện thị thứ tự
    indexed_runners = list(enumerate(selected_scrapers, start=1))

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_map = {
            executor.submit(_run_single_scraper, item, run_fn, args.run_type, pages, idx, total): item
            for idx, item in indexed_runners
        }
        for future in concurrent.futures.as_completed(future_map):
            item = future_map[future]
            try:
                result = future.result()
                results.append(result)
                if not result.success and args.stop_on_error:
                    log.warning("--stop-on-error: huỷ các scraper còn lại.")
                    for f in future_map:
                        f.cancel()
                    break
            except Exception as exc:
                elapsed = 0.0
                results.append(ScraperResult(item.name, False, 0, elapsed, str(exc)))
                if args.stop_on_error:
                    for f in future_map:
                        f.cancel()
                    break

    total_elapsed = time.monotonic() - t_start
    _print_summary(results, total_elapsed)

    failed_count = sum(1 for r in results if not r.success)
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
