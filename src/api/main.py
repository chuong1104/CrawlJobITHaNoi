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
from sqlalchemy.pool import QueuePool, NullPool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database Engine — Connection Pool
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://airflow:airflow@postgres:5432/job_scraper_db"
).strip()
# Chuẩn hoá về driver psycopg2 (psycopg2-binary) bất kể Vercel/Neon cấp URL dạng nào
DATABASE_URL = re.sub(
    r"^(postgres|postgresql)(\+[a-z0-9_]+)?://",
    "postgresql+psycopg2://",
    DATABASE_URL,
    count=1,
)


# Serverless (Vercel): dùng NullPool để không giữ connection idle khi Lambda đóng băng
# Local/Docker: dùng QueuePool để tối ưu hiệu năng
is_serverless = os.getenv("VERCEL") == "1"

if is_serverless:
    engine = create_engine(
        DATABASE_URL,
        poolclass=NullPool,
        pool_pre_ping=True,
        echo=False,
    )
else:
    engine = create_engine(
        DATABASE_URL,
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=3600,
        pool_pre_ping=True,
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
    Không lưu kết quả rỗng để tránh bug cache kết quả lỗi.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{args}:{sorted(kwargs.items())}"
            now = time.monotonic()

            # Cache hit: trả về ngay nếu còn trong thời hạn và không rỗng
            if cache_key in _cache:
                result, cached_at = _cache[cache_key]
                is_empty = False
                if isinstance(result, dict) and "data" in result and not result["data"]:
                    is_empty = True
                elif isinstance(result, list) and not result:
                    is_empty = True

                if not is_empty and (now - cached_at < seconds):
                    return result

            # Cache miss: gọi hàm thật
            result = func(*args, **kwargs)

            # Chỉ lưu kết quả hợp lệ vào cache (không cache rỗng)
            is_empty = False
            if isinstance(result, dict) and "data" in result and not result["data"]:
                is_empty = True
            elif isinstance(result, list) and not result:
                is_empty = True

            if not is_empty:
                _cache[cache_key] = (result, now)
            return result
        return wrapper
    return decorator


def invalidate_cache():
    """Xóa toàn bộ cache (gọi sau khi pipeline chạy xong hoặc khi cập nhật dữ liệu)."""
    _cache.clear()
    logger.info("Cache đã được xóa thành công.")


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


def clean_salary(val: Optional[str]) -> Optional[str]:
    if not val:
        return None
    val = str(val).strip()
    if val in ("NaN", "nan", "None", "none", "", "null"):
        return None
    # Xóa các ký tự thừa ở đầu và cuối chuỗi (dấu phẩy, hai chấm, gạch ngang, khoảng trắng...)
    val = re.sub(r"^[\s,;:–—\-\./]+", "", val).strip()
    val = re.sub(r"[\s,;:–—\-\./]+$", "", val).strip()
    return val if val else None



# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["System"])
def health_check():
    """Kiểm tra trạng thái API và kết nối database."""
    try:
        _query("SELECT 1")
        if hasattr(engine.pool, "size"):
            pool_status = {
                "pool_size": engine.pool.size(),
                "checked_in": engine.pool.checkedin(),
                "checked_out": engine.pool.checkedout(),
                "overflow": engine.pool.overflow(),
            }
        else:
            pool_status = {"type": "NullPool (serverless)"}
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
                loc_sub.location_name,
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
            j.last_seen_at,
            COUNT(*) OVER() AS full_count
        FROM silver.jobs j
        JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = true
        JOIN silver.companies c ON j.company_id = c.company_id
        JOIN silver.sources src ON j.source_id = src.source_id
        LEFT JOIN silver.job_duplicate_groups dg ON j.duplicate_group_id = dg.group_id
        LEFT JOIN (
            SELECT DISTINCT ON (jsl.snapshot_id) jsl.snapshot_id, loc.display_name AS location_name
            FROM silver.job_snapshot_locations jsl
            JOIN silver.locations loc ON jsl.location_id = loc.location_id
        ) loc_sub ON loc_sub.snapshot_id = s.snapshot_id
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
        search = search.strip()
        tokens = [t for t in search.split() if len(t) >= 1]
        if len(tokens) > 1:
            term_clauses = []
            for i, token in enumerate(tokens):
                key = f"token_{i}"
                term_clauses.append(f"(s.title_clean ILIKE :{key} OR c.display_name ILIKE :{key})")
                params[key] = f"%{token}%"
            base_sql += " AND (" + " AND ".join(term_clauses) + ")"
        else:
            base_sql += " AND (s.title_clean ILIKE :search OR c.display_name ILIKE :search)"
            params["search"] = f"%{search}%"

    if location:
        if location in ("Hà Nội", "ha_noi"):
            base_sql += """ AND (
                s.title_clean ILIKE '%Hà Nội%' OR s.title_clean ILIKE '%HN%'
                OR loc_sub.location_name ILIKE '%Hà Nội%'
                OR (
                    loc_sub.location_name IS NULL
                    AND s.title_clean NOT ILIKE '%Hồ Chí Minh%' AND s.title_clean NOT ILIKE '%HCM%' AND s.title_clean NOT ILIKE '%Đà Nẵng%'
                )
            )"""
        elif location in ("Hồ Chí Minh", "TP. Hồ Chí Minh", "ho_chi_minh", "HCM"):
            base_sql += """ AND (
                s.title_clean ILIKE '%Hồ Chí Minh%' OR s.title_clean ILIKE '%HCM%' OR s.title_clean ILIKE '%HCMC%' OR s.title_clean ILIKE '%Sài Gòn%'
                OR loc_sub.location_name ILIKE '%Hồ Chí Minh%' OR loc_sub.location_name ILIKE '%HCM%'
            )"""
        elif location in ("Đà Nẵng", "da_nang"):
            base_sql += """ AND (
                s.title_clean ILIKE '%Đà Nẵng%' OR s.title_clean ILIKE '%ĐN%'
                OR loc_sub.location_name ILIKE '%Đà Nẵng%'
            )"""
        elif location in ("Remote", "remote"):
            base_sql += """ AND (
                s.title_clean ILIKE '%Remote%' OR s.title_clean ILIKE '%Từ xa%' OR s.title_clean ILIKE '%Hybrid%' OR s.work_mode::text IN ('REMOTE', 'HYBRID')
            )"""
        else:
            params["location"] = f"%{location}%"
            base_sql += " AND (s.title_clean ILIKE :location OR loc_sub.location_name ILIKE :location)"

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
            s.is_fresher = TRUE 
            OR s.is_intern = TRUE 
            OR s.is_no_experience = TRUE 
            OR s.experience_min_years = 0 
            OR s.experience_raw ILIKE '%không yêu cầu%'
            OR s.experience_raw ILIKE '%chưa có kinh nghiệm%'
            OR s.experience_raw ILIKE '%không cần kinh nghiệm%'
            OR s.experience_raw ILIKE '%fresher%'
            OR s.experience_raw ILIKE '%thực tập%'
            OR s.experience_raw ILIKE '%intern%'
            OR s.title_clean ILIKE '%fresher%'
            OR s.title_clean ILIKE '%thực tập%'
            OR s.title_clean ILIKE '%intern%'
        )
        AND s.title_clean NOT ILIKE '%senior%'
        AND s.title_clean NOT ILIKE '%lead%'
        AND s.title_clean NOT ILIKE '%manager%'
        AND s.title_clean NOT ILIKE '%trưởng phòng%'
        AND s.title_clean NOT ILIKE '%giám đốc%'
        """
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
        base_sql += " ORDER BY j.last_seen_at DESC NULLS LAST, j.job_id DESC LIMIT :limit OFFSET :offset"
    elif sort in ("oldest", "deadline_asc"):
        base_sql += """ ORDER BY 
            CASE WHEN s.deadline_date IS NULL OR s.deadline_date < CURRENT_DATE THEN 1 ELSE 0 END ASC,
            s.deadline_date ASC NULLS LAST, 
            j.job_id DESC 
            LIMIT :limit OFFSET :offset"""
    elif sort == "deadline_desc":
        base_sql += " ORDER BY s.deadline_date DESC NULLS LAST, j.job_id DESC LIMIT :limit OFFSET :offset"
    elif sort == "salary_desc":
        base_sql += " ORDER BY COALESCE(s.salary_max, s.salary_min) DESC NULLS LAST, j.job_id DESC LIMIT :limit OFFSET :offset"
    elif sort == "salary_asc":
        base_sql += " ORDER BY COALESCE(s.salary_min, s.salary_max) ASC NULLS LAST, j.job_id DESC LIMIT :limit OFFSET :offset"
    else:
        base_sql += " ORDER BY j.last_seen_at DESC NULLS LAST, j.job_id DESC LIMIT :limit OFFSET :offset"

    try:
        jobs = _query(base_sql, params)
        total = 0
        if jobs:
            total = int(jobs[0].get("full_count", len(jobs)))
            for j in jobs:
                j.pop("full_count", None)
                for key in ("title_clean", "company_name", "salary_raw", "deadline_raw", "location_clean"):
                    val = j.get(key)
                    if val in ("NaN", "nan", "None", "none", ""):
                        j[key] = None
                j["deadline_raw"] = clean_deadline(j.get("deadline_raw"))
                j["salary_raw"] = clean_salary(j.get("salary_raw"))

                if j.get("last_seen_at"):
                    j["scraped_at"] = j["last_seen_at"].isoformat() if hasattr(j["last_seen_at"], "isoformat") else str(j["last_seen_at"])
                elif j.get("created_at"):
                    j["scraped_at"] = j["created_at"].isoformat() if hasattr(j["created_at"], "isoformat") else str(j["created_at"])

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
        elif page > 1:
            try:
                count_sql = base_sql.split("ORDER BY")[0]
                count_sql = f"SELECT COUNT(*) AS total FROM ({count_sql}) AS sub"
                count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
                total_row = _query(count_sql, count_params)
                total = total_row[0]["total"] if total_row else 0
            except Exception:
                total = 0

        total_pages = max(1, (total + limit - 1) // limit)

        return {
            "data": jobs,
            "total": total,
            "page": page,
            "limit": limit,
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
        job["salary_raw"] = clean_salary(job.get("salary_raw"))
        
        raw_desc = job.get("description") or ""
        lines = [ln for ln in raw_desc.splitlines() if ln.strip() not in ("None", "nan", "NaN", "")]
        job["description"] = "\n".join(lines) if lines else "Vui lòng truy cập đường link gốc để xem mô tả chi tiết."
            
        return job
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats/skills", tags=["Statistics"])
@ttl_cache(seconds=300)
def get_skill_stats(top_n: int = Query(default=12, le=50)):
    """
    Thống kê top N kỹ năng phổ biến nhất - tính toán 100% động từ dữ liệu thực tế.
    """
    try:
        rows = []
        # Tầng 1: Đọc từ dwh.mv_salary_by_skill nếu có
        try:
            sql = """
                SELECT skill_name, job_count, demand_rank AS rank
                FROM dwh.mv_salary_by_skill
                WHERE job_count > 0
                ORDER BY demand_rank ASC
                LIMIT :top_n
            """
            rows = _query(sql, {"top_n": top_n})
        except Exception:
            rows = []

        # Tầng 2: Trích xuất trực tiếp từ các tin tuyển dụng đang hoạt động trong silver
        if not rows:
            try:
                kw_sql = """
                    SELECT 
                        skill_name,
                        COUNT(DISTINCT j.job_id) AS job_count,
                        RANK() OVER (ORDER BY COUNT(DISTINCT j.job_id) DESC) AS rank
                    FROM (
                        SELECT 'Java' AS skill_name, j.job_id FROM silver.jobs j JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = true WHERE j.is_active = true AND (s.title_clean ILIKE '%Java%' AND s.title_clean NOT ILIKE '%JavaScript%')
                        UNION ALL
                        SELECT 'Python' AS skill_name, j.job_id FROM silver.jobs j JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = true WHERE j.is_active = true AND s.title_clean ILIKE '%Python%'
                        UNION ALL
                        SELECT 'React / Frontend' AS skill_name, j.job_id FROM silver.jobs j JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = true WHERE j.is_active = true AND (s.title_clean ILIKE '%React%' OR s.title_clean ILIKE '%Frontend%')
                        UNION ALL
                        SELECT '.NET / C#' AS skill_name, j.job_id FROM silver.jobs j JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = true WHERE j.is_active = true AND (s.title_clean ILIKE '%.Net%' OR s.title_clean ILIKE '%C#%')
                        UNION ALL
                        SELECT 'Data Engineer' AS skill_name, j.job_id FROM silver.jobs j JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = true WHERE j.is_active = true AND (s.title_clean ILIKE '%Data%' AND s.title_clean ILIKE '%Engineer%')
                        UNION ALL
                        SELECT 'Data Analyst' AS skill_name, j.job_id FROM silver.jobs j JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = true WHERE j.is_active = true AND (s.title_clean ILIKE '%Data%' AND s.title_clean ILIKE '%Analyst%')
                        UNION ALL
                        SELECT 'DevOps / Cloud' AS skill_name, j.job_id FROM silver.jobs j JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = true WHERE j.is_active = true AND (s.title_clean ILIKE '%DevOps%' OR s.title_clean ILIKE '%Cloud%' OR s.title_clean ILIKE '%AWS%')
                        UNION ALL
                        SELECT 'NodeJS / JavaScript' AS skill_name, j.job_id FROM silver.jobs j JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = true WHERE j.is_active = true AND (s.title_clean ILIKE '%Node%' OR s.title_clean ILIKE '%JavaScript%')
                        UNION ALL
                        SELECT 'PHP' AS skill_name, j.job_id FROM silver.jobs j JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = true WHERE j.is_active = true AND s.title_clean ILIKE '%PHP%'
                        UNION ALL
                        SELECT 'QA / Tester' AS skill_name, j.job_id FROM silver.jobs j JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = true WHERE j.is_active = true AND (s.title_clean ILIKE '%Tester%' OR s.title_clean ILIKE '%QA%' OR s.title_clean ILIKE '%QC%')
                        UNION ALL
                        SELECT 'Golang' AS skill_name, j.job_id FROM silver.jobs j JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = true WHERE j.is_active = true AND (s.title_clean ILIKE '%Golang%' OR s.title_clean ILIKE '%Go %')
                        UNION ALL
                        SELECT 'AI / Machine Learning' AS skill_name, j.job_id FROM silver.jobs j JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = true WHERE j.is_active = true AND (s.title_clean ILIKE '%AI%' OR s.title_clean ILIKE '%Machine Learning%')
                    ) t
                    GROUP BY skill_name
                    ORDER BY job_count DESC
                    LIMIT :top_n
                """
                rows = _query(kw_sql, {"top_n": top_n})
            except Exception as e:
                logger.error(f"Error extracting live skills: {e}")
                rows = []

        return {"data": rows}
    except Exception as e:
        logger.error(f"Error in get_skill_stats: {e}")
        return {"data": []}


@app.get("/stats/companies", tags=["Statistics"])
@ttl_cache(seconds=300)
def get_company_stats(top_n: int = Query(default=10, le=50)):
    """
    Thống kê top N công ty đăng tuyển nhiều nhất - tính toán 100% từ bảng doanh nghiệp và tin tuyển dụng thực tế.
    """
    try:
        sql = """
            SELECT c.display_name AS company_name,
                   COUNT(CASE WHEN j.is_active = true THEN 1 END) AS active_job_count,
                   COUNT(*) AS total_job_count
            FROM silver.jobs j
            JOIN silver.companies c ON j.company_id = c.company_id
            WHERE c.display_name NOT IN ('__ANONYMOUS__', 'Công ty ẩn danh', 'NaN', 'nan', '')
            GROUP BY c.display_name
            HAVING COUNT(CASE WHEN j.is_active = true THEN 1 END) > 0
            ORDER BY active_job_count DESC, total_job_count DESC
            LIMIT :top_n
        """
        rows = _query(sql, {"top_n": top_n})
        return {"data": rows}
    except Exception as e:
        logger.error(f"Error in get_company_stats: {e}")
        return {"data": []}


@app.get("/stats/locations", tags=["Statistics"])
@ttl_cache(seconds=300)
def get_location_stats(top_n: int = Query(default=6, le=20)):
    """
    Thống kê phân bổ việc làm theo địa điểm - tính toán 100% từ dữ liệu thực tế.
    """
    try:
        sql = """
            SELECT
                CASE 
                    WHEN s.title_clean ILIKE '%remote%' OR s.work_mode::text = 'REMOTE' THEN 'Remote / Từ xa'
                    WHEN s.title_clean ILIKE '%Đà Nẵng%' OR s.title_clean ILIKE '%ĐN%' OR loc_sub.location_name ILIKE '%Đà Nẵng%' THEN 'Đà Nẵng'
                    WHEN s.title_clean ILIKE '%Hồ Chí Minh%' OR s.title_clean ILIKE '%HCM%' OR s.title_clean ILIKE '%HCMC%' OR s.title_clean ILIKE '%Sài Gòn%' 
                         OR loc_sub.location_name ILIKE '%Hồ Chí Minh%' OR loc_sub.location_name ILIKE '%HCM%' THEN 'Hồ Chí Minh'
                    WHEN s.title_clean ILIKE '%Hải Phòng%' OR loc_sub.location_name ILIKE '%Hải Phòng%' THEN 'Hải Phòng'
                    WHEN s.title_clean ILIKE '%Bình Dương%' OR loc_sub.location_name ILIKE '%Bình Dương%' THEN 'Bình Dương'
                    WHEN s.title_clean ILIKE '%Cần Thơ%' OR loc_sub.location_name ILIKE '%Cần Thơ%' THEN 'Cần Thơ'
                    ELSE 'Hà Nội'
                END AS location_name,
                COUNT(DISTINCT j.job_id) AS job_count
            FROM silver.jobs j
            JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = true
            LEFT JOIN (
                SELECT DISTINCT ON (jsl.snapshot_id) jsl.snapshot_id, loc.display_name AS location_name
                FROM silver.job_snapshot_locations jsl
                JOIN silver.locations loc ON jsl.location_id = loc.location_id
            ) loc_sub ON loc_sub.snapshot_id = s.snapshot_id
            WHERE j.is_active = true
            GROUP BY 1
            ORDER BY job_count DESC
            LIMIT :top_n
        """
        rows = _query(sql, {"top_n": top_n})
        return {"data": rows}
    except Exception as e:
        logger.error(f"Error in get_location_stats: {e}")
        return {"data": []}



@app.get("/stats/kpi", tags=["Statistics"])
@ttl_cache(seconds=600)  # Cache 10 phút — KPI thị trường thay đổi chậm, giảm tải tối đa cho DB
def get_kpi_summary():
    """
    Thống kê KPI thị trường - tính toán 100% động từ dữ liệu thực tế, không dùng hằng số mock.
    """
    try:
        # Tái sử dụng 1 kết nối duy nhất (single connection) thay vì mở/đóng liên tục
        with engine.connect() as conn:
            kpi_data = {}
            try:
                res = conn.execute(text("SELECT * FROM dwh.mv_kpi_realtime LIMIT 1"))
                rows = [dict(zip(res.keys(), row)) for row in res.fetchall()]
                kpi_data = rows[0] if rows else {}
            except Exception:
                kpi_data = {}

            total_jobs = kpi_data.get("total_active_jobs") or 0
            total_companies = kpi_data.get("total_hiring_companies") or 0
            remote_jobs = kpi_data.get("total_remote_hybrid_jobs") or 0
            avg_sal = kpi_data.get("market_avg_salary_vnd") or 0
            med_sal = kpi_data.get("market_median_salary_vnd") or 0
            disclosure_rate = kpi_data.get("salary_disclosure_rate_pct") or 0

            # Tính trực tiếp từ silver layer nếu mv_kpi_realtime chưa được tính hoặc = 0
            if not total_jobs:
                try:
                    res = conn.execute(text("""
                        SELECT
                            COUNT(DISTINCT j.job_id) AS total_jobs,
                            COUNT(DISTINCT j.company_id) AS total_companies,
                            COUNT(DISTINCT CASE WHEN s.work_mode::text = 'REMOTE' OR s.title_clean ILIKE '%remote%' THEN j.job_id END) AS remote_jobs,
                            ROUND(AVG(NULLIF(s.salary_avg, 0))) AS avg_sal,
                            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY s.salary_avg)) AS med_sal,
                            ROUND(
                                COUNT(DISTINCT CASE WHEN s.salary_avg > 0 OR s.salary_min > 0 OR s.salary_max > 0 THEN j.job_id END)::numeric
                                * 100.0 / NULLIF(COUNT(DISTINCT j.job_id), 0), 1
                            ) AS disclosure_rate
                        FROM silver.jobs j
                        JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = true
                        JOIN silver.companies c ON j.company_id = c.company_id
                        LEFT JOIN silver.job_duplicate_groups dg ON j.duplicate_group_id = dg.group_id
                        WHERE j.is_active = true
                          AND (j.duplicate_group_id IS NULL OR j.job_id = dg.canonical_job_id)
                          AND COALESCE(s.title_clean, '') NOT IN ('NaN', 'nan', '')
                          AND COALESCE(c.display_name, '') NOT IN ('NaN', 'nan', '')
                    """))
                    live_stats = [dict(zip(res.keys(), row)) for row in res.fetchall()]
                    if live_stats and live_stats[0].get("total_jobs") is not None:
                        row = live_stats[0]
                        total_jobs = row.get("total_jobs") or 0
                        total_companies = row.get("total_companies") or 0
                        remote_jobs = row.get("remote_jobs") or 0
                        avg_sal = row.get("avg_sal") or 0
                        med_sal = row.get("med_sal") or 0
                        disclosure_rate = row.get("disclosure_rate") or 0
                except Exception as e:
                    logger.error(f"Error computing live KPI summary from silver: {e}")

            # Top skills: Tính trực tiếp số lượng việc làm theo tiêu đề khớp 1:1 với bộ lọc tìm kiếm
            skills = []
            try:
                skill_counts_query = text("""
                    SELECT
                        COUNT(CASE WHEN s.title_clean ILIKE '%Java%' AND s.title_clean NOT ILIKE '%JavaScript%' THEN 1 END) AS count_java,
                        COUNT(CASE WHEN s.title_clean ILIKE '%Python%' THEN 1 END) AS count_python,
                        COUNT(CASE WHEN s.title_clean ILIKE '%React%' OR s.title_clean ILIKE '%Frontend%' THEN 1 END) AS count_react,
                        COUNT(CASE WHEN s.title_clean ILIKE '%.Net%' OR s.title_clean ILIKE '%C#%' THEN 1 END) AS count_dotnet,
                        COUNT(CASE WHEN s.title_clean ILIKE '%Data%' AND s.title_clean ILIKE '%Engineer%' THEN 1 END) AS count_de,
                        COUNT(CASE WHEN s.title_clean ILIKE '%Data%' AND s.title_clean ILIKE '%Analyst%' THEN 1 END) AS count_da,
                        COUNT(CASE WHEN s.title_clean ILIKE '%DevOps%' OR s.title_clean ILIKE '%Cloud%' OR s.title_clean ILIKE '%AWS%' THEN 1 END) AS count_devops,
                        COUNT(CASE WHEN s.title_clean ILIKE '%Node%' OR s.title_clean ILIKE '%JavaScript%' THEN 1 END) AS count_node,
                        COUNT(CASE WHEN s.title_clean ILIKE '%PHP%' THEN 1 END) AS count_php,
                        COUNT(CASE WHEN s.title_clean ILIKE '%Tester%' OR s.title_clean ILIKE '%QA%' OR s.title_clean ILIKE '%QC%' THEN 1 END) AS count_qa,
                        COUNT(CASE WHEN s.title_clean ILIKE '%Golang%' OR s.title_clean ILIKE '%Go %' THEN 1 END) AS count_go,
                        COUNT(CASE WHEN s.title_clean ILIKE '%AI%' OR s.title_clean ILIKE '%Machine Learning%' THEN 1 END) AS count_ai
                    FROM silver.jobs j
                    JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = true
                    JOIN silver.companies c ON j.company_id = c.company_id
                    LEFT JOIN silver.job_duplicate_groups dg ON j.duplicate_group_id = dg.group_id
                    WHERE j.is_active = true
                      AND (j.duplicate_group_id IS NULL OR j.job_id = dg.canonical_job_id)
                      AND COALESCE(s.title_clean, '') NOT IN ('NaN', 'nan', '')
                      AND COALESCE(c.display_name, '') NOT IN ('NaN', 'nan', '')
                """)
                res = conn.execute(skill_counts_query)
                row = res.fetchone()
                if row:
                    counts = dict(zip(res.keys(), row))
                    raw_skills = [
                        {"name": "Java", "search_term": "Java", "count": counts.get("count_java", 0)},
                        {"name": "Python", "search_term": "Python", "count": counts.get("count_python", 0)},
                        {"name": "React / Frontend", "search_term": "React", "count": counts.get("count_react", 0)},
                        {"name": ".NET / C#", "search_term": ".NET", "count": counts.get("count_dotnet", 0)},
                        {"name": "Data Engineer", "search_term": "Data Engineer", "count": counts.get("count_de", 0)},
                        {"name": "Data Analyst", "search_term": "Data Analyst", "count": counts.get("count_da", 0)},
                        {"name": "DevOps", "search_term": "DevOps", "count": counts.get("count_devops", 0)},
                        {"name": "NodeJS", "search_term": "NodeJS", "count": counts.get("count_node", 0)},
                        {"name": "PHP", "search_term": "PHP", "count": counts.get("count_php", 0)},
                        {"name": "QA / Tester", "search_term": "Tester", "count": counts.get("count_qa", 0)},
                        {"name": "Golang", "search_term": "Golang", "count": counts.get("count_go", 0)},
                        {"name": "AI / ML", "search_term": "AI", "count": counts.get("count_ai", 0)},
                    ]
                    raw_skills = [s for s in raw_skills if s["count"] > 0]
                    raw_skills.sort(key=lambda x: x["count"], reverse=True)
                    skills = raw_skills[:10]
            except Exception as e:
                logger.error(f"Error computing live skill counts: {e}")
                skills = []

            # New jobs 7 ngày gần nhất
            new_jobs_7d = 0
            try:
                res = conn.execute(text("""
                    SELECT COUNT(*) AS cnt 
                    FROM silver.jobs j
                    WHERE j.is_active = true 
                      AND j.last_seen_at >= CURRENT_DATE - INTERVAL '7 days'
                """))
                row = res.fetchone()
                if row:
                    new_jobs_7d = row[0] or 0
            except Exception:
                new_jobs_7d = 0

            # Fresher jobs: Khớp chính xác với bộ lọc 'no_exp' để số lượng trên thẻ trùng khớp khi bấm
            fresher_jobs = 0
            try:
                res = conn.execute(text("""
                    SELECT COUNT(DISTINCT j.job_id) AS cnt 
                    FROM silver.jobs j
                    JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = true
                    JOIN silver.companies c ON j.company_id = c.company_id
                    LEFT JOIN silver.job_duplicate_groups dg ON j.duplicate_group_id = dg.group_id
                    WHERE j.is_active = true 
                      AND (j.duplicate_group_id IS NULL OR j.job_id = dg.canonical_job_id)
                      AND COALESCE(s.title_clean, '') NOT IN ('NaN', 'nan', '')
                      AND COALESCE(c.display_name, '') NOT IN ('NaN', 'nan', '')
                      AND (
                          s.is_fresher = true 
                          OR s.is_intern = true 
                          OR s.is_no_experience = true 
                          OR s.experience_min_years = 0 
                          OR s.experience_raw ILIKE '%không yêu cầu%'
                          OR s.experience_raw ILIKE '%chưa có kinh nghiệm%'
                          OR s.experience_raw ILIKE '%không cần kinh nghiệm%'
                          OR s.experience_raw ILIKE '%fresher%'
                          OR s.experience_raw ILIKE '%thực tập%'
                          OR s.experience_raw ILIKE '%intern%'
                          OR s.title_clean ILIKE '%fresher%'
                          OR s.title_clean ILIKE '%thực tập%'
                          OR s.title_clean ILIKE '%intern%'
                      )
                      AND s.title_clean NOT ILIKE '%senior%'
                      AND s.title_clean NOT ILIKE '%lead%'
                      AND s.title_clean NOT ILIKE '%manager%'
                      AND s.title_clean NOT ILIKE '%trưởng phòng%'
                      AND s.title_clean NOT ILIKE '%giám đốc%'
                """))
                row = res.fetchone()
                if row and row[0]:
                    fresher_jobs = row[0]
            except Exception:
                fresher_jobs = 0

            # Tỷ lệ tin tuyển dụng có ghi mức lương rõ ràng (dải lương số cụ thể)
            if not disclosure_rate:
                try:
                    res = conn.execute(text("""
                        SELECT 
                            ROUND(
                                COUNT(CASE WHEN (s.salary_min IS NOT NULL AND s.salary_min > 0)
                                            OR (s.salary_max IS NOT NULL AND s.salary_max > 0)
                                            OR (s.salary_raw ~ '[0-9]')
                                      THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0), 1
                            ) AS real_disclosure_rate
                        FROM silver.jobs j
                        JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = true
                        WHERE j.is_active = true
                    """))
                    row = res.fetchone()
                    if row and row[0] is not None:
                        disclosure_rate = float(row[0])
                except Exception:
                    disclosure_rate = 0.0

            return {
                "total_jobs":              int(total_jobs or 0),
                "new_jobs_7d":             int(new_jobs_7d or 0),
                "average_salary_million":  f"{avg_sal / 1_000_000:.1f} Tr" if avg_sal else None,
                "median_salary":           f"{med_sal / 1_000_000:.1f}" if med_sal else None,
                "disclosure_rate":         round(float(disclosure_rate or 0), 1),
                "total_companies":         int(total_companies or 0),
                "fresher_jobs":            int(fresher_jobs or 0),
                "remote_jobs":             int(remote_jobs or 0),
                "top_skills":              skills,
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats/salary-by-skill", tags=["Statistics"])
@ttl_cache(seconds=3600)
def get_salary_by_skill(top_n: int = Query(default=15, le=30)):
    """
    Lương trung bình và lương cao nhất theo kỹ năng.
    Thử mv_salary_by_skill trước, fallback sang silver layer và keyword matching nếu trống.
    Tính toán 100% động từ DB.
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
            ROUND(AVG(NULLIF(js.salary_min, 0)))        AS avg_salary_min_vnd,
            ROUND(MAX(NULLIF(js.salary_max, 0)))        AS max_salary_max_vnd,
            COUNT(*)                                   AS job_count,
            RANK() OVER (ORDER BY COUNT(*) DESC)       AS demand_rank
        FROM silver.job_snapshot_skills jss
        JOIN silver.skills s  ON jss.skill_id = s.skill_id
        JOIN silver.job_snapshots js ON jss.snapshot_id = js.snapshot_id
        WHERE js.is_current = true AND (js.salary_min IS NOT NULL OR js.salary_max IS NOT NULL)
        GROUP BY s.display_name
        HAVING COUNT(*) >= 2
        ORDER BY avg_salary_min_vnd DESC NULLS LAST
        LIMIT :top_n
    """
    kw_sql = """
        SELECT
            skill_name,
            ROUND(AVG(NULLIF(salary_min, 0))) AS avg_salary_min_vnd,
            ROUND(MAX(NULLIF(salary_max, 0))) AS max_salary_max_vnd,
            COUNT(*) AS job_count,
            RANK() OVER (ORDER BY COUNT(*) DESC) AS demand_rank
        FROM (
            SELECT 
                js.salary_min,
                js.salary_max,
                CASE 
                    WHEN js.title_clean ILIKE '%python%' THEN 'Python'
                    WHEN js.title_clean ILIKE '%java%' THEN 'Java'
                    WHEN js.title_clean ILIKE '%react%' THEN 'React'
                    WHEN js.title_clean ILIKE '%data engineer%' OR js.title_clean ILIKE '%kỹ sư dữ liệu%' THEN 'Data Engineer'
                    WHEN js.title_clean ILIKE '%data analyst%' OR js.title_clean ILIKE '%phân tích dữ liệu%' THEN 'Data Analyst'
                    WHEN js.title_clean ILIKE '%backend%' THEN 'Backend'
                    WHEN js.title_clean ILIKE '%frontend%' THEN 'Frontend'
                    WHEN js.title_clean ILIKE '%devops%' THEN 'DevOps'
                    WHEN js.title_clean ILIKE '%ai%' OR js.title_clean ILIKE '%machine learning%' THEN 'AI / ML'
                    WHEN js.title_clean ILIKE '%cloud%' OR js.title_clean ILIKE '%aws%' THEN 'Cloud / AWS'
                    WHEN js.title_clean ILIKE '%fullstack%' OR js.title_clean ILIKE '%full stack%' THEN 'Fullstack'
                    WHEN js.title_clean ILIKE '%golang%' OR js.title_clean ILIKE '%go%' THEN 'Golang'
                    WHEN js.title_clean ILIKE '%qa%' OR js.title_clean ILIKE '%tester%' OR js.title_clean ILIKE '%qc%' THEN 'QA / Tester'
                    ELSE NULL
                END AS skill_name
            FROM silver.job_snapshots js
            WHERE js.is_current = true AND (js.salary_min IS NOT NULL OR js.salary_max IS NOT NULL)
        ) t
        WHERE skill_name IS NOT NULL
        GROUP BY skill_name
        ORDER BY avg_salary_min_vnd DESC NULLS LAST
        LIMIT :top_n
    """
    try:
        rows = []
        try:
            rows = _query(mv_sql, {"top_n": top_n})
        except Exception:
            rows = []
        if not rows:
            try:
                rows = _query(silver_sql, {"top_n": top_n})
            except Exception:
                rows = []
        if not rows:
            try:
                rows = _query(kw_sql, {"top_n": top_n})
            except Exception:
                rows = []

        return {"data": rows}
    except Exception as e:
        logger.error(f"Error in get_salary_by_skill: {e}")
        return {"data": []}


@app.get("/stats/salary-by-experience", tags=["Statistics"])
@ttl_cache(seconds=3600)
def get_salary_by_experience():
    """
    Thống kê mức lương theo cấp bậc và khoảng năm kinh nghiệm từ BI Mart (agg_salary_by_experience).
    Tính toán 100% động từ dữ liệu thực tế, không dùng hằng số mock.
    """
    dwh_sql = """
        SELECT
            experience_band,
            SUM(total_jobs)                         AS total_jobs,
            ROUND(AVG(NULLIF(avg_salary_vnd, 0)))   AS avg_salary_min_vnd,
            ROUND(AVG(NULLIF(max_salary_vnd, 0)))   AS avg_salary_max_vnd,
            ROUND(MAX(NULLIF(max_salary_vnd, 0)))   AS max_salary_vnd
        FROM dwh.agg_salary_by_experience
        GROUP BY experience_band, exp_sort_key
        ORDER BY exp_sort_key NULLS LAST
    """
    silver_sql = """
        WITH cleaned_jobs AS (
            SELECT
                j.job_id,
                js.title_clean,
                js.salary_min,
                js.salary_max,
                -- Lọc outlier: Số năm kinh nghiệm > 10 năm trong tin tuyển dụng IT thường là do
                -- bóc tách nhầm tuổi đời thành lập của công ty (VD: MCBooks 15 năm, Viglacera 30 năm...)
                -- Hoặc các vị trí helpdesk, support, thực tập bị bóc nhầm >= 3 năm kinh nghiệm
                CASE
                    WHEN js.experience_min_years IS NULL OR js.experience_min_years < 0 THEN NULL
                    WHEN js.experience_min_years > 10 THEN NULL
                    WHEN LOWER(js.title_clean) ~* '(helpdesk|support|cskh|thực tập|intern)' AND js.experience_min_years >= 3 THEN NULL
                    ELSE js.experience_min_years
                END AS exp_years
            FROM silver.jobs j
            JOIN silver.job_snapshots js ON j.job_id = js.job_id AND js.is_current = true
            WHERE j.is_active = true
        )
        SELECT
            CASE
                WHEN exp_years IS NULL THEN 'Chưa rõ kinh nghiệm'
                WHEN exp_years = 0 THEN 'Fresher (0 năm)'
                WHEN exp_years <= 1 THEN 'Junior (≤1 năm)'
                WHEN exp_years <= 3 THEN 'Mid (1-3 năm)'
                WHEN exp_years <= 5 THEN 'Senior (3-5 năm)'
                ELSE 'Lead / Expert (>5 năm)'
            END AS experience_band,
            CASE
                WHEN exp_years IS NULL THEN 99
                WHEN exp_years = 0 THEN 0
                WHEN exp_years <= 1 THEN 1
                WHEN exp_years <= 3 THEN 2
                WHEN exp_years <= 5 THEN 3
                ELSE 4
            END AS sort_key,
            COUNT(DISTINCT job_id) AS total_jobs,
            ROUND(AVG(NULLIF(salary_min, 0))) AS avg_salary_min_vnd,
            ROUND(AVG(NULLIF(salary_max, 0))) AS avg_salary_max_vnd,
            ROUND(MAX(NULLIF(salary_max, 0))) AS max_salary_vnd
        FROM cleaned_jobs
        GROUP BY 1, 2
        ORDER BY sort_key ASC
    """
    try:
        rows = []
        try:
            rows = _query(dwh_sql)
        except Exception:
            rows = []
        if not rows:
            try:
                rows = _query(silver_sql)
            except Exception:
                rows = []
        return {"data": rows}
    except Exception as e:
        logger.error(f"Error in get_salary_by_experience: {e}")
        return {"data": []}



@app.get("/cache/invalidate", tags=["System"])
@app.post("/cache/invalidate", tags=["System"])
def clear_cache():
    """
    Xóa toàn bộ in-memory cache.
    Gọi endpoint này sau khi Airflow pipeline chạy xong
    hoặc để refresh dữ liệu biểu đồ.
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
