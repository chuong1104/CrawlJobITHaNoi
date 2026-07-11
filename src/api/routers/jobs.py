from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from src.api.database import db

router = APIRouter(prefix="/api/v1", tags=["Jobs"])

@router.get("/stats/summary")
async def get_summary_stats():
    """Lấy dữ liệu thống kê nhanh (KPIs) hiển thị trên đỉnh Dashboard"""
    query_kpis = "SELECT total_active_jobs, market_avg_salary_vnd, total_hiring_companies, market_median_salary_vnd, salary_disclosure_rate_pct, total_fresher_jobs, total_remote_hybrid_jobs FROM dwh.mv_kpi_realtime LIMIT 1;"
    query_new_jobs = "SELECT COUNT(*) FROM silver.jobs WHERE first_seen_at >= CURRENT_DATE - INTERVAL '7 days';"
    query_skills = """
        SELECT word as name, count(*) as count 
        FROM (
          SELECT regexp_split_to_table(lower(job_title), '\s+') as word 
          FROM mart_api.latest_jobs_flat
        ) t 
        WHERE word IN ('python', 'sql', 'react', 'java', 'docker', 'golang', 'devops', 'kubernetes', 'aws', 'javascript', 'php', 'c#', 'c++', 'typescript', 'django', 'node', 'nodejs', 'vue')
        GROUP BY word 
        ORDER BY count DESC 
        LIMIT 5;
    """
    
    async with db.pool.acquire() as conn:
        kpi_row = await conn.fetchrow(query_kpis)
        new_jobs_count = await conn.fetchval(query_new_jobs)
        
        if kpi_row and kpi_row["total_active_jobs"] > 0:
            total_jobs = kpi_row["total_active_jobs"]
            total_companies = kpi_row["total_hiring_companies"]
            avg_salary = round(float(kpi_row["market_avg_salary_vnd"] or 0) / 1000000.0, 1) if kpi_row["market_avg_salary_vnd"] else 0.0
            median_salary = round(float(kpi_row["market_median_salary_vnd"] or 0) / 1000000.0, 1) if kpi_row["market_median_salary_vnd"] else 0.0
            disclosure_rate = round(float(kpi_row["salary_disclosure_rate_pct"] or 0), 1)
            fresher_jobs = kpi_row["total_fresher_jobs"] or 0
            remote_jobs = kpi_row["total_remote_hybrid_jobs"] or 0
        else:
            # Fallback to direct queries
            total_jobs = await conn.fetchval("SELECT COUNT(*) FROM mart_api.latest_jobs_flat;")
            total_companies = await conn.fetchval("SELECT COUNT(DISTINCT company_name) FROM mart_api.latest_jobs_flat;")
            avg_salary_val = await conn.fetchval("SELECT AVG(salary_midpoint_vnd) FROM dwh.fct_job_posting WHERE is_active = TRUE AND has_salary = TRUE;")
            avg_salary = round(float(avg_salary_val or 0) / 1000000.0, 1) if avg_salary_val else 0.0
            median_salary = 0.0
            disclosure_rate = 0.0
            fresher_jobs = 0
            remote_jobs = 0

        skills_rows = await conn.fetch(query_skills)
        top_skills = [{"name": r["name"].upper(), "count": r["count"]} for r in skills_rows]
        
    return {
        "total_jobs": total_jobs,
        "average_salary_million": avg_salary,
        "total_companies": total_companies,
        "top_skills": top_skills,
        "new_jobs_7d": new_jobs_count or 0,
        "median_salary": median_salary,
        "disclosure_rate": disclosure_rate,
        "fresher_jobs": fresher_jobs,
        "remote_jobs": remote_jobs
    }

@router.get("/jobs")
async def get_jobs(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = None,
    location: Optional[str] = None,
    experience: Optional[str] = None,
    source: Optional[str] = None,
    salary: Optional[str] = None,
    sort: str = Query("newest")
):
    """Tìm kiếm tin tuyển dụng với Full-Text Search và nhiều bộ lọc nâng cao"""
    offset = (page - 1) * limit
    
    # Base CTE query joining snapshot to get experience_raw and deadline information
    base_cte = """
        WITH jobs_mapped AS (
            SELECT 
                f.id as job_id, 
                f.job_title as title_clean, 
                f.company_name as company_display_name, 
                f.salary_display as salary_raw, 
                COALESCE(
                    NULLIF(array_to_string(f.locations, ', '), ''), 
                    CASE 
                        WHEN f.job_title ILIKE '%Hồ Chí Minh%' OR f.job_title ILIKE '%HCM%' OR f.job_title ILIKE '%HCMC%' OR f.job_title ILIKE '%Sài Gòn%' THEN 'Hồ Chí Minh'
                        WHEN f.job_title ILIKE '%Đà Nẵng%' OR f.job_title ILIKE '%ĐN%' THEN 'Đà Nẵng'
                        ELSE 'Hà Nội' 
                    END
                ) as location_clean, 
                COALESCE(js.experience_raw, 'Không yêu cầu') as experience_raw, 
                j.created_at as scraped_at, 
                f.canonical_url,
                f.job_title,
                f.source_name,
                f.salary_min_vnd,
                f.salary_max_vnd,
                js.deadline_raw,
                TO_DATE(SUBSTRING(js.deadline_raw FROM '^([0-9]{2}/[0-9]{2}/[0-9]{4})'), 'DD/MM/YYYY') as deadline_date,
                TO_DATE(SUBSTRING(js.deadline_raw FROM '^([0-9]{2}/[0-9]{2}/[0-9]{4})'), 'DD/MM/YYYY') - CURRENT_DATE as remaining_days,
                CASE 
                    WHEN TO_DATE(SUBSTRING(js.deadline_raw FROM '^([0-9]{2}/[0-9]{2}/[0-9]{4})'), 'DD/MM/YYYY') < CURRENT_DATE THEN TRUE 
                    ELSE FALSE 
                END as is_expired
            FROM mart_api.latest_jobs_flat f
            JOIN silver.jobs j ON f.id = j.job_id
            JOIN silver.job_snapshots js ON j.job_id = js.job_id AND js.is_current = TRUE
        )
    """

    conditions = []
    params = []

    if search:
        params.append(search)
        conditions.append(f"to_tsvector('simple', job_title) @@ plainto_tsquery('simple', ${len(params)})")

    if location:
        params.append(f"%{location}%")
        conditions.append(f"location_clean ILIKE ${len(params)}")

    if source:
        params.append(source)
        conditions.append(f"source_name = ${len(params)}")

    if experience:
        if experience == "no_exp":
            conditions.append("(experience_raw ILIKE '%Không yêu cầu%' OR experience_raw ILIKE '%Dưới 1 năm%' OR experience_raw ILIKE '%fresher%')")
        elif experience == "1_3_years":
            conditions.append("(experience_raw ILIKE '%1 năm%' OR experience_raw ILIKE '%2 năm%' OR experience_raw ILIKE '%3 năm%' OR experience_raw ILIKE '%1 - %' OR experience_raw ILIKE '%2 - %')")
        elif experience == "over_3_years":
            conditions.append("(experience_raw ILIKE '%4 năm%' OR experience_raw ILIKE '%5 năm%' OR experience_raw ILIKE '%Trên 3 năm%' OR experience_raw ILIKE '%Trên 5 năm%' OR experience_raw ~* '([4-9]|[1-9][0-9])\\s*năm')")

    if salary:
        if salary == "negotiable":
            conditions.append("(salary_raw ILIKE '%Thoả thuận%' OR salary_raw ILIKE '%Cạnh tranh%' OR salary_raw = 'NaN' OR salary_raw ILIKE '%love%')")
        elif salary == "under_15":
            conditions.append("(salary_raw ~* '(dưới|đến|từ)?\\s*(5|6|7|8|9|10|11|12|13|14)\\s*(triệu|tr)' OR (salary_min_vnd IS NOT NULL AND salary_min_vnd < 15000000))")
        elif salary == "15_30":
            conditions.append("(salary_raw ~* '(15|16|17|18|19|20|22|25|30)\\s*(triệu|tr)' OR (salary_min_vnd IS NOT NULL AND salary_min_vnd >= 15000000 AND salary_min_vnd <= 30000000))")
        elif salary == "over_30":
            conditions.append("(salary_raw ~* '(30|35|40|45|50|60|70|80|100)\\s*(triệu|tr)' OR (salary_min_vnd IS NOT NULL AND salary_min_vnd > 30000000))")

    where_clause = ""
    if conditions:
        where_clause = " WHERE " + " AND ".join(conditions)

    # Build count query and pagination list query
    count_query = f"{base_cte} SELECT COUNT(*) FROM jobs_mapped {where_clause};"
    
    params.append(limit)
    limit_param = f"${len(params)}"
    params.append(offset)
    offset_param = f"${len(params)}"

    order_clause = "ORDER BY scraped_at DESC, job_id DESC"
    if sort == "oldest":
        order_clause = "ORDER BY scraped_at ASC, job_id ASC"

    list_query = f"""
        {base_cte} 
        SELECT job_id, title_clean, company_display_name, salary_raw, location_clean, experience_raw, scraped_at, canonical_url, source_name, deadline_raw, deadline_date, remaining_days, is_expired
        FROM jobs_mapped 
        {where_clause}
        {order_clause}
        LIMIT {limit_param} OFFSET {offset_param};
    """

    async with db.pool.acquire() as conn:
        total = await conn.fetchval(count_query, *params[:-2])
        rows = await conn.fetch(list_query, *params)
        
    jobs = [dict(r) for r in rows]
    total_pages = (total + limit - 1) // limit
    
    return {
        "data": jobs,
        "pagination": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages
        }
    }

@router.get("/jobs/{job_id}")
async def get_job_detail(job_id: int):
    """Lấy mô tả chi tiết của công việc (đọc từ Silver Layer)"""
    query = """
        SELECT j.job_id, s.title_clean, s.description, c.display_name as company_name, j.canonical_url, s.deadline_raw,
               TO_DATE(SUBSTRING(s.deadline_raw FROM '^([0-9]{2}/[0-9]{2}/[0-9]{4})'), 'DD/MM/YYYY') < CURRENT_DATE as is_expired
        FROM silver.jobs j
        JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = TRUE
        JOIN silver.companies c ON j.company_id = c.company_id
        WHERE j.job_id = $1;
    """
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(query, job_id)
        
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
        
    return dict(row)

