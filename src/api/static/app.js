// JobITVN - giao diện danh sách việc làm
const API_URL = "";

let currentPage = 1;
let pageSize = 10;
let totalPages = 1;
let searchTimer = null;
let requestSeq = 0; // bỏ qua phản hồi cũ khi người dùng gõ/lọc nhanh

const salaryChart = { inst: null };
const locationChart = { inst: null };
const skillsChart = { inst: null };

// Cache trong bộ nhớ (60s) để chuyển trang đã xem không phải gọi lại API
const ramCache = new Map();
const CACHE_MS = 60000;

// ---------- Tiện ích ----------
function $(id) { return document.getElementById(id); }

// Màn hình đủ lớn: giao diện vừa một khung nhìn, danh sách/chi tiết cuộn bên trong
function isFit() {
    return window.matchMedia("(min-width: 961px) and (min-height: 640px)").matches;
}

function esc(s) {
    return String(s == null ? "" : s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function fmt(n) {
    if (n === null || n === undefined || n === "") return "0";
    return n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

function timeAgo(dateStr) {
    if (!dateStr) return "";
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return "";
    const sec = Math.floor((Date.now() - d.getTime()) / 1000);
    if (sec < 60) return "vừa cập nhật";
    const min = Math.floor(sec / 60);
    if (min < 60) return min + " phút trước";
    const hr = Math.floor(min / 60);
    if (hr < 24) return hr + " giờ trước";
    const day = Math.floor(hr / 24);
    if (day === 1) return "hôm qua";
    if (day < 7) return day + " ngày trước";
    if (day < 30) return Math.floor(day / 7) + " tuần trước";
    return d.toLocaleDateString("vi-VN");
}

function deadlineInfo(job) {
    const r = job.remaining_days;
    const has = r !== null && r !== undefined;
    if (job.is_expired) {
        const n = has ? Math.abs(r) : 0;
        return { cls: "dl-expired", text: n > 0 ? "Hết hạn " + n + " ngày trước" : "Đã hết hạn", expired: true };
    }
    if (has) {
        if (r === 0) return { cls: "dl-urgent", text: "Hết hạn hôm nay", expired: false };
        if (r <= 7) return { cls: "dl-urgent", text: "Còn " + r + " ngày", expired: false };
        return { cls: "dl-ok", text: "Còn " + r + " ngày", expired: false };
    }
    if (job.deadline_raw) return { cls: "dl-ok", text: "Hạn: " + job.deadline_raw, expired: false };
    return { cls: "dl-none", text: "Không ghi hạn", expired: false };
}

// Escape trước rồi mới đánh dấu từ khóa, tránh chèn HTML từ dữ liệu cào
function highlight(text, query) {
    const safe = esc(text);
    if (!query) return safe;
    const words = query.trim().split(/\s+/).filter(Boolean)
        .map(w => esc(w).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    if (!words.length) return safe;
    try {
        return safe.replace(new RegExp("(" + words.join("|") + ")", "gi"), "<mark>$1</mark>");
    } catch (e) {
        return safe;
    }
}

function setText(id, value) {
    const el = $(id);
    if (el) el.textContent = value;
}

// ---------- Khởi tạo ----------
document.addEventListener("DOMContentLoaded", () => {
    // Chuyển tab
    document.querySelectorAll(".nav-link:not(.external)").forEach(link => {
        link.addEventListener("click", e => {
            e.preventDefault();
            const target = link.getAttribute("data-target");
            document.querySelectorAll(".nav-link:not(.external)").forEach(n => n.classList.remove("active"));
            link.classList.add("active");
            document.querySelectorAll(".tab-content").forEach(c => {
                c.classList.remove("active");
                c.classList.add("hidden");
            });
            const tab = $(target);
            tab.classList.remove("hidden");
            tab.classList.add("active");
            if (target === "analytics-tab") loadAnalytics();
        });
    });

    // Bật/tắt bộ lọc
    $("toggle-filter-btn").addEventListener("click", () => {
        $("advanced-filters").classList.toggle("hidden");
    });

    // Ô tìm kiếm (chờ 350ms sau khi ngừng gõ)
    const input = $("search-input");
    const clearBtn = $("search-clear-btn");
    const syncClear = () => clearBtn.classList.toggle("hidden", input.value.trim() === "");

    input.addEventListener("input", () => {
        syncClear();
        document.querySelectorAll(".search-chip").forEach(c => c.classList.remove("active"));
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => { currentPage = 1; loadJobs(); }, 350);
    });
    input.addEventListener("keypress", e => {
        if (e.key === "Enter") {
            clearTimeout(searchTimer);
            currentPage = 1;
            loadJobs();
        }
    });
    clearBtn.addEventListener("click", () => {
        input.value = "";
        syncClear();
        document.querySelectorAll(".search-chip").forEach(c => c.classList.remove("active"));
        currentPage = 1;
        loadJobs();
    });
    $("search-btn").addEventListener("click", () => {
        clearTimeout(searchTimer);
        currentPage = 1;
        loadJobs();
    });

    // Gợi ý từ khóa
    document.querySelectorAll(".search-chip").forEach(chip => {
        chip.addEventListener("click", () => {
            input.value = chip.getAttribute("data-query");
            syncClear();
            document.querySelectorAll(".search-chip").forEach(c => c.classList.remove("active"));
            chip.classList.add("active");
            currentPage = 1;
            loadJobs();
        });
    });

    // Bộ lọc
    ["filter-status", "filter-location", "filter-salary", "filter-experience", "filter-source", "filter-sort"].forEach(id => {
        $(id).addEventListener("change", () => { currentPage = 1; loadJobs(); });
    });

    // Phân trang
    $("page-size-select").addEventListener("change", e => {
        pageSize = parseInt(e.target.value, 10) || 10;
        currentPage = 1;
        loadJobs();
    });
    $("first-btn").addEventListener("click", () => goPage(1));
    $("prev-btn").addEventListener("click", () => goPage(currentPage - 1));
    $("next-btn").addEventListener("click", () => goPage(currentPage + 1));
    $("last-btn").addEventListener("click", () => goPage(totalPages));

    const jumpInput = $("jump-page-input");
    const jump = () => goPage(parseInt(jumpInput.value, 10));
    $("jump-page-btn").addEventListener("click", jump);
    jumpInput.addEventListener("keypress", e => { if (e.key === "Enter") jump(); });

    loadKPIs();
    loadJobs();
});

function goPage(p) {
    if (!p || p < 1 || p > totalPages || p === currentPage) return;
    currentPage = p;
    loadJobs();
    const top = $("jobs-container");
    if (top) {
        top.scrollTop = 0;
        if (!isFit()) top.scrollIntoView({ block: "start" });
    }
}

// ---------- Số liệu tổng quan ----------
function renderKPIs(d) {
    if (!d) return;
    setText("stat-total-jobs", fmt(d.total_jobs));
    setText("stat-new-jobs-sub", "+" + fmt(d.new_jobs_7d || 0));

    const avg = d.average_salary_million;
    setText("stat-avg-salary", avg && avg !== "N/A" ? avg : "N/A");
    setText("stat-median-salary", d.median_salary && d.median_salary !== "0" ? d.median_salary : "N/A");

    setText("stat-total-companies", fmt(d.total_companies));
    setText("stat-disclosure-rate", parseFloat(d.disclosure_rate || 0).toFixed(1) + "%");
    setText("stat-fresher-jobs", fmt(d.fresher_jobs));

    const box = $("stat-top-skills");
    if (box && Array.isArray(d.top_skills)) {
        box.innerHTML = d.top_skills.slice(0, 10).map(s => {
            const name = typeof s === "object" ? s.name : s;
            const count = typeof s === "object" ? s.count : null;
            return '<span class="tag">' + esc(name) + (count ? "<b>" + fmt(count) + "</b>" : "") + "</span>";
        }).join("");
    }
}

async function loadKPIs() {
    // Hiện ngay số liệu lần trước (nếu có), sau đó cập nhật bằng dữ liệu mới
    try {
        const stored = localStorage.getItem("jobitvn_kpis");
        if (stored) renderKPIs(JSON.parse(stored));
    } catch (e) { /* bỏ qua */ }

    try {
        const res = await fetch(API_URL + "/stats/kpi");
        if (!res.ok) return;
        const d = await res.json();
        renderKPIs(d);
        try { localStorage.setItem("jobitvn_kpis", JSON.stringify(d)); } catch (e) { /* bỏ qua */ }
    } catch (err) {
        console.error("KPI load error:", err);
    }
}

// ---------- Danh sách việc làm ----------
function currentQuery() {
    return {
        search: $("search-input").value.trim(),
        status: $("filter-status").value,
        location: $("filter-location").value,
        salary: $("filter-salary").value,
        experience: $("filter-experience").value,
        source: $("filter-source").value,
        sort: $("filter-sort").value,
    };
}

async function loadJobs() {
    const q = currentQuery();
    let url = API_URL + "/jobs?page=" + currentPage + "&limit=" + pageSize;
    ["search", "status", "location", "salary", "experience", "source", "sort"].forEach(k => {
        if (q[k]) url += "&" + k + "=" + encodeURIComponent(q[k]);
    });

    const container = $("jobs-container");
    const seq = ++requestSeq;

    const cached = ramCache.get(url);
    if (cached && Date.now() - cached.t < CACHE_MS) {
        applyJobs(cached.data, q.search, container);
        return;
    }

    // Trang đầu mặc định: hiện bản lưu của lần trước trong lúc chờ API
    const isDefault = currentPage === 1 && !q.search && q.status === "active" && !q.location &&
        !q.salary && !q.experience && !q.source && q.sort === "newest" && pageSize === 10;
    let shownStale = false;
    if (isDefault && container.children.length === 0) {
        try {
            const stored = sessionStorage.getItem("jobitvn_jobs_p1");
            if (stored) { applyJobs(JSON.parse(stored), "", container); shownStale = true; }
        } catch (e) { /* bỏ qua */ }
    }
    if (!shownStale && container.children.length === 0) {
        container.innerHTML = '<div class="loading">Đang tải...</div>';
    }

    try {
        const res = await fetch(url);
        const d = await res.json();
        if (!res.ok) throw new Error(d.detail || "Lỗi máy chủ " + res.status);

        ramCache.set(url, { data: d, t: Date.now() });
        if (isDefault) {
            try { sessionStorage.setItem("jobitvn_jobs_p1", JSON.stringify(d)); } catch (e) { /* bỏ qua */ }
        }
        if (seq !== requestSeq) return; // đã có yêu cầu mới hơn
        applyJobs(d, q.search, container);
    } catch (err) {
        console.error("Jobs load error:", err);
        if (seq !== requestSeq) return;
        container.innerHTML = '<div class="empty">Không tải được dữ liệu: ' + esc(err.message || "thử lại sau") + "</div>";
    }
}

function applyJobs(d, search, container) {
    const jobs = Array.isArray(d.data) ? d.data : (Array.isArray(d) ? d : []);
    const total = d.total != null ? d.total : jobs.length;
    const page = d.page || currentPage;
    totalPages = d.total_pages || Math.max(1, Math.ceil(total / pageSize));

    setText("results-count", fmt(total) + " kết quả");
    renderJobs(jobs, container, search);
    renderPager(page, totalPages);
}

function renderJobs(jobs, container, query) {
    if (!jobs.length) {
        container.innerHTML = '<div class="empty">Không có việc làm nào khớp với từ khóa và bộ lọc.</div>';
        return;
    }

    // Dựng một lần bằng chuỗi HTML rồi gán một lần (nhanh hơn tạo từng node)
    const html = jobs.map(job => {
        const dl = deadlineInfo(job);
        const title = job.title_clean || job.job_title || "Không có tiêu đề";
        const company = job.company_display_name || job.company_name || "";
        const ago = timeAgo(job.last_seen_at || job.crawled_at);
        const meta = [job.location_clean || "Hà Nội", job.salary_raw || "Thỏa thuận", job.experience_raw || "Không yêu cầu"];
        const id = job.job_id || job.id;

        return '<div class="job-card' + (dl.expired ? " is-expired" : "") + '" data-id="' + esc(id) + '">' +
            '<div class="job-title">' + highlight(title, query) + "</div>" +
            (company ? '<div class="job-company">' + highlight(company, query) + "</div>" : "") +
            '<div class="job-meta">' + meta.map(esc).join(" · ") + "</div>" +
            '<div class="job-foot"><span><span class="' + dl.cls + '">' + esc(dl.text) + "</span>" +
            (ago ? " · " + esc(ago) : "") + "</span>" +
            '<span class="src">' + esc(job.source_name || "") + "</span></div>" +
            "</div>";
    }).join("");

    container.innerHTML = html;
}

// Một listener cho cả danh sách thay vì mỗi thẻ một listener
document.addEventListener("click", e => {
    const card = e.target.closest && e.target.closest(".job-card");
    if (!card || !card.dataset.id) return;
    document.querySelectorAll(".job-card.active").forEach(c => c.classList.remove("active"));
    card.classList.add("active");
    loadJobDetail(card.dataset.id);
});

function renderPager(page, max) {
    totalPages = max;
    $("first-btn").disabled = page <= 1;
    $("prev-btn").disabled = page <= 1;
    $("next-btn").disabled = page >= max;
    $("last-btn").disabled = page >= max;

    const jump = $("jump-page-input");
    jump.max = max;
    jump.value = page;

    let pages = [];
    if (max <= 5) {
        for (let i = 1; i <= max; i++) pages.push(i);
    } else {
        pages.push(1);
        if (page > 3) pages.push("...");
        for (let i = Math.max(2, page - 1); i <= Math.min(max - 1, page + 1); i++) pages.push(i);
        if (page < max - 2) pages.push("...");
        pages.push(max);
    }

    const box = $("page-numbers");
    box.innerHTML = pages.map(p => p === "..."
        ? '<span class="page-ellipsis">…</span>'
        : '<button type="button" class="pg-btn' + (p === page ? " active" : "") + '" data-page="' + p + '">' + p + "</button>"
    ).join("");
    box.querySelectorAll("[data-page]").forEach(b => {
        b.addEventListener("click", () => goPage(parseInt(b.dataset.page, 10)));
    });
}

// ---------- Chi tiết việc làm ----------
async function loadJobDetail(jobId) {
    const pane = $("detail-pane");
    pane.innerHTML = '<p class="detail-empty">Đang tải...</p>';

    try {
        const res = await fetch(API_URL + "/jobs/" + encodeURIComponent(jobId));
        const job = await res.json();
        if (!res.ok) throw new Error(job.detail || "Lỗi máy chủ");

        const min = job.experience_min_years;
        const max = job.experience_max_years;
        const has = v => v !== null && v !== undefined;
        let exp = "Không yêu cầu";
        if (has(min) && has(max)) exp = min === max ? (min > 0 ? min + " năm" : "Dưới 1 năm") : min + " - " + max + " năm";
        else if (has(min)) exp = "Từ " + min + " năm";
        else if (has(max)) exp = "Đến " + max + " năm";

        const dl = deadlineInfo(job);
        const deadlineText = job.deadline_raw ||
            (job.deadline_date ? new Date(job.deadline_date).toLocaleDateString("vi-VN") : "Không ghi hạn");

        let noteCls = "note-ok";
        let noteText = "Đang nhận hồ sơ. Hạn nộp: " + deadlineText;
        if (dl.expired) {
            noteCls = "note-expired";
            noteText = "Tin đã hết hạn (" + deadlineText + "). Giữ lại để tham khảo yêu cầu và mức lương.";
        } else if (has(job.remaining_days) && job.remaining_days <= 3) {
            noteCls = "note-urgent";
            noteText = job.remaining_days === 0 ? "Hôm nay là hạn cuối nộp hồ sơ." : "Chỉ còn " + job.remaining_days + " ngày để nộp hồ sơ.";
        }

        const ago = timeAgo(job.last_seen_at || job.crawled_at);

        pane.innerHTML =
            '<div class="detail-title">' + esc(job.title_clean || "Không có tiêu đề") + "</div>" +
            '<div class="detail-company">' + esc(job.company_name || "") + "</div>" +
            '<div class="note ' + noteCls + '">' + esc(noteText) + "</div>" +
            '<dl class="info">' +
                "<dt>Địa điểm</dt><dd>" + esc(job.location_clean || "Hà Nội") + "</dd>" +
                "<dt>Mức lương</dt><dd>" + esc(job.salary_raw || "Thỏa thuận") + "</dd>" +
                "<dt>Kinh nghiệm</dt><dd>" + esc(exp) + "</dd>" +
                "<dt>Nguồn</dt><dd>" + esc(job.source_name || "") + "</dd>" +
                "<dt>Cập nhật</dt><dd>" + esc(ago || "gần đây") + "</dd>" +
                "<dt>Hạn nộp</dt><dd>" + esc(deadlineText) + "</dd>" +
            "</dl>" +
            '<div class="detail-desc">' + esc(job.description || "Không có mô tả chi tiết.") + "</div>" +
            (job.canonical_url
                ? '<a class="apply' + (dl.expired ? " old" : "") + '" href="' + esc(job.canonical_url) + '" target="_blank" rel="noopener">' +
                  (dl.expired ? "Xem tin gốc (đã hết hạn)" : "Xem tin gốc / ứng tuyển") + "</a>"
                : "");
        pane.scrollTop = 0;
        if (!isFit()) pane.scrollIntoView({ block: "start" });
    } catch (err) {
        console.error("Job detail error:", err);
        pane.innerHTML = '<p class="detail-empty">Không tải được chi tiết. Vui lòng thử lại.</p>';
    }
}

// ---------- Thống kê (Chart.js chỉ tải khi mở tab này) ----------
let chartLibPromise = null;
function ensureChartLib() {
    if (window.Chart) return Promise.resolve();
    if (!chartLibPromise) {
        chartLibPromise = new Promise((resolve, reject) => {
            const s = document.createElement("script");
            s.src = "https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js";
            s.onload = resolve;
            s.onerror = () => { chartLibPromise = null; reject(new Error("Không tải được Chart.js")); };
            document.head.appendChild(s);
        });
    }
    return chartLibPromise;
}

async function loadAnalytics() {
    try {
        await ensureChartLib();
    } catch (e) {
        console.error(e);
        return;
    }
    Chart.defaults.color = "#6a6a64";
    Chart.defaults.font.family = '"Segoe UI", Tahoma, Arial, sans-serif';
    Chart.defaults.font.size = 12;
    Chart.defaults.animation = false;

    await Promise.all([drawSalary(), drawLocation(), drawSkills()]);
}

const GRID = { color: "#e6e6e1" };
const PALETTE = ["#1f5f9e", "#c9772b", "#4f8a5b", "#8a5a9e", "#b8453f", "#5f8aa8", "#a89a3a", "#7a7a72"];

async function drawSalary() {
    try {
        const res = await fetch(API_URL + "/stats/salary-by-skill");
        if (!res.ok) return;
        const data = await res.json();
        if (!Array.isArray(data)) return;
        if (salaryChart.inst) salaryChart.inst.destroy();

        salaryChart.inst = new Chart($("salaryChart").getContext("2d"), {
            type: "bar",
            data: {
                labels: data.map(d => d.skill_name),
                datasets: [
                    { label: "Lương thấp nhất TB", data: data.map(d => (d.avg_salary_min_vnd || 0) / 1e6), backgroundColor: "#1f5f9e" },
                    { label: "Lương cao nhất", data: data.map(d => (d.max_salary_max_vnd || 0) / 1e6), backgroundColor: "#a9bfd6" },
                ],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { tooltip: { callbacks: { label: c => " " + c.dataset.label + ": " + c.parsed.y.toFixed(1) + " triệu" } } },
                scales: { x: { grid: GRID, ticks: { maxRotation: 35 } }, y: { beginAtZero: true, grid: GRID } },
            },
        });
    } catch (err) { console.error("Salary chart error:", err); }
}

async function drawLocation() {
    try {
        const res = await fetch(API_URL + "/stats/locations?top_n=8");
        if (!res.ok) return;
        const body = await res.json();
        const data = Array.isArray(body.data) ? body.data : (Array.isArray(body) ? body : []);
        if (!data.length) return;
        if (locationChart.inst) locationChart.inst.destroy();

        locationChart.inst = new Chart($("locationChart").getContext("2d"), {
            type: "doughnut",
            data: {
                labels: data.map(d => d.location_name),
                datasets: [{ data: data.map(d => d.job_count), backgroundColor: PALETTE, borderColor: "#fff", borderWidth: 2 }],
            },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "right" } } },
        });
    } catch (err) { console.error("Location chart error:", err); }
}

async function drawSkills() {
    try {
        const res = await fetch(API_URL + "/stats/skills?top_n=15");
        if (!res.ok) return;
        const body = await res.json();
        const data = Array.isArray(body.data) ? body.data : (Array.isArray(body) ? body : []);
        if (!data.length) return;
        if (skillsChart.inst) skillsChart.inst.destroy();

        skillsChart.inst = new Chart($("skillsChart").getContext("2d"), {
            type: "bar",
            data: {
                labels: data.map(d => d.skill_name),
                datasets: [{ label: "Số tin yêu cầu", data: data.map(d => d.job_count), backgroundColor: "#1f5f9e" }],
            },
            options: {
                indexAxis: "y",
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: { x: { grid: GRID, beginAtZero: true }, y: { grid: { display: false } } },
            },
        });
    } catch (err) { console.error("Skills chart error:", err); }
}
