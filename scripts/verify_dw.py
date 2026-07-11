import duckdb

DB = '/opt/airflow/data/jobitvn.duckdb'
conn = duckdb.connect(DB, read_only=True)

print('='*60)
print('DATA WAREHOUSE QUALITY VERIFICATION REPORT')
print('='*60)

# 1. List all tables
print('\n TABLES IN DUCKDB:')
tables = conn.execute("""
    SELECT table_schema || '.' || table_name as tbl, 
           table_type
    FROM information_schema.tables 
    ORDER BY 1
""").fetchall()
for t in tables:
    try:
        cnt = conn.execute(f'SELECT COUNT(*) FROM "{t[0].split(".")[0]}"."{t[0].split(".")[1]}"').fetchone()[0]
        print(f'  {t[0]}: {cnt:,} rows')
    except:
        print(f'  {t[0]}: (view/error)')

# 2. Skills verification
print('\n TOP 20 SKILLS (after fix):')
try:
    rows = conn.execute("""
        SELECT normalized_skill, skill_category, COUNT(*) as job_count 
        FROM main.int_job_skills_exploded 
        GROUP BY 1, 2 
        ORDER BY 3 DESC 
        LIMIT 20
    """).fetchall()
    for r in rows:
        print(f'  [{r[2]:4d}x] [{r[1]}] {r[0]}')
except Exception as e:
    print(f'  ERROR: {e}')

# 3. Experience NULL rate
print('\n EXPERIENCE PARSE RATE:')
try:
    r = conn.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(experience_min_years) as has_exp_min,
            COUNT(experience_max_years) as has_exp_max,
            ROUND(COUNT(experience_min_years)*100.0/COUNT(*),1) as pct_parsed
        FROM main.int_deduped_jobs
    """).fetchone()
    print(f'  Total: {r[0]:,} | Has exp_min: {r[1]:,} ({r[3]}%) | Has exp_max: {r[2]:,}')
except Exception as e:
    print(f'  ERROR: {e}')

# 4. Salary avg
print('\n SALARY AVG COVERAGE:')
try:
    r = conn.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(salary_avg) as has_salary_avg,
            ROUND(COUNT(salary_avg)*100.0/COUNT(*),1) as pct
        FROM main.int_deduped_jobs
    """).fetchone()
    print(f'  Total: {r[0]:,} | Has salary_avg: {r[1]:,} ({r[2]}%)')
except Exception as e:
    print(f'  ERROR: {e}')

# 5. fct_job_posting check
print('\n FCT_JOB_POSTING (Gold Layer):')
try:
    r = conn.execute("""
        SELECT 
            COUNT(*) as total_jobs,
            COUNT(DISTINCT company_id) as companies,
            COUNT(DISTINCT source_code) as sources,
            COUNT(DISTINCT job_family) as job_families,
            COUNT(CASE WHEN salary_avg IS NOT NULL THEN 1 END) as with_salary,
            COUNT(CASE WHEN is_fresher THEN 1 END) as fresher,
            COUNT(CASE WHEN is_intern THEN 1 END) as intern,
            COUNT(CASE WHEN work_mode='REMOTE' THEN 1 END) as remote
        FROM main.fct_job_posting
    """).fetchone()
    print(f'  Jobs: {r[0]:,} | Companies: {r[1]:,} | Sources: {r[2]} | Job Families: {r[3]}')
    print(f'  With Salary: {r[4]:,} | Fresher: {r[5]:,} | Intern: {r[6]:,} | Remote: {r[7]:,}')
except Exception as e:
    print(f'  ERROR: {e}')

# 6. Job family breakdown
print('\n JOB FAMILY BREAKDOWN:')
try:
    rows = conn.execute("""
        SELECT job_family, COUNT(*) as cnt
        FROM main.fct_job_posting
        GROUP BY 1 ORDER BY 2 DESC
    """).fetchall()
    for r in rows:
        bar = '█' * min(40, r[1] // 50)
        print(f'  {r[0]:20s}: {r[1]:5d} {bar}')
except Exception as e:
    print(f'  ERROR: {e}')

# 7. fct_job_skill top skills
print('\n TOP SKILLS FROM FCT_JOB_SKILL:')
try:
    rows = conn.execute("""
        SELECT normalized_skill, skill_category, COUNT(DISTINCT job_id) as cnt
        FROM main.fct_job_skill
        GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 15
    """).fetchall()
    for r in rows:
        print(f'  [{r[2]:4d} jobs] [{r[1]:12s}] {r[0]}')
except Exception as e:
    print(f'  ERROR: {e}')

# 8. Business queries
print('\n TOP 10 HIRING COMPANIES:')
try:
    rows = conn.execute("""
        SELECT company_name, total_active_jobs, industry
        FROM main.agg_company_hiring
        ORDER BY total_active_jobs DESC LIMIT 10
    """).fetchall()
    for r in rows:
        print(f'  {r[0][:40]:40s}: {r[1]:4d} jobs | {r[2] or "N/A"}')
except Exception as e:
    print(f'  ERROR: {e}')

print('\n SALARY BY EXPERIENCE:')
try:
    rows = conn.execute("""
        SELECT experience_band, job_family, total_jobs, avg_salary_million_vnd
        FROM main.agg_salary_by_experience
        WHERE job_family IN ('DATA_ENGINEER','BACKEND','FRONTEND','DATA_ANALYST')
        ORDER BY experience_band, job_family
    """).fetchall()
    for r in rows:
        sal = f'{r[3]}M VND' if r[3] else 'N/A'
        print(f'  [{r[0]}] {r[1]:20s}: {r[2]:4d} jobs | Avg: {sal}')
except Exception as e:
    print(f'  ERROR: {e}')

conn.close()
print('\n Verification DONE.')
