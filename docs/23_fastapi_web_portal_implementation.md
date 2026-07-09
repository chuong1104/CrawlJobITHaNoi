# 23. Hướng Dẫn Triển Khai Chi Tiết Giao Diện Web & FastAPI (Web Portal)

Tài liệu này chứa toàn bộ mã nguồn, cấu hình và hướng dẫn từng bước để bạn có thể tự mình xây dựng hoặc triển khai **Tầng Phục Vụ (Serving Layer)** cho dự án JobITVN. Khi kích hoạt, hệ thống sẽ cung cấp một giao diện Web Dashboard sang trọng, hỗ trợ tìm kiếm tin tuyển dụng siêu tốc (<50ms) cùng các biểu đồ trực quan hóa dữ liệu thời gian thực.

---

## 1. Kiến Trúc Hoạt Động

```text
  [Người Dùng Cuối]
          │ (HTTP / Web Browser)
          ▼
    [FastAPI Server] (Port 8000)
          │
          ├── Read Static Assets ➔ (HTML/CSS/JS Dashboard)
          │
          ├── Queries (asyncpg)
          ▼
   [PostgreSQL DB] (Port 5432)
          │
          ├── ➔ Đọc Materialized Views: `mart_api.latest_jobs_flat` (Truy vấn nhanh)
          └── ➔ Đọc Chi tiết Job: `silver.job_snapshots`
```

---

## 2. Chi Tiết Các Bước Triển Khai & Mã Nguồn

Hãy tạo các thư mục và tập tin theo đúng cấu trúc sau dưới thư mục `src/`:

```text
src/
└── api/
    ├── __init__.py
    ├── database.py          # Kết nối CSDL bất đồng bộ
    ├── main.py              # Entrypoint chính của FastAPI
    ├── routers/
    │   ├── __init__.py
    │   └── jobs.py          # Endpoints xử lý tìm kiếm và lấy thống kê
    └── static/              # Thư mục chứa giao diện Web
        ├── index.html       # Giao diện Dashboard chính
        ├── styles.css       # CSS Premium Dark Theme (Glassmorphism)
        └── app.js           # Logic gọi API và Render dữ liệu
```

### Bước 2.1: Cấu hình Kết nối Cơ sở dữ liệu (`src/api/database.py`)

Sử dụng thư viện `asyncpg` để thiết lập connection pool bất đồng bộ hiệu năng cao tới PostgreSQL:

```python
# src/api/database.py
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://airflow:airflow@postgres:5432/job_scraper_db"
)

class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        if not self.pool:
            self.pool = await asyncpg.create_pool(
                dsn=DATABASE_URL,
                min_size=5,
                max_size=20,
                max_inactive_connection_lifetime=300.0
            )

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            self.pool = None

db = Database()
```

---

### Bước 2.2: Định nghĩa các Router API (`src/api/routers/jobs.py`)

Định nghĩa các endpoint phục vụ tìm kiếm tin tuyển dụng, lấy chi tiết, và lấy thống kê tổng hợp:

```python
# src/api/routers/jobs.py
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from src.api.database import db

router = APIRouter(prefix="/api/v1", tags=["Jobs"])

@router.get("/stats/summary")
async def get_summary_stats():
    """Lấy dữ liệu thống kê nhanh (KPIs) hiển thị trên đỉnh Dashboard"""
    query_total = "SELECT COUNT(*) FROM mart_api.latest_jobs_flat WHERE is_active = TRUE;"
    query_avg_salary = """
        SELECT ROUND(AVG(salary_midpoint_vnd) / 1000000, 1) as avg_salary 
        FROM dwh.fct_job_posting 
        WHERE is_active = TRUE AND has_salary = TRUE;
    """
    query_top_skills = """
        SELECT s.display_name, COUNT(f.job_key) as job_count
        FROM dwh.fct_job_posting f
        JOIN dwh.dim_skill s ON f.posted_date_key IS NOT NULL -- Giả sử join với bảng trung gian hoặc mapping
        WHERE f.is_active = TRUE
        GROUP BY s.display_name
        ORDER BY job_count DESC
        LIMIT 5;
    """
    
    async with db.pool.acquire() as conn:
        total_jobs = await conn.fetchval(query_total)
        avg_salary = await conn.fetchval(query_avg_salary) or 0.0
        
        # Mock/Query thực tế danh sách kỹ năng
        skills_raw = await conn.fetch("""
            SELECT s.display_name, COUNT(*) as count 
            FROM silver.skills s
            JOIN silver.job_snapshot_skills jss ON s.skill_id = jss.skill_id
            GROUP BY s.display_name 
            ORDER BY count DESC LIMIT 5;
        """)
        top_skills = [{"name": r["display_name"], "count": r["count"]} for r in skills_raw]

    return {
        "total_jobs": total_jobs,
        "average_salary_million": avg_salary,
        "top_skills": top_skills
    }

@router.get("/jobs")
async def get_jobs(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = None,
    location: Optional[str] = None,
    experience: Optional[str] = None
):
    """Tìm kiếm tin tuyển dụng với Full-Text Search"""
    offset = (page - 1) * limit
    
    # Xây dựng câu SQL động
    conditions = ["is_active = TRUE"]
    params = []
    
    if search:
        # Sử dụng Full-Text Search của PostgreSQL thông qua GIN index
        params.append(search)
        conditions.append(f"ts_vector_document @@ plainto_tsquery('vietnamese', ${len(params)})")
        
    if location:
        params.append(f"%{location}%")
        conditions.append(f"location_clean ILIKE ${len(params)}")
        
    where_clause = " WHERE " + " AND ".join(conditions)
    
    # Query lấy danh sách
    query_list = f"""
        SELECT job_id, title_clean, company_display_name, salary_raw, location_clean, experience_raw, scraped_at, canonical_url
        FROM mart_api.latest_jobs_flat
        {where_clause}
        ORDER BY scraped_at DESC
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2};
    """
    
    # Query đếm tổng số bản ghi phục vụ phân trang
    query_count = f"SELECT COUNT(*) FROM mart_api.latest_jobs_flat {where_clause};"
    
    async with db.pool.acquire() as conn:
        total = await conn.fetchval(query_count, *params)
        rows = await conn.fetch(query_list, *params, limit, offset)
        
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
        SELECT j.job_id, s.title_clean, s.description, c.display_name as company_name, j.canonical_url
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
```

---

### Bước 2.3: Tạo Entrypoint FastAPI (`src/api/main.py`)

Thiết lập ứng dụng, đăng ký kết nối cơ sở dữ liệu vào vòng đời ứng dụng (lifespan) và cấu hình static files:

```python
# src/api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from src.api.database import db
from src.api.routers import jobs
import uvicorn

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Kết nối DB khi ứng dụng khởi chạy
    await db.connect()
    yield
    # Ngắt kết nối khi ứng dụng dừng
    await db.disconnect()

app = FastAPI(
    title="JobITVN Data Serving API",
    description="API cung cấp thông tin tuyển dụng IT tại Việt Nam",
    version="1.0.0",
    lifespan=lifespan
)

# Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đăng ký router
app.include_router(jobs.router)

# Mount thư mục Static phục vụ giao diện Web Frontend
app.mount("/", StaticFiles(directory="src/api/static", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
```

---

### Bước 2.4: Giao diện HTML Dashboard (`src/api/static/index.html`)

Tạo giao diện Web Dashboard sang trọng, responsive gồm ô tìm kiếm, khối KPI và danh sách tin:

```html
<!-- src/api/static/index.html -->
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JobITVN - Hệ Thống Phân Tích Việc Làm IT</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="styles.css">
</head>
<body>
    <div class="glow-bg"></div>
    <div class="app-container">
        <!-- Header -->
        <header>
            <div class="logo">
                <span class="highlight">JobIT</span>VN
                <span class="badge">Data Platform v2.1</span>
            </div>
            <h1>Khám Phá Dữ Liệu Thị Trường Tuyển Dụng IT</h1>
        </header>

        <!-- Khối KPIs -->
        <section class="kpi-grid">
            <div class="kpi-card">
                <p class="kpi-label">Tổng Tin Tuyển Dụng Đang Mở</p>
                <h3 id="stat-total-jobs">-</h3>
            </div>
            <div class="kpi-card">
                <p class="kpi-label">Mức Lương Trung Bình</p>
                <h3><span id="stat-avg-salary">-</span> <small>Triệu VND</small></h3>
            </div>
            <div class="kpi-card">
                <p class="kpi-label">Top Kỹ Năng Đang Yêu Cầu</p>
                <div id="stat-top-skills" class="skills-list">-</div>
            </div>
        </section>

        <!-- Tìm Kiếm & Lọc -->
        <section class="search-section">
            <div class="search-box">
                <input type="text" id="search-input" placeholder="Tìm kiếm theo kỹ năng, chức danh (ví dụ: Python, React, Fresher)...">
                <button id="search-btn">Tìm Kiếm</button>
            </div>
            <div class="filters">
                <select id="filter-location">
                    <option value="">Tất cả địa điểm</option>
                    <option value="Hà Nội">Hà Nội</option>
                    <option value="Hồ Chí Minh">TP. Hồ Chí Minh</option>
                    <option value="Đà Nẵng">Đà Nẵng</option>
                </select>
            </div>
        </section>

        <!-- Nội dung chính -->
        <main class="main-content">
            <!-- Danh sách công việc -->
            <div class="jobs-column">
                <h2>Kết Quả Tìm Kiếm (<span id="results-count">0</span>)</h2>
                <div id="jobs-container" class="jobs-list">
                    <!-- Cards render tự động từ Javascript -->
                </div>
                <!-- Phân Trang -->
                <div class="pagination">
                    <button id="prev-btn" disabled>Trang Trước</button>
                    <span id="page-num">Trang 1 / 1</span>
                    <button id="next-btn" disabled>Trang Sau</button>
                </div>
            </div>

            <!-- Chi tiết công việc -->
            <div class="detail-column" id="detail-pane">
                <div class="detail-placeholder">
                    <p>Chọn một công việc từ danh sách để xem chi tiết mô tả công việc bằng AI & nhà tuyển dụng.</p>
                </div>
            </div>
        </main>
    </div>

    <script src="app.js"></script>
</body>
</html>
```

---

### Bước 2.5: CSS Premium Glassmorphism Theme (`src/api/static/styles.css`)

Trang trí giao diện theo phong cách **Glassmorphism** với nền tối huyền ảo, viền neon, mờ hậu cảnh và hiệu ứng 3D hover:

```css
/* src/api/static/styles.css */
:root {
    --bg-dark: #080b11;
    --card-bg: rgba(255, 255, 255, 0.03);
    --border-color: rgba(255, 255, 255, 0.08);
    --primary-neon: #00f2fe;
    --secondary-neon: #4facfe;
    --text-main: #f8fafc;
    --text-mute: #94a3b8;
    --font-family: 'Outfit', sans-serif;
}

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    background-color: var(--bg-dark);
    color: var(--text-main);
    font-family: var(--font-family);
    overflow-x: hidden;
    min-height: 100vh;
}

.glow-bg {
    position: fixed;
    top: -10%;
    left: 20%;
    width: 600px;
    height: 600px;
    background: radial-gradient(circle, rgba(0,242,254,0.08) 0%, rgba(79,172,254,0) 70%);
    z-index: -1;
    pointer-events: none;
}

.app-container {
    max-width: 1400px;
    margin: 0 auto;
    padding: 40px 20px;
}

header {
    text-align: center;
    margin-bottom: 40px;
}

header .logo {
    font-size: 2.2rem;
    font-weight: 800;
    margin-bottom: 10px;
    letter-spacing: 1px;
}

.highlight {
    background: linear-gradient(135deg, var(--primary-neon), var(--secondary-neon));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

header .badge {
    font-size: 0.8rem;
    padding: 3px 8px;
    border-radius: 12px;
    background-color: rgba(0, 242, 258, 0.15);
    border: 1px solid var(--primary-neon);
    color: var(--primary-neon);
    vertical-align: middle;
    margin-left: 10px;
}

header h1 {
    font-size: 1.2rem;
    color: var(--text-mute);
    font-weight: 400;
}

/* KPIs Grid */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 20px;
    margin-bottom: 40px;
}

.kpi-card {
    background: var(--card-bg);
    border: 1px solid var(--border-color);
    backdrop-filter: blur(16px);
    border-radius: 16px;
    padding: 24px;
    text-align: center;
    transition: transform 0.3s ease, border-color 0.3s ease;
}

.kpi-card:hover {
    transform: translateY(-5px);
    border-color: rgba(0, 242, 254, 0.3);
}

.kpi-label {
    color: var(--text-mute);
    font-size: 0.9rem;
    margin-bottom: 10px;
}

.kpi-card h3 {
    font-size: 2.2rem;
    font-weight: 800;
    background: linear-gradient(135deg, #fff, var(--text-mute));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.kpi-card small {
    font-size: 1rem;
    color: var(--text-mute);
}

.skills-list {
    display: flex;
    justify-content: center;
    flex-wrap: wrap;
    gap: 8px;
}

.skills-list span {
    font-size: 0.8rem;
    padding: 4px 10px;
    border-radius: 20px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--border-color);
}

/* Search Bar */
.search-section {
    display: flex;
    flex-direction: column;
    gap: 15px;
    margin-bottom: 40px;
    max-width: 800px;
    margin-left: auto;
    margin-right: auto;
}

.search-box {
    display: flex;
    background: rgba(255,255,255,0.02);
    border: 1px solid var(--border-color);
    border-radius: 50px;
    padding: 6px 6px 6px 20px;
    align-items: center;
}

.search-box input {
    flex: 1;
    background: transparent;
    border: none;
    outline: none;
    color: var(--text-main);
    font-size: 1rem;
}

.search-box button {
    background: linear-gradient(135deg, var(--primary-neon), var(--secondary-neon));
    border: none;
    color: #000;
    font-weight: 600;
    padding: 12px 30px;
    border-radius: 50px;
    cursor: pointer;
    transition: opacity 0.2s ease;
}

.search-box button:hover {
    opacity: 0.9;
}

.filters select {
    background: var(--bg-dark);
    color: var(--text-main);
    border: 1px solid var(--border-color);
    padding: 10px 20px;
    border-radius: 8px;
    outline: none;
    cursor: pointer;
}

/* Main Layout */
.main-content {
    display: grid;
    grid-template-columns: 1fr 1.2fr;
    gap: 30px;
}

.jobs-list {
    display: flex;
    flex-direction: column;
    gap: 15px;
    margin-top: 20px;
}

.job-card {
    background: var(--card-bg);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 20px;
    cursor: pointer;
    transition: all 0.2s ease;
}

.job-card:hover, .job-card.active {
    border-color: var(--primary-neon);
    background: rgba(0, 242, 254, 0.02);
    transform: translateX(4px);
}

.job-card h4 {
    font-size: 1.1rem;
    margin-bottom: 5px;
    font-weight: 600;
}

.job-card .company {
    color: var(--secondary-neon);
    font-size: 0.95rem;
    margin-bottom: 12px;
}

.job-details-row {
    display: flex;
    flex-wrap: wrap;
    gap: 15px;
    color: var(--text-mute);
    font-size: 0.85rem;
}

.job-details-row span {
    display: flex;
    align-items: center;
    gap: 4px;
}

/* Detail Column */
.detail-column {
    background: var(--card-bg);
    border: 1px solid var(--border-color);
    border-radius: 16px;
    padding: 30px;
    position: sticky;
    top: 20px;
    height: calc(100vh - 80px);
    overflow-y: auto;
}

.detail-placeholder {
    display: flex;
    justify-content: center;
    align-items: center;
    height: 100%;
    color: var(--text-mute);
    text-align: center;
    font-style: italic;
}

.job-detail-content h3 {
    font-size: 1.6rem;
    margin-bottom: 10px;
}

.job-detail-content .company {
    color: var(--secondary-neon);
    font-size: 1.1rem;
    margin-bottom: 20px;
}

.job-detail-content .desc {
    white-space: pre-wrap;
    line-height: 1.6;
    color: #cbd5e1;
    font-size: 0.95rem;
}

.apply-btn {
    display: inline-block;
    background: linear-gradient(135deg, var(--primary-neon), var(--secondary-neon));
    color: #000;
    text-decoration: none;
    font-weight: 600;
    padding: 12px 30px;
    border-radius: 8px;
    margin-top: 20px;
    text-align: center;
}

/* Pagination */
.pagination {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 15px;
    margin-top: 30px;
}

.pagination button {
    background: transparent;
    border: 1px solid var(--border-color);
    color: var(--text-main);
    padding: 8px 16px;
    border-radius: 6px;
    cursor: pointer;
}

.pagination button:disabled {
    opacity: 0.3;
    cursor: not-allowed;
}

.pagination button:not(:disabled):hover {
    border-color: var(--primary-neon);
    color: var(--primary-neon);
}
```

---

### Bước 2.6: Vanilla JavaScript Controller (`src/api/static/app.js`)

Logic gửi request lấy danh sách, tìm kiếm, phân trang và cập nhật nội dung tin chi tiết:

```javascript
// src/api/static/app.js
const API_URL = ''; // Gọi relative path vì chạy chung host/port

let currentPage = 1;
let totalPages = 1;

// Khởi chạy khi load trang
document.addEventListener("DOMContentLoaded", () => {
    loadSummaryStats();
    loadJobs();

    // Đăng ký sự kiện
    document.getElementById("search-btn").addEventListener("click", () => {
        currentPage = 1;
        loadJobs();
    });
    
    document.getElementById("search-input").addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
            currentPage = 1;
            loadJobs();
        }
    });

    document.getElementById("filter-location").addEventListener("change", () => {
        currentPage = 1;
        loadJobs();
    });

    document.getElementById("prev-btn").addEventListener("click", () => {
        if (currentPage > 1) {
            currentPage--;
            loadJobs();
        }
    });

    document.getElementById("next-btn").addEventListener("click", () => {
        if (currentPage < totalPages) {
            currentPage++;
            loadJobs();
        }
    });

    // TỰ ĐỘNG CẬP NHẬT REALTIME MỖI 30 GIÂY MÀ KHÔNG CẦN TẢI LẠI TRANG
    setInterval(() => {
        // Chỉ tự động cập nhật khi người dùng không đang gõ tìm kiếm để tránh làm gián đoạn trải nghiệm
        const isUserTyping = document.activeElement === document.getElementById("search-input");
        if (!isUserTyping) {
            loadSummaryStats();
            loadJobs();
        }
    }, 30000);
});

async function loadSummaryStats() {
    try {
        const res = await fetch(`${API_URL}/api/v1/stats/summary`);
        const stats = await res.json();

        document.getElementById("stat-total-jobs").innerText = stats.total_jobs.toLocaleString();
        document.getElementById("stat-avg-salary").innerText = stats.average_salary_million;

        const skillsContainer = document.getElementById("stat-top-skills");
        skillsContainer.innerHTML = stats.top_skills.map(s => 
            `<span>${s.name} (${s.count})</span>`
        ).join("");
    } catch (err) {
        console.error("Lỗi khi load thống kê:", err);
    }
}

async function loadJobs() {
    const searchVal = document.getElementById("search-input").value;
    const locationVal = document.getElementById("filter-location").value;
    
    let url = `${API_URL}/api/v1/jobs?page=${currentPage}&limit=10`;
    if (searchVal) url += `&search=${encodeURIComponent(searchVal)}`;
    if (locationVal) url += `&location=${encodeURIComponent(locationVal)}`;

    try {
        const res = await fetch(url);
        const result = await res.json();

        renderJobsList(result.data);
        updatePagination(result.pagination);
    } catch (err) {
        console.error("Lỗi khi load danh sách jobs:", err);
    }
}

function renderJobsList(jobs) {
    const container = document.getElementById("jobs-container");
    document.getElementById("results-count").innerText = jobs.length;
    
    if (jobs.length === 0) {
        container.innerHTML = `<p style="padding: 20px; font-style: italic; color: #94a3b8;">Không tìm thấy công việc nào phù hợp.</p>`;
        return;
    }

    container.innerHTML = jobs.map(job => `
        <div class="job-card" onclick="loadJobDetail(${job.job_id}, this)">
            <h4>${job.title_clean}</h4>
            <div class="company">${job.company_display_name}</div>
            <div class="job-details-row">
                <span>📍 ${job.location_clean || 'Hà Nội'}</span>
                <span>💰 ${job.salary_raw || 'Thỏa thuận'}</span>
                <span>💼 ${job.experience_raw || 'Không yêu cầu'}</span>
            </div>
        </div>
    `).join("");
}

function updatePagination(pagination) {
    currentPage = pagination.page;
    totalPages = pagination.total_pages;

    document.getElementById("page-num").innerText = `Trang ${currentPage} / ${totalPages || 1}`;
    document.getElementById("prev-btn").disabled = currentPage <= 1;
    document.getElementById("next-btn").disabled = currentPage >= totalPages;
}

async function loadJobDetail(jobId, element) {
    // Đánh dấu card active
    document.querySelectorAll(".job-card").forEach(c => c.classList.remove("active"));
    if (element) element.classList.add("active");

    const detailPane = document.getElementById("detail-pane");
    detailPane.innerHTML = `<div class="detail-placeholder"><p>Đang tải chi tiết...</p></div>`;

    try {
        const res = await fetch(`${API_URL}/api/v1/jobs/${jobId}`);
        if (res.status === 404) {
            detailPane.innerHTML = `<div class="detail-placeholder"><p>Không tìm thấy mô tả chi tiết.</p></div>`;
            return;
        }
        const job = await res.json();

        detailPane.innerHTML = `
            <div class="job-detail-content">
                <h3>${job.title_clean}</h3>
                <div class="company">${job.company_name}</div>
                <hr style="border: 0; border-top: 1px solid var(--border-color); margin-bottom: 20px;">
                <div class="desc">${job.description || 'Không có mô tả chi tiết.'}</div>
                <a href="${job.canonical_url}" target="_blank" class="apply-btn">Ứng Tuyển Ngay ➔</a>
            </div>
        `;
    } catch (err) {
        console.error("Lỗi khi load chi tiết công việc:", err);
        detailPane.innerHTML = `<div class="detail-placeholder"><p>Lỗi kết nối máy chủ.</p></div>`;
    }
}
```

---

## 3. Tích Hợp Vào Docker Compose

Để chạy FastAPI tự động và phân tách cổng với Airflow, hãy chỉnh sửa/bổ sung cấu hình sau:

### Bước 3.1: Cập nhật `docker-compose.yml`

Thêm service `web-api` vào cuối khối `services` trong file `docker-compose.yml`:

```yaml
  web-api:
    build: .
    command: python -m src.api.main
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://airflow:airflow@postgres:5432/job_scraper_db
      PYTHONPATH: /opt/airflow
    volumes:
      - .:/opt/airflow
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped
```

### Bước 3.2: Đảm bảo các dependencies trong `requirements.txt`

FastAPI và driver kết nối DB bất đồng bộ cần các thư viện sau (hầu hết đã có sẵn trong image Airflow, nhưng cần khai báo rõ nếu tách Service):
* `fastapi>=0.100.0`
* `uvicorn>=0.22.0`
* `asyncpg>=0.28.0`

---

## 4. Cách Vận Hành Sau Khi Triển Khai

1. Chạy lệnh để build lại container và cập nhật cấu trúc:
   ```bash
   docker compose build web-api
   docker compose up -d
   ```
2. Mở trình duyệt Web của bạn tại địa chỉ: **http://localhost:8000** để trải nghiệm cổng tìm kiếm việc làm IT.
3. Khi bạn muốn xem tài liệu API (Swagger UI), truy cập: **http://localhost:8000/docs**

---

## 5. Hướng Dẫn Cấu Hình Dashboard Realtime Trên Power BI

Để tạo một Dashboard Power BI tự động cập nhật số liệu thời gian thực (Realtime) mỗi khi pipeline cào dữ liệu mới vào DB mà không cần người dùng nhấn nút Refresh thủ công:

### Bước 5.1: Cấu hình Kết nối thông qua DirectQuery
1. Mở **Power BI Desktop**.
2. Chọn **Get Data** ➔ **PostgreSQL database**.
3. Điền thông tin máy chủ:
   * **Server**: `localhost` (hoặc `127.0.0.1`)
   * **Database**: `job_scraper_db`
   * **Data Connectivity mode**: **Bắt buộc chọn DirectQuery**. *(Chế độ này sẽ không nạp dữ liệu cứng vào RAM của Power BI, mà Power BI sẽ tự động truy vấn trực tiếp xuống PostgreSQL mỗi khi hiển thị).*
4. Nhập Username: `airflow` / Password: `airflow`.

### Bước 5.2: Bật Tự Động Làm Mới Trang (Automatic Page Refresh)
Để Power BI tự động gửi truy vấn cập nhật biểu đồ theo chu kỳ:
1. Click chọn vào một vùng trống bất kỳ trên trang vẽ báo cáo (**Report Canvas**).
2. Tại cột **Visualizations** ở bên phải, click chọn biểu tượng hình cái chổi/cây cọ vẽ (**Format page**).
3. Tìm và mở rộng mục **Page refresh**.
4. Chuyển trạng thái từ **Off** sang **On**.
5. Cấu hình tần suất cập nhật:
   * Chọn đơn vị: **Seconds** (Giây) hoặc **Minutes** (Phút).
   * Điền giá trị: **10** (Để tự động làm mới sau mỗi 10 giây).
6. Kéo thả các visual (biểu đồ) từ các bảng/views trong schema `dwh` hoặc `mart_api`. Mỗi 10 giây, toàn bộ biểu đồ sẽ tự động truy vấn CSDL và hiển thị dữ liệu mới nhất.

---

## 6. Hướng Dẫn Tích Hợp Web Backend RESTful API Khác (Node.js, Python, Go, Java...)

Nếu bạn không muốn dùng FastAPI mà muốn sử dụng các ngôn ngữ khác để xây dựng web service RESTful API (ví dụ: Node.js Express, NestJS, Spring Boot, Go Fiber, Django, Laravel), bạn hoàn toàn có thể tận dụng dữ liệu trong PostgreSQL một cách dễ dàng:

### 6.1. Nguyên tắc truy vấn
* **Endpoints danh sách/tìm kiếm việc làm (GET /jobs):**
  Truy cập trực tiếp vào Materialized View `mart_api.latest_jobs_flat`. View này chứa dữ liệu đã được khử chuẩn (denormalized), tối ưu hóa cấu trúc và có sẵn cột `ts_vector_document` kèm GIN Index để phục vụ tìm kiếm Full-Text Search.
  *Ví dụ câu lệnh SQL tìm kiếm trong Node.js/Go:*
  ```sql
  SELECT job_id, title_clean, company_display_name, salary_raw, location_clean, scraped_at
  FROM mart_api.latest_jobs_flat
  WHERE is_active = TRUE 
    AND ts_vector_document @@ plainto_tsquery('vietnamese', $1)
  ORDER BY scraped_at DESC
  LIMIT $2 OFFSET $3;
  ```
* **Endpoints chi tiết công việc (GET /jobs/:id):**
  Lấy dữ liệu mô tả (description) từ bảng `silver.job_snapshots` kết hợp thông tin tĩnh từ `silver.jobs`.
  ```sql
  SELECT j.job_id, s.title_clean, s.description, c.display_name as company_name, j.canonical_url
  FROM silver.jobs j
  JOIN silver.job_snapshots s ON j.job_id = s.job_id AND s.is_current = TRUE
  JOIN silver.companies c ON j.company_id = c.company_id
  WHERE j.job_id = $1;
  ```

---

## 7. Hướng Dẫn Tận Dụng Dữ Liệu Cho Phân Tích Dữ Liệu (Data Analysis - DA)

Lớp dữ liệu Gold và Silver được thiết kế tối ưu cho phân tích hành vi và xu hướng tuyển dụng thị trường:

### 7.1. Phân tích trên PostgreSQL (Star Schema)
Bạn có thể kết nối các công cụ phân tích hoặc dùng Python (Pandas/Polars) kết nối trực tiếp tới cơ sở dữ liệu để chạy các truy vấn phân tích:
* **Tính toán xu hướng kỹ năng yêu cầu nhiều nhất theo tuần:**
  ```sql
  SELECT s.display_name, COUNT(jss.snapshot_id) as demand_count
  FROM silver.skills s
  JOIN silver.job_snapshot_skills jss ON s.skill_id = jss.skill_id
  JOIN silver.job_snapshots js ON jss.snapshot_id = js.snapshot_id
  WHERE js.valid_from >= CURRENT_DATE - INTERVAL '30 days'
  GROUP BY s.display_name
  ORDER BY demand_count DESC
  LIMIT 10;
  ```

### 7.2. Phân tích hiệu năng cao bằng Delta Lake (S3 Parquet)
Thay vì truy vấn trực tiếp vào database nghiệp vụ (gây chậm hệ thống), Data Analyst nên kết nối tới dữ liệu dạng Delta Table trên S3 (`s3://jobit-gold/gold/mart_bi/`) thông qua **DuckDB** để xử lý hàng triệu dòng dữ liệu siêu tốc:
```python
import duckdb

# Kết nối và quét trực tiếp thư mục Delta S3
con = duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs; INSTALL delta; LOAD delta;")
con.execute(\"\"\"
    SET s3_endpoint='localhost:4566';
    SET s3_access_key_id='test';
    SET s3_secret_access_key='test';
    SET s3_use_ssl=false;
    SET s3_url_style='path';
\"\"\")

# Chạy truy vấn phân tích lương trung bình theo kỹ năng trực tiếp trên file Parquet S3
df = con.execute(\"\"\"
    SELECT skill_name, AVG(salary_midpoint_vnd) as avg_salary
    FROM delta_scan('s3://jobit-gold/gold/mart_bi/agg_salary_by_company')
    GROUP BY skill_name
    ORDER BY avg_salary DESC;
\"\"\").fetchdf()
print(df)
```

---

## 8. Hướng Dẫn Tận Dụng Dữ Liệu Cho AI / Machine Learning & RAG

Dữ liệu chất lượng cao từ dự án là nguyên liệu vàng cho các tác vụ mô hình hóa và AI thông minh:

### 8.1. Xây dựng mô hình Dự đoán Lương (Predictive ML)
Bạn có thể xây dựng mô hình dự đoán mức lương dựa trên các trường thông tin tuyển dụng (như Kỹ năng, Vị trí địa lý, Vai trò, Kinh nghiệm):
* **Lấy dữ liệu đặc trưng (Features extraction):** Sử dụng Delta Table `mart_ml/job_features` được export tự động trên S3.
* **Quy trình:**
  1. Đọc tệp Parquet từ S3 bằng Pandas/Polars.
  2. Encode các biến phân loại (Location, Job level, Required Skills).
  3. Huấn luyện mô hình hồi quy (ví dụ: XGBoost Regressor, LightGBM) để dự đoán `salary_midpoint_vnd`.
  4. Triển khai mô hình thành một endpoint `/api/v1/predict-salary` trên API phục vụ ước tính lương cho các tin tuyển dụng ghi "Lương thỏa thuận".

### 8.2. Ứng ứng Tìm kiếm Ngữ nghĩa & Chatbot tư vấn việc làm (RAG - LLMs)
Bạn có thể xây dựng một chatbot AI tư vấn lộ trình học và gợi ý việc làm phù hợp cho ứng viên bằng kỹ thuật RAG (Retrieval-Augmented Generation):
1. **Trích xuất dữ liệu:** Truy vấn cột `description` (Mô tả công việc) trong bảng `silver.job_snapshots` và thông tin kỹ năng để lấy ngữ cảnh.
2. **Tạo Embedding:** Sử dụng các mô hình Embedding (như `text-embedding-3-small` của OpenAI hoặc mô hình mã nguồn mở trên Hugging Face) để chuyển hóa mô tả công việc thành các Vector Embeddings.
3. **Lưu trữ vào Vector Database:** Đẩy các vector này kèm metadata (Job Title, Company, Link ứng tuyển) vào một Vector DB như **Qdrant**, **Milvus**, hoặc sử dụng extension **pgvector** ngay trong chính CSDL PostgreSQL của bạn.
4. **Xây dựng RAG Chatbot:**
   * Khi ứng viên chat: *"Tôi biết Python và SQL, muốn tìm việc làm Fresher tại Hà Nội"*
   * Chatbot sẽ Vectorize câu hỏi của người dùng ➔ Thực hiện Vector Similarity Search trên Vector DB để tìm ra 3 tin tuyển dụng có mô tả phù hợp nhất.
   * Đưa thông tin 3 tin này vào Prompt của LLM (GPT-4, Gemini) để sinh câu trả lời tư vấn và gợi ý chi tiết kèm link ứng tuyển.

