"""
gold_exporter.py — Gold Layer Exporter

Đọc dữ liệu từ Silver (PostgreSQL) qua DuckDB, tính toán các bảng theo
kiến trúc Star Schema, rồi ghi kết quả ra file Parquet lên S3 (Floci/AWS).

Cấu trúc S3:
    s3://jobit-gold/
        warehouse/
            dim_date.parquet
            dim_company.parquet
            dim_location.parquet
            dim_skill.parquet
            fct_job_posting.parquet
            fct_job_skill.parquet
        mart_api/
            company_profiles.parquet
            latest_jobs_flat.parquet
            skill_stats.parquet
        mart_ml/
            job_features.parquet
            skill_cooccurrence.parquet

Chạy độc lập:
    python -m src.gold.gold_exporter

Hoặc từ script:
    python src/gold/gold_exporter.py
"""

from __future__ import annotations

import io
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import boto3
import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.exceptions import BotoCoreError, ClientError

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
POSTGRES_HOST     = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT     = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB       = os.getenv("POSTGRES_DB", "job_scraper_db")
POSTGRES_USER     = os.getenv("POSTGRES_USER", "airflow")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "airflow")

S3_ENDPOINT_URL   = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
S3_ACCESS_KEY     = os.getenv("AWS_ACCESS_KEY_ID", "test")
S3_SECRET_KEY     = os.getenv("AWS_SECRET_ACCESS_KEY", "test")
S3_REGION         = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
S3_GOLD_BUCKET    = "jobit-gold"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("gold_exporter")


# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------
_G  = "\033[32m"
_RD = "\033[31m"
_Y  = "\033[33m"
_C  = "\033[36m"
_B  = "\033[1m"
_D  = "\033[2m"
_R  = "\033[0m"


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------
@dataclass
class ExportResult:
    name: str
    success: bool
    rows: int = 0
    elapsed: float = 0.0
    error: str = ""


# ---------------------------------------------------------------------------
# DuckDB connection helper
# ---------------------------------------------------------------------------
def _build_duckdb_conn() -> duckdb.DuckDBPyConnection:
    """
    Tạo kết nối DuckDB với Postgres extension được load sẵn.
    DuckDB sẽ query Postgres trực tiếp qua postgres_scanner.
    """
    con = duckdb.connect(":memory:")
    con.execute("INSTALL postgres_scanner; LOAD postgres_scanner;")
    pg_dsn = (
        f"host={POSTGRES_HOST} port={POSTGRES_PORT} "
        f"dbname={POSTGRES_DB} user={POSTGRES_USER} password={POSTGRES_PASSWORD}"
    )
    con.execute(f"ATTACH '{pg_dsn}' AS silver (TYPE postgres, READ_ONLY);")
    log.info(f"DuckDB attached to Postgres: {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
    return con


# ---------------------------------------------------------------------------
# S3 helper
# ---------------------------------------------------------------------------
def _get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT_URL,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        region_name=S3_REGION,
    )


def _ensure_bucket(s3, bucket: str) -> None:
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError:
        s3.create_bucket(Bucket=bucket)
        log.info(f"Created bucket: {bucket}")


def _upload_parquet(s3, table: pa.Table, bucket: str, key: str) -> None:
    """Ghi PyArrow Table thành bytes Parquet rồi upload lên S3."""
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")
    buf.seek(0)
    s3.put_object(Bucket=bucket, Key=key, Body=buf.getvalue())
    log.debug(f"  Uploaded s3://{bucket}/{key}  ({table.num_rows} rows)")


# ---------------------------------------------------------------------------
# Generic export helper
# ---------------------------------------------------------------------------
def _export(
    con: duckdb.DuckDBPyConnection,
    s3,
    sql: str,
    s3_key: str,
    label: str,
) -> ExportResult:
    """Chạy SQL qua DuckDB, lấy kết quả, upload Parquet lên S3."""
    t0 = time.monotonic()
    try:
        arrow_table = con.execute(sql).arrow()
        _upload_parquet(s3, arrow_table, S3_GOLD_BUCKET, s3_key)
        elapsed = time.monotonic() - t0
        print(f"  {_G}✔{_R} {_B}{label:<35}{_R}  {_G}{arrow_table.num_rows:>6} rows{_R}  {_D}{elapsed:.1f}s{_R}")
        return ExportResult(label, True, arrow_table.num_rows, elapsed)
    except Exception as exc:
        elapsed = time.monotonic() - t0
        err = f"{type(exc).__name__}: {exc}"
        print(f"  {_RD}✖{_R} {_B}{label:<35}{_R}  {_RD}{err[:60]}{_R}")
        log.debug(f"[{label}] Full error: {exc}", exc_info=True)
        return ExportResult(label, False, 0, elapsed, err)


# ---------------------------------------------------------------------------
# SQL Definitions — giữ nguyên logic từ các dbt model cũ
# ---------------------------------------------------------------------------

# ── DIM DATE ────────────────────────────────────────────────────────────────
SQL_DIM_DATE = """
SELECT
    date_day,
    CAST(strftime(date_day::DATE, '%Y%m%d') AS INTEGER)          AS date_key,
    EXTRACT(year  FROM date_day)::INTEGER                          AS year,
    EXTRACT(month FROM date_day)::INTEGER                          AS month,
    EXTRACT(day   FROM date_day)::INTEGER                          AS day,
    EXTRACT(quarter FROM date_day)::INTEGER                        AS quarter,
    EXTRACT(dow   FROM date_day)::INTEGER                          AS day_of_week,
    EXTRACT(week  FROM date_day)::INTEGER                          AS week_of_year,
    strftime(date_day::DATE, '%A')                                 AS day_name,
    strftime(date_day::DATE, '%B')                                 AS month_name,
    CASE WHEN EXTRACT(dow FROM date_day) IN (0, 6) THEN TRUE
         ELSE FALSE END                                            AS is_weekend
FROM (
    SELECT (DATE '2024-01-01' + INTERVAL (n) DAY)::DATE AS date_day
    FROM generate_series(0, 3650) t(n)
)
"""

# ── DIM COMPANY ─────────────────────────────────────────────────────────────
SQL_DIM_COMPANY = """
SELECT
    company_id,
    normalized_name,
    display_name,
    website,
    industry,
    company_size,
    is_anonymous,
    created_at AS source_created_at
FROM silver.silver.companies
"""

# ── DIM LOCATION ─────────────────────────────────────────────────────────────
SQL_DIM_LOCATION = """
SELECT
    location_id,
    location_code,
    display_name,
    region,
    is_remote
FROM silver.silver.locations
"""

# ── DIM SKILL ────────────────────────────────────────────────────────────────
SQL_DIM_SKILL = """
SELECT
    skill_id,
    skill_code,
    display_name,
    skill_category,
    skill_subcategory,
    is_active
FROM silver.silver.skills
"""

# ── FCT JOB POSTING ──────────────────────────────────────────────────────────
SQL_FCT_JOB_POSTING = """
SELECT
    j.job_id,
    j.source_id,
    j.company_id,
    j.source_job_id,
    j.canonical_url,
    j.job_status,
    j.is_active,
    CAST(strftime(j.first_seen_at::DATE, '%Y%m%d') AS INTEGER)   AS first_seen_date_key,
    CAST(strftime(j.last_seen_at::DATE,  '%Y%m%d') AS INTEGER)   AS last_seen_date_key,
    CAST(strftime(j.closed_at::DATE,     '%Y%m%d') AS INTEGER)   AS closed_date_key,
    s.snapshot_id,
    s.title_clean,
    s.salary_min,
    s.salary_max,
    s.salary_avg,
    s.salary_currency,
    s.experience_min_years,
    s.experience_max_years,
    s.job_level,
    s.job_type,
    s.work_mode,
    s.job_family,
    CAST(strftime(s.deadline_date::DATE, '%Y%m%d') AS INTEGER)   AS deadline_date_key,
    s.is_intern,
    s.is_fresher,
    j.updated_at
FROM silver.silver.jobs j
JOIN silver.silver.job_snapshots s
  ON j.job_id = s.job_id AND s.is_current = TRUE
"""

# ── FCT JOB SKILL ─────────────────────────────────────────────────────────────
SQL_FCT_JOB_SKILL = """
SELECT
    j.job_id,
    js.skill_id,
    js.is_primary,
    js.skill_position
FROM silver.silver.jobs j
JOIN silver.silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = TRUE
JOIN silver.silver.job_snapshot_skills js ON s.snapshot_id = js.snapshot_id
"""

# ── MART API: COMPANY PROFILES ────────────────────────────────────────────────
SQL_COMPANY_PROFILES = """
WITH company_job_stats AS (
    SELECT
        company_id,
        COUNT(DISTINCT job_id)                                     AS total_jobs_posted,
        COUNT(DISTINCT CASE WHEN is_active THEN job_id END)        AS active_jobs,
        ROUND(AVG(salary_avg), 0)                                  AS avg_salary_offered
    FROM fct_job_posting
    GROUP BY company_id
)
SELECT
    c.company_id,
    c.normalized_name,
    c.display_name,
    c.website,
    c.industry,
    c.company_size,
    COALESCE(s.total_jobs_posted, 0)   AS total_jobs_posted,
    COALESCE(s.active_jobs, 0)         AS active_jobs,
    s.avg_salary_offered
FROM dim_company c
LEFT JOIN company_job_stats s ON c.company_id = s.company_id
WHERE c.is_anonymous = FALSE
"""

# ── MART API: LATEST JOBS FLAT ────────────────────────────────────────────────
SQL_LATEST_JOBS_FLAT = """
WITH job_skills_agg AS (
    SELECT
        fs.job_id,
        LIST(s.display_name) AS skill_names,
        LIST(s.skill_code)   AS skill_codes
    FROM fct_job_skill fs
    JOIN dim_skill s ON fs.skill_id = s.skill_id
    GROUP BY fs.job_id
),
job_locations_agg AS (
    SELECT
        j.job_id,
        LIST(l.display_name)   AS location_names,
        LIST(l.location_code)  AS location_codes
    FROM fct_job_posting j
    JOIN silver.silver.job_snapshot_locations sl ON j.snapshot_id = sl.snapshot_id
    JOIN dim_location l ON sl.location_id = l.location_id
    GROUP BY j.job_id
)
SELECT
    f.job_id,
    f.canonical_url,
    f.title_clean          AS job_title,
    c.display_name         AS company_name,
    c.website              AS company_website,
    c.company_size,
    COALESCE(loc.location_names,  [])  AS locations,
    COALESCE(loc.location_codes,  [])  AS location_codes,
    f.salary_min,
    f.salary_max,
    f.salary_currency,
    f.experience_min_years,
    f.experience_max_years,
    COALESCE(sk.skill_names, [])       AS skills,
    COALESCE(sk.skill_codes, [])       AS skill_codes,
    f.job_level,
    f.job_type,
    f.work_mode,
    f.first_seen_date_key,
    f.last_seen_date_key
FROM fct_job_posting f
LEFT JOIN dim_company c ON f.company_id = c.company_id
LEFT JOIN job_skills_agg sk ON f.job_id = sk.job_id
LEFT JOIN job_locations_agg loc ON f.job_id = loc.job_id
WHERE f.is_active = TRUE
"""

# ── MART API: SKILL STATS ─────────────────────────────────────────────────────
SQL_SKILL_STATS = """
SELECT
    s.skill_id,
    s.skill_code,
    s.display_name,
    s.skill_category,
    COUNT(DISTINCT fs.job_id) AS total_jobs
FROM dim_skill s
LEFT JOIN fct_job_skill fs ON s.skill_id = fs.skill_id
WHERE s.is_active = TRUE
GROUP BY 1, 2, 3, 4
ORDER BY total_jobs DESC
"""

# ── MART ML: JOB FEATURES ─────────────────────────────────────────────────────
SQL_JOB_FEATURES = """
SELECT
    f.job_id,
    f.salary_avg                              AS target_salary,
    COALESCE(f.experience_min_years, 0)       AS exp_min,
    f.job_level,
    f.job_type,
    f.work_mode,
    c.industry,
    c.company_size,
    f.title_clean,
    sk.skill_codes
FROM fct_job_posting f
LEFT JOIN dim_company c ON f.company_id = c.company_id
LEFT JOIN (
    SELECT job_id, LIST(s.skill_code) AS skill_codes
    FROM fct_job_skill fs
    JOIN dim_skill s ON fs.skill_id = s.skill_id
    GROUP BY job_id
) sk ON f.job_id = sk.job_id
WHERE f.salary_avg IS NOT NULL
"""

# ── MART ML: SKILL CO-OCCURRENCE ──────────────────────────────────────────────
SQL_SKILL_COOCCURRENCE = """
SELECT
    a.skill_id     AS skill_a_id,
    b.skill_id     AS skill_b_id,
    sa.display_name AS skill_a_name,
    sb.display_name AS skill_b_name,
    COUNT(DISTINCT a.job_id) AS co_occurrence_count
FROM fct_job_skill a
JOIN fct_job_skill b ON a.job_id = b.job_id AND a.skill_id < b.skill_id
JOIN dim_skill sa ON a.skill_id = sa.skill_id
JOIN dim_skill sb ON b.skill_id = sb.skill_id
GROUP BY 1, 2, 3, 4
HAVING COUNT(DISTINCT a.job_id) >= 3
ORDER BY co_occurrence_count DESC
"""


# ---------------------------------------------------------------------------
# Export Plan — thứ tự quan trọng (dim trước, fct sau, agg sau cùng)
# ---------------------------------------------------------------------------
EXPORT_PLAN: list[tuple[str, str, str]] = [
    # (label, s3_key, sql)
    # ── Warehouse (Star Schema) ──────────────────────────────────────────────
    ("warehouse/dim_date",          "warehouse/dim_date.parquet",          SQL_DIM_DATE),
    ("warehouse/dim_company",       "warehouse/dim_company.parquet",        SQL_DIM_COMPANY),
    ("warehouse/dim_location",      "warehouse/dim_location.parquet",       SQL_DIM_LOCATION),
    ("warehouse/dim_skill",         "warehouse/dim_skill.parquet",          SQL_DIM_SKILL),
    ("warehouse/fct_job_posting",   "warehouse/fct_job_posting.parquet",    SQL_FCT_JOB_POSTING),
    ("warehouse/fct_job_skill",     "warehouse/fct_job_skill.parquet",      SQL_FCT_JOB_SKILL),
    # ── Mart API ─────────────────────────────────────────────────────────────
    ("mart_api/company_profiles",   "mart_api/company_profiles.parquet",    SQL_COMPANY_PROFILES),
    ("mart_api/latest_jobs_flat",   "mart_api/latest_jobs_flat.parquet",    SQL_LATEST_JOBS_FLAT),
    ("mart_api/skill_stats",        "mart_api/skill_stats.parquet",         SQL_SKILL_STATS),
    # ── Mart ML ──────────────────────────────────────────────────────────────
    ("mart_ml/job_features",        "mart_ml/job_features.parquet",         SQL_JOB_FEATURES),
    ("mart_ml/skill_cooccurrence",  "mart_ml/skill_cooccurrence.parquet",   SQL_SKILL_COOCCURRENCE),
]


# ---------------------------------------------------------------------------
# Main export function
# ---------------------------------------------------------------------------
def run_gold_export(dry_run: bool = False) -> list[ExportResult]:
    """
    Chạy toàn bộ Gold Export:
      1. Kết nối DuckDB + Postgres
      2. Tạo bucket S3 nếu chưa có
      3. Xuất từng bảng theo EXPORT_PLAN
      4. In summary

    Returns:
        list[ExportResult] — kết quả từng bảng.
    """
    t_start = time.monotonic()
    width = 60
    print()
    print(f"{_B}{_C}{'━' * width}{_R}")
    print(f"{_B}{_C}{'  GOLD LAYER EXPORT':^{width}}{_R}")
    print(f"{_B}{_C}{'━' * width}{_R}")
    print(f"  {_D}Started   {_R}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  {_D}Target    {_R}s3://{S3_GOLD_BUCKET}/")
    print(f"  {_D}Tables    {_R}{len(EXPORT_PLAN)}")
    print(f"{_C}{'─' * width}{_R}")
    print()

    # ── Kết nối ─────────────────────────────────────────────────────────────
    try:
        con = _build_duckdb_conn()
        s3  = _get_s3_client()
        _ensure_bucket(s3, S3_GOLD_BUCKET)
    except Exception as exc:
        log.error(f"Không thể kết nối: {exc}")
        raise

    # ── Pre-load các dim và fact vào in-memory để agg queries tham chiếu ────
    # Các mart_bi/mart_api/mart_ml tham chiếu dim_* và fct_* không qua silver. nên ta
    # cần load chúng vào DuckDB memory trước.
    _preload_tables(con)

    # ── Xuất từng bảng ───────────────────────────────────────────────────────
    results: list[ExportResult] = []
    for label, s3_key, sql in EXPORT_PLAN:
        if dry_run:
            print(f"  {_Y}DRY-RUN{_R} {label}")
            results.append(ExportResult(label, True, 0, 0.0))
            continue
        result = _export(con, s3, sql, s3_key, label)
        results.append(result)

    # ── Summary ──────────────────────────────────────────────────────────────
    total_elapsed = time.monotonic() - t_start
    success_count = sum(1 for r in results if r.success)
    failed_count  = len(results) - success_count
    total_rows    = sum(r.rows for r in results if r.success)

    print()
    print(f"{_C}{'─' * width}{_R}")
    print(
        f"  {_D}Total time {_R}{total_elapsed:.1f}s   "
        f"{_G}✔ {success_count} ok{_R}   "
        f"{(_RD + f'✖ {failed_count} failed' + _R) if failed_count else ''}"
    )
    print(f"  {_D}Total rows {_R}{_G}{total_rows:,}{_R}")
    print(f"{_C}{'━' * width}{_R}")

    if failed_count:
        print(f"\n  {_Y}Failed tables:{_R}")
        for r in results:
            if not r.success:
                print(f"    {_RD}• {r.name}{_R}: {r.error[:80]}")
        print()

    con.close()
    return results


# ---------------------------------------------------------------------------
# Pre-load helper — nạp dim/fact vào DuckDB memory để các mart query được
# ---------------------------------------------------------------------------
def _preload_tables(con: duckdb.DuckDBPyConnection) -> None:
    """
    Tạo các DuckDB table in-memory từ dim/fct SQL để các mart query
    (agg_*, kpi_*, company_profiles, ...) có thể JOIN trực tiếp mà
    không cần prefix silver.silver.*
    """
    preload = [
        ("dim_date",        SQL_DIM_DATE),
        ("dim_company",     SQL_DIM_COMPANY),
        ("dim_location",    SQL_DIM_LOCATION),
        ("dim_skill",       SQL_DIM_SKILL),
        ("fct_job_posting", SQL_FCT_JOB_POSTING),
        ("fct_job_skill",   SQL_FCT_JOB_SKILL),
    ]
    log.info("Pre-loading dim/fact tables into DuckDB memory...")
    for name, sql in preload:
        try:
            con.execute(f"CREATE OR REPLACE TABLE {name} AS ({sql})")
            count = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            log.debug(f"  Loaded {name}: {count} rows")
        except Exception as exc:
            # Nếu Silver chưa có data thì tạo empty table để không crash
            log.warning(f"  Could not load {name}: {exc} — creating empty table")
            con.execute(f"CREATE OR REPLACE TABLE {name} AS ({sql} LIMIT 0)")
    log.info("Pre-load complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Gold Layer Exporter: Postgres → Parquet → S3")
    parser.add_argument("--dry-run", action="store_true", help="Không thực sự ghi, chỉ kiểm tra kết nối.")
    args = parser.parse_args()

    results = run_gold_export(dry_run=args.dry_run)
    failed = sum(1 for r in results if not r.success)
    raise SystemExit(0 if failed == 0 else 1)
