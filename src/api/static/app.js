// src/api/static/app.js — v5
const API_URL = "";

let currentPage = 1;
let salaryChartInstance = null;
let locationChartInstance = null;
let skillsChartInstance = null;

// ── Helpers ──────────────────────────────────────────────
function fmt(num) {
    if (num === null || num === undefined || num === "") return "0";
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

function srcClass(name) {
    const map = {
        topcv: "src-topcv",
        jobsgo: "src-jobsgo",
        linkedin: "src-linkedin",
        itviec: "src-itviec",
        vietnamworks: "src-vietnamworks",
        careerviet: "src-careerviet",
        joboko: "src-joboko",
        "123job": "src-123job",
    };
    return map[(name || "").toLowerCase()] || "src-default";
}

function formatTimeAgo(dateStr) {
    if (!dateStr) return null;
    try {
        const date = new Date(dateStr);
        if (isNaN(date.getTime())) return null;
        const now = new Date();
        const diffSec = Math.floor((now - date) / 1000);
        if (diffSec < 60) return "Vừa cập nhật";
        const diffMin = Math.floor(diffSec / 60);
        if (diffMin < 60) return `${diffMin} phút trước`;
        const diffHours = Math.floor(diffMin / 60);
        if (diffHours < 24) return `${diffHours} giờ trước`;
        const diffDays = Math.floor(diffHours / 24);
        if (diffDays === 1) return "Hôm qua";
        if (diffDays < 7) return `${diffDays} ngày trước`;
        if (diffDays < 30) return `${Math.floor(diffDays / 7)} tuần trước`;
        return date.toLocaleDateString("vi-VN");
    } catch (e) {
        return null;
    }
}

function getDeadlineInfo(job) {
    if (job.is_expired) {
        const days = job.remaining_days !== null && job.remaining_days !== undefined ? Math.abs(job.remaining_days) : null;
        const text = days !== null && days > 0 ? `❌ Hết hạn (${days} ngày trước)` : `❌ Đã hết hạn`;
        return { badgeClass: "badge-expired", text, isExpired: true };
    }
    if (job.remaining_days !== null && job.remaining_days !== undefined) {
        if (job.remaining_days === 0) {
            return { badgeClass: "badge-urgent", text: `🚨 Hết hạn hôm nay!`, isExpired: false };
        }
        if (job.remaining_days <= 3) {
            return { badgeClass: "badge-urgent", text: `🚨 Còn ${job.remaining_days} ngày`, isExpired: false };
        }
        if (job.remaining_days <= 7) {
            return { badgeClass: "badge-warning", text: `⏳ Còn ${job.remaining_days} ngày`, isExpired: false };
        }
        return { badgeClass: "badge-active", text: `📅 Còn ${job.remaining_days} ngày`, isExpired: false };
    }
    if (job.deadline_raw) {
        return { badgeClass: "badge-active", text: `⏳ Hạn: ${job.deadline_raw}`, isExpired: false };
    }
    return { badgeClass: "badge-none", text: `⏳ Không thời hạn`, isExpired: false };
}

// ── DOMContentLoaded ─────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    // Tab navigation
    document.querySelectorAll(".nav-link:not(.external)").forEach(link => {
        link.addEventListener("click", e => {
            e.preventDefault();
            const targetId = link.getAttribute("data-target");
            document.querySelectorAll(".nav-link:not(.external)").forEach(n => n.classList.remove("active"));
            link.classList.add("active");
            document.querySelectorAll(".tab-content").forEach(c => {
                c.classList.remove("active");
                c.classList.add("hidden");
            });
            const tab = document.getElementById(targetId);
            tab.classList.remove("hidden");
            tab.classList.add("active");

            if (targetId === "analytics-tab") loadAnalytics();
        });
    });

    // Toggle advanced filters
    const toggleBtn = document.getElementById("toggle-filter-btn");
    const advFilters = document.getElementById("advanced-filters");
    toggleBtn.addEventListener("click", () => {
        advFilters.classList.toggle("hidden");
        toggleBtn.classList.toggle("active");
    });

    // Search
    document.getElementById("search-btn").addEventListener("click", () => { currentPage = 1; loadJobs(); });
    document.getElementById("search-input").addEventListener("keypress", e => { if (e.key === "Enter") { currentPage = 1; loadJobs(); } });

    // Filters
    ["filter-status", "filter-location", "filter-salary", "filter-experience", "filter-source", "filter-sort"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener("change", () => { currentPage = 1; loadJobs(); });
    });

    // Pagination
    document.getElementById("prev-btn").addEventListener("click", () => { if (currentPage > 1) { currentPage--; loadJobs(); } });
    document.getElementById("next-btn").addEventListener("click", () => { currentPage++; loadJobs(); });

    // Initial data
    loadKPIs();
    loadJobs();
});

// ── KPI ──────────────────────────────────────────────────
async function loadKPIs() {
    try {
        const res = await fetch(`${API_URL}/stats/kpi`);
        if (!res.ok) {
            console.error("KPI load HTTP error:", res.status);
            return;
        }
        const d = await res.json();

        // Total jobs
        setKPIVal("stat-total-jobs", fmt(d.total_jobs));

        // New jobs in 7 days
        const sub = document.getElementById("stat-new-jobs-sub");
        if (sub) sub.textContent = "+" + fmt(d.new_jobs_7d || 0);

        // Average salary
        const avgSal = d.average_salary_million;
        setKPIVal("stat-avg-salary", avgSal && avgSal !== "N/A" ? `${avgSal} <small style="font-size:0.8rem;font-weight:500;color:var(--text-muted)">Tr. VNĐ</small>` : "N/A");

        // Median salary
        const med = document.getElementById("stat-median-salary");
        if (med) med.textContent = d.median_salary && d.median_salary !== "0" ? d.median_salary : "N/A";

        // Companies
        setKPIVal("stat-total-companies", fmt(d.total_companies));

        // Disclosure rate
        const disc = parseFloat(d.disclosure_rate || 0);
        setKPIVal("stat-disclosure-rate", `${disc.toFixed(1)}<span style="font-size:1rem;font-weight:600;color:var(--text-muted)">%</span>`);

        // Fresher jobs
        setKPIVal("stat-fresher-jobs", fmt(d.fresher_jobs));

        // Top skills → skills bar
        const skillsEl = document.getElementById("stat-top-skills");
        if (skillsEl && Array.isArray(d.top_skills)) {
            skillsEl.innerHTML = d.top_skills.slice(0, 10).map(s => {
                const name = typeof s === "object" ? s.name : s;
                const count = typeof s === "object" ? s.count : null;
                const countBadge = count ? `<span class="chip-count">${fmt(count)}</span>` : "";
                return `<span class="skill-chip">${name}${countBadge}</span>`;
            }).join("");
        }
    } catch (err) {
        console.error("KPI load error:", err);
    }
}

function setKPIVal(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
}

// ── Jobs list ─────────────────────────────────────────────
async function loadJobs() {
    const search = document.getElementById("search-input").value;
    const statusEl = document.getElementById("filter-status");
    const status = statusEl ? statusEl.value : "";
    const location = document.getElementById("filter-location").value;
    const salary = document.getElementById("filter-salary").value;
    const experience = document.getElementById("filter-experience").value;
    const source = document.getElementById("filter-source").value;
    const sort = document.getElementById("filter-sort").value;

    let url = `${API_URL}/jobs?page=${currentPage}&limit=10`;
    if (search)     url += `&search=${encodeURIComponent(search)}`;
    if (status)     url += `&status=${encodeURIComponent(status)}`;
    if (location)   url += `&location=${encodeURIComponent(location)}`;
    if (salary)     url += `&salary=${encodeURIComponent(salary)}`;
    if (experience) url += `&experience=${encodeURIComponent(experience)}`;
    if (source)     url += `&source=${encodeURIComponent(source)}`;
    if (sort)       url += `&sort=${encodeURIComponent(sort)}`;

    // Show skeleton
    const container = document.getElementById("jobs-container");
    container.innerHTML = buildSkeletons(4);
    container.scrollTop = 0;

    try {
        const res = await fetch(url);
        const d = await res.json();
        if (!res.ok) {
            throw new Error(d.detail || `Máy chủ phản hồi mã lỗi ${res.status}`);
        }

        // Support both flat and paginated response shapes
        const jobs = Array.isArray(d.data) ? d.data : (Array.isArray(d) ? d : []);
        const total = d.total ?? jobs.length;
        const page = d.page || currentPage;
        const totalPages = d.total_pages || d.pagination?.total_pages || 1;

        const countEl = document.getElementById("results-count");
        if (countEl) countEl.textContent = `${fmt(total)} kết quả`;

        renderJobs(jobs, container);

        document.getElementById("page-num").textContent = `Trang ${page} / ${totalPages}`;
        document.getElementById("prev-btn").disabled = page <= 1;
        document.getElementById("next-btn").disabled = page >= totalPages;

    } catch (err) {
        console.error("Jobs load error:", err);
        container.innerHTML = `<div class="empty-state"><p style="color:#ef4444">Không thể tải dữ liệu: ${err.message || "Vui lòng thử lại"}</p></div>`;
    }
}

function buildSkeletons(n) {
    return Array.from({ length: n }, () => `
        <div class="job-card" style="pointer-events:none;">
            <div class="job-card-top">
                <div class="skeleton" style="width:65%;height:15px;border-radius:4px;"></div>
                <div class="skeleton" style="width:44px;height:13px;border-radius:4px;"></div>
            </div>
            <div class="skeleton" style="width:45%;height:12px;border-radius:4px;margin:8px 0 12px;"></div>
            <div style="display:flex;gap:8px;">
                <div class="skeleton" style="width:55px;height:11px;border-radius:4px;"></div>
                <div class="skeleton" style="width:75px;height:11px;border-radius:4px;"></div>
                <div class="skeleton" style="width:65px;height:11px;border-radius:4px;"></div>
            </div>
        </div>
    `).join("");
}

function renderJobs(jobs, container) {
    container.innerHTML = "";
    if (!Array.isArray(jobs) || jobs.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M15.182 16.318A4.486 4.486 0 0 0 12.016 15a4.486 4.486 0 0 0-3.198 1.318M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM9.75 9.75c0 .414-.168.75-.375.75S9 10.164 9 9.75 9.168 9 9.375 9s.375.336.375.75Zm-.375 0h.008v.015h-.008V9.75Zm5.625 0c0 .414-.168.75-.375.75s-.375-.336-.375-.75.168-.75.375-.75.375.336.375.75Zm-.375 0h.008v.015h-.008V9.75Z" />
                </svg>
                <p>Không tìm thấy công việc phù hợp với bộ lọc hiện tại.</p>
            </div>`;
        return;
    }

    jobs.forEach(job => {
        const card = document.createElement("div");
        const deadlineInfo = getDeadlineInfo(job);
        const timeAgo = formatTimeAgo(job.last_seen_at || job.crawled_at);

        card.className = `job-card ${deadlineInfo.isExpired ? "is-expired" : ""}`;
        card.innerHTML = `
            <div class="job-card-top">
                <h4>${job.title_clean || job.job_title || "Không có tiêu đề"}</h4>
                <span class="src-badge ${srcClass(job.source_name)}">${job.source_name || "—"}</span>
            </div>
            <div class="company">${job.company_display_name || job.company_name || "—"}</div>
            <div class="job-meta">
                <span>📍 ${job.location_clean || "Hà Nội"}</span>
                <span>💰 ${job.salary_raw || "Thỏa thuận"}</span>
                <span>💼 ${job.experience_raw || "Không yêu cầu"}</span>
            </div>
            <div class="job-card-footer">
                <span class="deadline-pill ${deadlineInfo.badgeClass}">${deadlineInfo.text}</span>
                ${timeAgo ? `<span class="time-ago">🕒 ${timeAgo}</span>` : ""}
            </div>
        `;
        card.addEventListener("click", () => {
            document.querySelectorAll(".job-card").forEach(c => c.classList.remove("active"));
            card.classList.add("active");
            loadJobDetail(job.job_id || job.id);
        });
        container.appendChild(card);
    });
}

// ── Job Detail ────────────────────────────────────────────
async function loadJobDetail(jobId) {
    const pane = document.getElementById("detail-pane");
    pane.innerHTML = `
        <div class="detail-placeholder">
            <div class="skeleton" style="width:48px;height:48px;border-radius:14px;margin-bottom:16px;"></div>
            <div class="skeleton" style="width:80%;height:18px;border-radius:5px;margin-bottom:8px;"></div>
            <div class="skeleton" style="width:50%;height:14px;border-radius:5px;"></div>
        </div>`;

    try {
        const res = await fetch(`${API_URL}/jobs/${jobId}`);
        const job = await res.json();

        const firstLetter = (job.company_name || "C").charAt(0).toUpperCase();

        // Tính experience text
        const expMin = job.experience_min_years;
        const expMax = job.experience_max_years;
        let expText = "Không yêu cầu kinh nghiệm";
        if (expMin !== null && expMin !== undefined && expMax !== null && expMax !== undefined) {
            if (expMin === expMax) expText = expMin > 0 ? `${expMin} năm kinh nghiệm` : "Dưới 1 năm kinh nghiệm";
            else expText = `${expMin} - ${expMax} năm kinh nghiệm`;
        } else if (expMin !== null && expMin !== undefined) {
            expText = `Từ ${expMin} năm kinh nghiệm`;
        } else if (expMax !== null && expMax !== undefined) {
            expText = `Đến ${expMax} năm kinh nghiệm`;
        }

        const deadlineInfo = getDeadlineInfo(job);
        const timeAgo = formatTimeAgo(job.last_seen_at || job.crawled_at);

        let bannerHtml = "";
        if (deadlineInfo.isExpired) {
            bannerHtml = `
                <div class="job-banner banner-expired">
                    <div class="banner-icon">⚠️</div>
                    <div>
                        <div class="banner-title">Công việc đã hết hạn nhận hồ sơ</div>
                        <div class="banner-sub">Hạn nộp: ${job.deadline_raw || job.deadline_date || "Đã hết hạn"}. Thông tin được lưu trữ để tham khảo yêu cầu công việc và mặt bằng lương.</div>
                    </div>
                </div>
            `;
        } else if (job.remaining_days !== null && job.remaining_days !== undefined && job.remaining_days <= 3) {
            bannerHtml = `
                <div class="job-banner banner-urgent">
                    <div class="banner-icon">🚨</div>
                    <div>
                        <div class="banner-title">Sắp hết hạn ứng tuyển!</div>
                        <div class="banner-sub">Chỉ còn ${job.remaining_days === 0 ? "hôm nay" : job.remaining_days + " ngày"} để nộp CV (${job.deadline_raw || job.deadline_date}). Hãy ứng tuyển sớm!</div>
                    </div>
                </div>
            `;
        } else {
            bannerHtml = `
                <div class="job-banner banner-active">
                    <div class="banner-icon">✅</div>
                    <div>
                        <div class="banner-title">Đang mở nhận hồ sơ ứng tuyển</div>
                        <div class="banner-sub">Hạn nộp: ${job.deadline_raw || (job.remaining_days ? `Còn ${job.remaining_days} ngày` : "Nhận hồ sơ liên tục")}</div>
                    </div>
                </div>
            `;
        }

        let desc = (job.description || "Không có mô tả chi tiết.")
            .replace(/\n\s*\n/g, "\n\n")
            .replace(/\n[-*•] /g, "\n<li class='desc-bullet'>")
            .replace(/([A-ZÀ-Ỹ][A-ZÀ-Ỹ\s]+:)/g, "<span class='section-title'>$1</span>");

        pane.innerHTML = `
            <div class="detail-header">
                <div class="company-logo">${firstLetter}</div>
                <div style="flex:1;min-width:0;">
                    <div class="detail-title">${job.title_clean || "Không có tiêu đề"}</div>
                    <div class="detail-company">${job.company_name || "—"}</div>
                </div>
            </div>

            ${bannerHtml}

            <div class="detail-overview-grid">
                <div class="overview-item">
                    <span class="overview-label">📍 Địa điểm</span>
                    <strong class="overview-val">${job.location_clean || "Hà Nội"}</strong>
                </div>
                <div class="overview-item">
                    <span class="overview-label">💰 Mức lương</span>
                    <strong class="overview-val text-green">${job.salary_raw || "Thỏa thuận"}</strong>
                </div>
                <div class="overview-item">
                    <span class="overview-label">💼 Kinh nghiệm</span>
                    <strong class="overview-val">${expText}</strong>
                </div>
                <div class="overview-item">
                    <span class="overview-label">🏢 Nguồn cào</span>
                    <strong class="overview-val">${job.source_name || "—"}</strong>
                </div>
                <div class="overview-item">
                    <span class="overview-label">🕒 Cập nhật</span>
                    <strong class="overview-val">${timeAgo ? timeAgo : "Gần đây"}</strong>
                </div>
                <div class="overview-item">
                    <span class="overview-label">⏳ Hạn ứng tuyển</span>
                    <strong class="overview-val">${job.deadline_raw || (job.deadline_date ? new Date(job.deadline_date).toLocaleDateString("vi-VN") : "Không thời hạn")}</strong>
                </div>
            </div>

            <hr class="detail-divider">
            <div class="detail-desc">${desc}</div>
            <div class="apply-sticky">
                <a href="${job.canonical_url || "#"}" target="_blank" class="btn-apply ${deadlineInfo.isExpired ? "btn-expired" : ""}">
                    ${deadlineInfo.isExpired ? "Xem Bài Tuyển Gốc (Đã Hết Hạn) ↗" : "Ứng Tuyển / Xem Nguồn Gốc ↗"}
                </a>
            </div>
        `;
    } catch (err) {
        console.error("Job detail error:", err);
        pane.innerHTML = `<div class="detail-placeholder"><p style="color:#ef4444">Lỗi tải dữ liệu. Vui lòng thử lại.</p></div>`;
    }
}

// ── Analytics ─────────────────────────────────────────────
async function loadAnalytics() {
    await Promise.all([
        loadSalaryChart(),
        loadLocationChart(),
        loadSkillsDemandChart(),
    ]);
}

const CHART_DEFAULTS = {
    color: "#64748b",
    font: { family: "'Inter', sans-serif", size: 12 },
};

function applyChartDefaults() {
    Chart.defaults.color = CHART_DEFAULTS.color;
    Chart.defaults.font.family = CHART_DEFAULTS.font.family;
    Chart.defaults.font.size = CHART_DEFAULTS.font.size;
}

async function loadSalaryChart() {
    try {
        const res = await fetch(`${API_URL}/stats/salary-by-skill`);
        if (!res.ok) return;
        const data = await res.json();
        if (!Array.isArray(data)) return;
        applyChartDefaults();
        const ctx = document.getElementById("salaryChart").getContext("2d");
        if (salaryChartInstance) salaryChartInstance.destroy();

        const labels = data.map(d => d.skill_name);
        const avgMin = data.map(d => (d.avg_salary_min_vnd || 0) / 1e6);
        const maxSal = data.map(d => (d.max_salary_max_vnd || 0) / 1e6);

        salaryChartInstance = new Chart(ctx, {
            type: "bar",
            data: {
                labels,
                datasets: [
                    {
                        label: "Lương TB Min (Tr. VNĐ)",
                        data: avgMin,
                        backgroundColor: "rgba(56,189,248,0.75)",
                        borderRadius: 5,
                        borderSkipped: false,
                    },
                    {
                        label: "Lương Max (Tr. VNĐ)",
                        data: maxSal,
                        backgroundColor: "rgba(129,140,248,0.65)",
                        borderRadius: 5,
                        borderSkipped: false,
                    },
                ],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: {
                    legend: { position: "top", labels: { padding: 16, usePointStyle: true, pointStyle: "rectRounded" } },
                    tooltip: {
                        mode: "index", intersect: false,
                        backgroundColor: "rgba(7,13,26,0.95)",
                        titleColor: "#38bdf8", bodyColor: "#94a3b8",
                        borderColor: "rgba(56,189,248,0.2)", borderWidth: 1,
                        callbacks: { label: ctx => ` ${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)} triệu` },
                    },
                },
                scales: {
                    x: { grid: { color: "rgba(255,255,255,0.04)" }, ticks: { maxRotation: 35 } },
                    y: { beginAtZero: true, grid: { color: "rgba(255,255,255,0.04)" }, ticks: { callback: v => v + "M" } },
                },
            },
        });
    } catch (err) { console.error("Salary chart error:", err); }
}

async function loadLocationChart() {
    try {
        const res = await fetch(`${API_URL}/stats/locations?top_n=8`);
        if (!res.ok) return;
        const body = await res.json();
        const data = Array.isArray(body.data) ? body.data : (Array.isArray(body) ? body : []);
        if (!data.length) return;
        applyChartDefaults();
        const ctx = document.getElementById("locationChart").getContext("2d");
        if (locationChartInstance) locationChartInstance.destroy();

        locationChartInstance = new Chart(ctx, {
            type: "doughnut",
            data: {
                labels: data.map(d => d.location_name),
                datasets: [{
                    data: data.map(d => d.job_count),
                    backgroundColor: [
                        "rgba(56,189,248,0.8)", "rgba(129,140,248,0.8)",
                        "rgba(52,211,153,0.8)", "rgba(251,146,60,0.8)",
                        "rgba(217,70,239,0.8)", "rgba(96,165,250,0.8)",
                        "rgba(248,113,113,0.8)", "rgba(250,204,21,0.8)",
                    ],
                    borderWidth: 2,
                    borderColor: "rgba(7,13,26,0.8)",
                }],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: {
                    legend: { position: "right", labels: { padding: 14, usePointStyle: true } },
                    tooltip: {
                        backgroundColor: "rgba(7,13,26,0.95)",
                        titleColor: "#38bdf8", bodyColor: "#94a3b8",
                        borderColor: "rgba(56,189,248,0.2)", borderWidth: 1,
                    },
                },
            },
        });
    } catch (err) { console.error("Location chart error:", err); }
}

async function loadSkillsDemandChart() {
    try {
        const res = await fetch(`${API_URL}/stats/skills?top_n=15`);
        if (!res.ok) return;
        const body = await res.json();
        const data = Array.isArray(body.data) ? body.data : (Array.isArray(body) ? body : []);
        if (!data.length) return;
        applyChartDefaults();
        const ctx = document.getElementById("skillsChart").getContext("2d");
        if (skillsChartInstance) skillsChartInstance.destroy();

        skillsChartInstance = new Chart(ctx, {
            type: "bar",
            data: {
                labels: data.map(d => d.skill_name),
                datasets: [{
                    label: "Số lượng job yêu cầu",
                    data: data.map(d => d.job_count),
                    backgroundColor: data.map((_, i) =>
                        `hsla(${190 + i * 12}, 80%, 60%, 0.75)`),
                    borderRadius: 5,
                    borderSkipped: false,
                }],
            },
            options: {
                indexAxis: "y",
                responsive: true, maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: "rgba(7,13,26,0.95)",
                        titleColor: "#38bdf8", bodyColor: "#94a3b8",
                        borderColor: "rgba(56,189,248,0.2)", borderWidth: 1,
                    },
                },
                scales: {
                    x: { grid: { color: "rgba(255,255,255,0.04)" }, beginAtZero: true },
                    y: { grid: { display: false } },
                },
            },
        });
    } catch (err) { console.error("Skills chart error:", err); }
}
