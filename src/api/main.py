"""
api/index.py — FastAPI Backend với Connection Pooling & In-memory Caching.

Tối ưu v2.0:
  - SQLAlchemy connection pool (pool_size=5, max_overflow=10, pool_pre_ping=True)
    → Tái sử dụng kết nối DB thay vì mở mới liên tục
  - TTL Cache (functools.lru_cache + time-based expiry) cho các endpoint
    thống kê nặng (skill stats, company stats, v.v.)
    → Giảm tải cho PostgreSQL Gold DWH
  - Async request handling với FastAPI + asyncpg
"""
import os
import re
import time
import logging
from functools import wraps
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database Engine — Connection Pool
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://airflow:airflow@postgres:5432/job_scraper_db"
)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


# QueuePool: duy trì pool_size kết nối thường trực,
# cho phép thêm max_overflow kết nối tạm khi bận.
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=5,           # Số kết nối thường trực trong pool
    max_overflow=10,       # Số kết nối tạm thêm khi pool đầy
    pool_timeout=30,       # Thời gian chờ lấy connection từ pool (giây)
    pool_recycle=3600,     # Tái tạo connection sau 1 tiếng (tránh idle timeout)
    pool_pre_ping=True,    # Kiểm tra connection còn sống trước khi dùng
    echo=False,
)

# ---------------------------------------------------------------------------
# Simple TTL Cache (không cần Redis, dùng dict + timestamp)
# ---------------------------------------------------------------------------
_cache: dict[str, tuple[Any, float]] = {}


def ttl_cache(seconds: int = 300):
    """
    Decorator cache kết quả hàm trong `seconds` giây.
    Key = tên hàm + arguments.
    Thread-safe cho FastAPI (single-process).
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{args}:{sorted(kwargs.items())}"
            now = time.monotonic()

            # Cache hit: trả về ngay nếu còn trong thời hạn
            if cache_key in _cache:
                result, cached_at = _cache[cache_key]
                if now - cached_at < seconds:
                    return result

            # Cache miss: gọi hàm thật và lưu vào cache
            result = func(*args, **kwargs)
            _cache[cache_key] = (result, now)
            return result
        return wrapper
    return decorator


def invalidate_cache():
    """Xóa toàn bộ cache (gọi sau khi pipeline chạy xong)."""
    _cache.clear()
    logger.info("Cache đã được xóa.")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="JobITVN API",
    description="API phục vụ Dashboard và thống kê Data Engineering Pipeline JobITVN",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helper: Thực thi query an toàn với connection pool
# ---------------------------------------------------------------------------
def _query(sql: str, params: dict | None = None) -> list[dict]:
    """
    Thực thi SQL query, trả về list of dicts.
    Connection được lấy từ pool và tự động trả về sau khi xong.
    """
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        cols = result.keys()
        return [dict(zip(cols, row)) for row in result.fetchall()]


def clean_deadline(val: Optional[str]) -> Optional[str]:
    if not val:
        return None
    val = val.strip()
    if val in ("NaN", "nan", "None", "none", ""):
        return None
    
    # 1. Match DD/MM/YYYY at the beginning
    match = re.match(r'^(\d{2}/\d{2}/\d{4})', val)
    if match:
        return match.group(1)
        
    # 2. Match "Hết hạn trong X ngày"
    match_days = re.match(r'^(Hết hạn trong \d+ ngày)', val, re.IGNORECASE)
    if match_days:
        return match_days.group(1)
        
    # 3. Match any DD/MM/YYYY pattern anywhere in the string
    match_any = re.search(r'(\d{2}/\d{2}/\d{4})', val)
    if match_any:
        return match_any.group(1)
        
    # 4. If it is too long, truncate it
    if len(val) > 25:
        return val[:22] + "..."
    return val


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["System"])
def health_check():
    """Kiểm tra trạng thái API và kết nối database."""
    try:
        _query("SELECT 1")
        pool_status = {
            "pool_size": engine.pool.size(),
            "checked_in": engine.pool.checkedin(),
            "checked_out": engine.pool.checkedout(),
            "overflow": engine.pool.overflow(),
        }
        return {"status": "ok", "db": "connected", "pool": pool_status}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB unavailable: {e}")


@app.get("/jobs", tags=["Jobs"])
@ttl_cache(seconds=60)
def get_jobs(
    limit: int = Query(default=10, le=100),
    page: int = Query(default=1, ge=1),
    source: Optional[str] = Query(default=None),
    is_active: bool = Query(default=True),
    search: Optional[str] = Query(default=None),
    location: Optional[str] = Query(default=None),
    salary: Optional[str] = Query(default=None),
    experience: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),  # 'active', 'expiring_soon', 'expired'
    sort: Optional[str] = Query(default="newest")  # 'newest', 'oldest', 'deadline_asc', 'deadline_desc', 'salary_desc', 'salary_asc'
):
    offset = (page - 1) * limit
    base_sql = """
        SELECT
            j.job_id,
            s.title_clean,
            c.display_name AS company_name,
            COALESCE(
                (
                    SELECT loc.display_name 
                    FROM silver.job_snapshot_locations jsl 
                    JOIN silver.locations loc ON jsl.location_id = loc.location_id 
                    WHERE jsl.snapshot_id = s.snapshot_id 
                    LIMIT 1
                ),
                CASE 
                    WHEN s.title_clean ILIKE '%Hồ Chí Minh%' OR s.title_clean ILIKE '%HCM%' OR s.title_clean ILIKE '%HCMC%' OR s.title_clean ILIKE '%Sài Gòn%' THEN 'Hồ Chí Minh'
                    WHEN s.title_clean ILIKE '%Đà Nẵng%' OR s.title_clean ILIKE '%ĐN%' THEN 'Đà Nẵng'
                    ELSE 'Hà Nội'
                END
            ) AS location_clean,
            s.salary_raw,
            s.salary_min,
            s.salary_max,
            s.experience_min_years,
            s.experience_max_years,
            s.experience_raw,
            COALESCE(TO_CHAR(s.deadline_date, 'DD/MM/YYYY'), s.deadline_raw) AS deadline_raw,
            s.deadline_date,
            CASE 
                WHEN s.deadline_date IS NOT NULL AND s.deadline_date < CURRENT_DATE THEN TRUE 
                ELSE FALSE 
            END AS is_expired,
            CASE 
                WHEN s.deadline_date IS NOT NULL THEN (s.deadline_date - CURRENT_DATE)
                ELSE NULL 
            END AS remaining_days,
            src.display_name AS source_name,
            j.canonical_url,
            j.is_active,
            j.created_at,
            j.last_seen_at
        FROM silver.jobs j
        JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = true
        JOIN silver.companies c ON j.company_id = c.company_id
        JOIN silver.sources src ON j.source_id = src.source_id
        LEFT JOIN silver.job_duplicate_groups dg ON j.duplicate_group_id = dg.group_id
        WHERE j.is_active = :is_active
          AND (j.duplicate_group_id IS NULL OR j.job_id = dg.canonical_job_id)
          AND COALESCE(s.title_clean, '') NOT IN ('NaN', 'nan', '')
          AND COALESCE(c.display_name, '') NOT IN ('NaN', 'nan', '')
    """
    params: dict = {"is_active": is_active, "limit": limit, "offset": offset}

    if source and source != "all":
        base_sql += " AND (src.display_name ILIKE :source OR src.source_code ILIKE :source)"
        params["source"] = source

    if search:
        base_sql += " AND (s.title_clean ILIKE :search OR c.display_name ILIKE :search OR s.description ILIKE :search)"
        params["search"] = f"%{search}%"

    if location:
        if location in ("Hà Nội", "ha_noi"):
            base_sql += """ AND (
                s.title_clean ILIKE '%Hà Nội%' OR s.title_clean ILIKE '%HN%'
                OR EXISTS (
                    SELECT 1 FROM silver.job_snapshot_locations jsl 
                    JOIN silver.locations loc ON jsl.location_id = loc.location_id 
                    WHERE jsl.snapshot_id = s.snapshot_id AND loc.location_code = 'ha_noi'
                )
                OR (
                    NOT EXISTS (SELECT 1 FROM silver.job_snapshot_locations jsl WHERE jsl.snapshot_id = s.snapshot_id)
                    AND s.title_clean NOT ILIKE '%Hồ Chí Minh%' AND s.title_clean NOT ILIKE '%HCM%' AND s.title_clean NOT ILIKE '%Đà Nẵng%'
                )
            )"""
        elif location in ("Hồ Chí Minh", "TP. Hồ Chí Minh", "ho_chi_minh", "HCM"):
            base_sql += """ AND (
                s.title_clean ILIKE '%Hồ Chí Minh%' OR s.title_clean ILIKE '%HCM%' OR s.title_clean ILIKE '%HCMC%' OR s.title_clean ILIKE '%Sài Gòn%'
                OR EXISTS (
                    SELECT 1 FROM silver.job_snapshot_locations jsl 
                    JOIN silver.locations loc ON jsl.location_id = loc.location_id 
                    WHERE jsl.snapshot_id = s.snapshot_id AND loc.location_code = 'ho_chi_minh'
                )
            )"""
        elif location in ("Đà Nẵng", "da_nang"):
            base_sql += """ AND (
                s.title_clean ILIKE '%Đà Nẵng%' OR s.title_clean ILIKE '%ĐN%'
                OR EXISTS (
                    SELECT 1 FROM silver.job_snapshot_locations jsl 
                    JOIN silver.locations loc ON jsl.location_id = loc.location_id 
                    WHERE jsl.snapshot_id = s.snapshot_id AND loc.location_code = 'da_nang'
                )
            )"""
        elif location in ("Remote", "remote"):
            base_sql += """ AND (
                s.title_clean ILIKE '%Remote%' OR s.title_clean ILIKE '%Từ xa%' OR s.title_clean ILIKE '%Hybrid%' OR s.work_mode::text IN ('REMOTE', 'HYBRID')
            )"""
        else:
            params["location"] = f"%{location}%"
            base_sql += """ AND (
                s.title_clean ILIKE :location
                OR EXISTS (
                    SELECT 1 FROM silver.job_snapshot_locations jsl 
                    JOIN silver.locations loc ON jsl.location_id = loc.location_id 
                    WHERE jsl.snapshot_id = s.snapshot_id AND loc.display_name ILIKE :location
                )
            )"""

    if salary == "negotiable":
        base_sql += " AND (s.salary_min IS NULL AND s.salary_max IS NULL)"
    elif salary == "under_15":
        base_sql += " AND (s.salary_min < 15000000 OR s.salary_max < 15000000)"
    elif salary == "15_30":
        base_sql += " AND (s.salary_min BETWEEN 15000000 AND 30000000 OR s.salary_max BETWEEN 15000000 AND 30000000)"
    elif salary == "over_30":
        base_sql += " AND (s.salary_max > 30000000 OR s.salary_min > 30000000)"

    if experience == "no_exp":
        base_sql += """ AND (
            s.experience_min_years = 0 
            OR s.is_fresher = TRUE 
            OR s.is_intern = TRUE
            OR s.experience_raw ILIKE '%không yêu cầu%'
            OR s.experience_raw ILIKE '%fresher%'
        )"""
    elif experience == "1_3_years":
        base_sql += """ AND (
            (s.experience_min_years BETWEEN 1 AND 3) 
            OR (s.experience_max_years BETWEEN 1 AND 3)
            OR (s.experience_raw ~* '(1|2|3)\s*năm')
        )"""
    elif experience == "3_5_years":
        base_sql += """ AND (
            (s.experience_min_years BETWEEN 3 AND 5) 
            OR (s.experience_max_years BETWEEN 3 AND 5)
            OR (s.experience_raw ~* '(3|4|5)\s*năm')
        )"""
    elif experience in ("over_3_years", "over_5_years"):
        threshold = 5 if experience == "over_5_years" else 3
        base_sql += f""" AND (
            s.experience_min_years >= {threshold} 
            OR s.experience_max_years >= {threshold}
            OR s.experience_raw ILIKE '%trên {threshold}%'
        )"""

    # Lọc hạn nộp (Deadline status filter)
    if status == "active":
        base_sql += " AND (s.deadline_date IS NULL OR s.deadline_date >= CURRENT_DATE)"
    elif status == "expiring_soon":
        base_sql += " AND (s.deadline_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '7 days')"
    elif status == "expired":
        base_sql += " AND (s.deadline_date IS NOT NULL AND s.deadline_date < CURRENT_DATE)"

    # Sắp xếp (Sorting logic)
    if sort == "newest":
        # Sắp xếp theo ngày cào/thấy mới nhất trước
        base_sql += " ORDER BY j.last_seen_at DESC NULLS LAST, j.job_id DESC LIMIT :limit OFFSET :offset"
    elif sort in ("oldest", "deadline_asc"):
        # Sắp hết hạn trước: Ưu tiên tin còn hạn trước
        base_sql += """ ORDER BY 
            CASE WHEN s.deadline_date IS NULL OR s.deadline_date < CURRENT_DATE THEN 1 ELSE 0 END ASC,
            s.deadline_date ASC NULLS LAST, 
            j.job_id DESC 
            LIMIT :limit OFFSET :offset"""
    elif sort == "deadline_desc":
        # Hạn nộp xa nhất trước
        base_sql += " ORDER BY s.deadline_date DESC NULLS LAST, j.job_id DESC LIMIT :limit OFFSET :offset"
    elif sort == "salary_desc":
        base_sql += " ORDER BY COALESCE(s.salary_max, s.salary_min) DESC NULLS LAST, j.job_id DESC LIMIT :limit OFFSET :offset"
    elif sort == "salary_asc":
        base_sql += " ORDER BY COALESCE(s.salary_min, s.salary_max) ASC NULLS LAST, j.job_id DESC LIMIT :limit OFFSET :offset"
    else:
        base_sql += " ORDER BY j.last_seen_at DESC NULLS LAST, j.job_id DESC LIMIT :limit OFFSET :offset"

    # Count query
    count_sql = base_sql.split("ORDER BY")[0]
    count_sql = f"SELECT COUNT(*) AS total FROM ({count_sql}) AS sub"
    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}

    try:
        jobs = _query(base_sql, params)
        for j in jobs:
            # Clean NaN strings that slipped through
            for key in ("title_clean", "company_name", "salary_raw", "deadline_raw", "location_clean"):
                val = j.get(key)
                if val in ("NaN", "nan", "None", "none", ""):
                    j[key] = None
            j["deadline_raw"] = clean_deadline(j.get("deadline_raw"))

            # Scraped date ISO string
            if j.get("last_seen_at"):
                j["scraped_at"] = j["last_seen_at"].isoformat() if hasattr(j["last_seen_at"], "isoformat") else str(j["last_seen_at"])
            elif j.get("created_at"):
                j["scraped_at"] = j["created_at"].isoformat() if hasattr(j["created_at"], "isoformat") else str(j["created_at"])

            # Clean experience display
            exp_min = j.get('experience_min_years')
            exp_max = j.get('experience_max_years')
            if exp_min is not None and exp_max is not None:
                if exp_min == exp_max:
                    j['experience_raw'] = f"{exp_min} năm" if exp_min > 0 else "Dưới 1 năm"
                else:
                    j['experience_raw'] = f"{exp_min} - {exp_max} năm"
            elif exp_min is not None:
                j['experience_raw'] = f"Từ {exp_min} năm"
            elif exp_max is not None:
                j['experience_raw'] = f"Đến {exp_max} năm"
            elif not j.get('experience_raw'):
                j['experience_raw'] = "Không yêu cầu"

        try:
            total_row = _query(count_sql, count_params)
            total = total_row[0]["total"] if total_row else 0
        except Exception:
            total = len(jobs)  # fallback

        total_pages = max(1, (total + limit - 1) // limit)

        return {
            "data": jobs,
            "total": total,
            "page": page,
            "total_pages": total_pages,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs/{job_id}", tags=["Jobs"])
def get_job_detail(job_id: int):
    sql = """
        SELECT
            j.job_id,
            s.title_clean,
            c.display_name AS company_name,
            COALESCE(
                (
                    SELECT loc.display_name 
                    FROM silver.job_snapshot_locations jsl 
                    JOIN silver.locations loc ON jsl.location_id = loc.location_id 
                    WHERE jsl.snapshot_id = s.snapshot_id 
                    LIMIT 1
                ),
                CASE 
                    WHEN s.title_clean ILIKE '%Hồ Chí Minh%' OR s.title_clean ILIKE '%HCM%' OR s.title_clean ILIKE '%HCMC%' OR s.title_clean ILIKE '%Sài Gòn%' THEN 'Hồ Chí Minh'
                    WHEN s.title_clean ILIKE '%Đà Nẵng%' OR s.title_clean ILIKE '%ĐN%' THEN 'Đà Nẵng'
                    ELSE 'Hà Nội'
                END
            ) AS location_clean,
            s.salary_raw,
            s.experience_min_years,
            s.experience_max_years,
            s.experience_raw,
            COALESCE(TO_CHAR(s.deadline_date, 'DD/MM/YYYY'), s.deadline_raw) AS deadline_raw,
            s.deadline_date,
            CASE 
                WHEN s.deadline_date IS NOT NULL AND s.deadline_date < CURRENT_DATE THEN TRUE 
                ELSE FALSE 
            END AS is_expired,
            CASE 
                WHEN s.deadline_date IS NOT NULL THEN (s.deadline_date - CURRENT_DATE)
                ELSE NULL 
            END AS remaining_days,
            j.canonical_url,
            src.display_name AS source_name,
            j.is_active,
            j.created_at,
            j.last_seen_at,
            s.description
        FROM silver.jobs j
        JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = true
        JOIN silver.companies c ON j.company_id = c.company_id
        JOIN silver.sources src ON j.source_id = src.source_id
        WHERE j.job_id = :job_id
    """
    try:
        data = _query(sql, {"job_id": job_id})
        if not data:
            raise HTTPException(status_code=404, detail="Job not found")
        job = data[0]

        for key in ("title_clean", "company_name", "salary_raw", "location_clean", "deadline_raw"):
            val = job.get(key)
            if val in ("NaN", "nan", "None", "none", ""):
                job[key] = None
        job["deadline_raw"] = clean_deadline(job.get("deadline_raw"))
        
        raw_desc = job.get("description") or ""
        lines = [ln for ln in raw_desc.splitlines() if ln.strip() not in ("None", "nan", "NaN", "")]
        job["description"] = "\n".join(lines) if lines else "Vui lòng truy cập đường link gốc để xem mô tả chi tiết."
            
        return job
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats/skills", tags=["Statistics"])
@ttl_cache(seconds=3600)  # Cache 1 tiếng — thống kê skill thay đổi chậm
def get_skill_stats(top_n: int = Query(default=20, le=50)):
    """
    Thống kê top N kỹ năng phổ biến nhất.
    Cache 1 tiếng vì query aggregation nặng.
    """
    sql = """
        SELECT skill_name, job_count, demand_rank AS rank
        FROM dwh.mv_salary_by_skill
        ORDER BY demand_rank ASC
        LIMIT :top_n
    """
    try:
        return {"data": _query(sql, {"top_n": top_n})}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats/companies", tags=["Statistics"])
@ttl_cache(seconds=3600)
def get_company_stats(top_n: int = Query(default=20, le=100)):
    """
    Thống kê top N công ty đăng tuyển nhiều nhất.
    """
    sql = """
        SELECT company_name, COUNT(*) AS active_job_count, COUNT(*) AS total_job_count
        FROM dwh.mv_active_jobs_summary
        GROUP BY company_name
        ORDER BY active_job_count DESC
        LIMIT :top_n
    """
    try:
        return {"data": _query(sql, {"top_n": top_n})}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats/locations", tags=["Statistics"])
@ttl_cache(seconds=3600)
def get_location_stats(top_n: int = Query(default=10, le=50)):
    """Thống kê phân bổ job theo địa điểm."""
    sql = """
        SELECT location_name, total_jobs AS job_count
        FROM dwh.mv_jobs_by_location
        ORDER BY total_jobs DESC
        LIMIT :top_n
    """
    try:
        return {"data": _query(sql, {"top_n": top_n})}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats/kpi", tags=["Statistics"])
@ttl_cache(seconds=60)
def get_kpi_summary():
    try:
        kpi_data = {}
        try:
            kpi_data_rows = _query("SELECT * FROM dwh.mv_kpi_realtime LIMIT 1")
            kpi_data = kpi_data_rows[0] if kpi_data_rows else {}
        except Exception:
            kpi_data = {}

        total_jobs = kpi_data.get("total_active_jobs", 0)
        total_companies = kpi_data.get("total_hiring_companies", 0)
        remote_jobs = kpi_data.get("total_remote_hybrid_jobs", 0)
        avg_sal = kpi_data.get("market_avg_salary_vnd") or 0
        med_sal = kpi_data.get("market_median_salary_vnd") or 0
        disclosure_rate = kpi_data.get("salary_disclosure_rate_pct", 0)

        # ── Fallback sang silver layer nếu mv_kpi_realtime chưa được refresh ──
        if not total_jobs:
            try:
                live_stats = _query("""
                    SELECT
                        COUNT(DISTINCT j.job_id) AS total_jobs,
                        COUNT(DISTINCT s.company_id) AS total_companies,
                        COUNT(DISTINCT CASE WHEN s.is_remote = true THEN j.job_id END) AS remote_jobs,
                        AVG(NULLIF(s.salary_avg_vnd, 0)) AS avg_sal,
                        COUNT(DISTINCT CASE WHEN s.salary_avg_vnd > 0 THEN j.job_id END)::numeric / NULLIF(COUNT(DISTINCT j.job_id), 0) * 100 AS disclosure_rate
                    FROM silver.jobs j
                    JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = true
                    WHERE j.is_active = true
                """)
                if live_stats and live_stats[0].get("total_jobs"):
                    row = live_stats[0]
                    total_jobs = row.get("total_jobs") or 0
                    total_companies = row.get("total_companies") or 0
                    remote_jobs = row.get("remote_jobs") or 0
                    avg_sal = row.get("avg_sal") or 0
                    disclosure_rate = row.get("disclosure_rate") or 0
            except Exception:
                pass

        # ── Top skills: thử mv_salary_by_skill trước, fallback sang silver ──
        skill_mv_sql = """
            SELECT skill_name, job_count
            FROM dwh.mv_salary_by_skill
            ORDER BY demand_rank ASC LIMIT 10
        """
        skill_silver_sql = """
            SELECT s.display_name AS skill_name, COUNT(*) AS job_count
            FROM silver.job_snapshot_skills jss
            JOIN silver.skills s ON jss.skill_id = s.skill_id
            JOIN silver.job_snapshots js ON jss.snapshot_id = js.snapshot_id
            WHERE js.is_current = true
            GROUP BY s.display_name
            ORDER BY job_count DESC
            LIMIT 10
        """
        try:
            skill_rows = _query(skill_mv_sql)
            if not skill_rows:
                skill_rows = _query(skill_silver_sql)
        except Exception:
            try:
                skill_rows = _query(skill_silver_sql)
            except Exception:
                skill_rows = []
        skills = [{"name": r.get("skill_name", ""), "count": r.get("job_count", 0)} for r in skill_rows]

        # ── New jobs 7 ngày: tính theo last_seen_at trong 7 ngày gần nhất ──
        new_jobs_sql = """
            SELECT COUNT(DISTINCT j.job_id) AS cnt
            FROM silver.jobs j
            WHERE j.is_active = true
              AND j.last_seen_at >= CURRENT_DATE - INTERVAL '7 days'
        """
        try:
            new_jobs_7d = _query(new_jobs_sql)[0].get("cnt", 0)
        except Exception:
            new_jobs_7d = 0

        # ── Fresher: query trực tiếp từ silver ──
        fresher_sql = """
            SELECT COUNT(DISTINCT j.job_id) AS cnt
            FROM silver.jobs j
            JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = true
            WHERE j.is_active = true
              AND (s.experience_min_years = 0 OR s.experience_min_years IS NULL)
        """
        try:
            fresher_jobs = _query(fresher_sql)[0].get("cnt", 0)
        except Exception:
            fresher_jobs = kpi_data.get("total_fresher_jobs", 0)

        return {
            "total_jobs":              total_jobs,
            "new_jobs_7d":             new_jobs_7d,
            "average_salary_million":  f"{avg_sal / 1_000_000:.1f} Tr" if avg_sal else "N/A",
            "median_salary":           f"{med_sal / 1_000_000:.1f}" if med_sal else "0",
            "disclosure_rate":         round(disclosure_rate or 0, 1),
            "total_companies":         total_companies,
            "fresher_jobs":            fresher_jobs,
            "remote_jobs":             remote_jobs,
            "top_skills":              skills,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats/salary-by-skill", tags=["Statistics"])
@ttl_cache(seconds=3600)
def get_salary_by_skill(top_n: int = Query(default=15, le=30)):
    """
    Lương trung bình và lương cao nhất theo kỹ năng.
    Thử mv_salary_by_skill trước, fallback sang silver layer nếu trống.
    """
    mv_sql = """
        SELECT
            skill_name,
            avg_salary       AS avg_salary_min_vnd,
            max_salary       AS max_salary_max_vnd,
            job_count,
            demand_rank
        FROM dwh.mv_salary_by_skill
        WHERE avg_salary IS NOT NULL
        ORDER BY avg_salary DESC
        LIMIT :top_n
    """
    silver_sql = """
        SELECT
            s.display_name                              AS skill_name,
            AVG(f.salary_min_vnd)                      AS avg_salary_min_vnd,
            MAX(f.salary_max_vnd)                      AS max_salary_max_vnd,
            COUNT(*)                                   AS job_count,
            RANK() OVER (ORDER BY COUNT(*) DESC)       AS demand_rank
        FROM silver.job_snapshot_skills jss
        JOIN silver.skills s  ON jss.skill_id = s.skill_id
        JOIN silver.job_snapshots js ON jss.snapshot_id = js.snapshot_id
        LEFT JOIN mart_api.latest_jobs_flat f ON f.id = js.job_id AND f.is_current = true
        WHERE js.is_current = true
        GROUP BY s.display_name
        HAVING COUNT(*) >= 3
        ORDER BY job_count DESC
        LIMIT :top_n
    """
    try:
        rows = _query(mv_sql, {"top_n": top_n})
        if not rows:
            rows = _query(silver_sql, {"top_n": top_n})
        return rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cache/invalidate", tags=["System"])
def clear_cache():
    """
    Xóa toàn bộ in-memory cache.
    Gọi endpoint này sau khi Airflow pipeline chạy xong
    để API trả về data mới nhất.
    """
    invalidate_cache()
    return {"status": "ok", "message": "Cache đã được xóa thành công."}


# ---------------------------------------------------------------------------
# Mount Static Frontend
# ---------------------------------------------------------------------------
import os
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        workers=1,
        log_level="info",
    )
