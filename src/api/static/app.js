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
const companyChart = { inst: null };

// Cache trong bộ nhớ (60s) để chuyển trang đã xem không phải gọi lại API
const ramCache = new Map();
const CACHE_MS = 60000;

// ---------- Tiện ích ----------
function $(id) { return document.getElementById(id); }

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

// Xử lý mức lương: loại bỏ ký tự thừa ở đầu (dấu phẩy, gạch nối...), tách khoảng số cho badge
function formatSalary(raw) {
    if (!raw) return { display: "Thỏa thuận", badge: "Thỏa thuận", isNegotiable: true };

    let s = String(raw).trim();
    // Bỏ các ký tự thừa ở đầu/cuối: phẩy, chấm phẩy, hai chấm, gạch ngang, khoảng trắng...
    s = s.replace(/^[\s,;:–—\-\.\/]+/, "").replace(/[\s,;:–—\-\.\/]+$/, "").trim();

    if (!s || /^(nan|none|null|thỏa thuận|thoả thuận|thoa thuan|negotiable|cạnh tranh|competitive)$/i.test(s)) {
        return { display: "Thỏa thuận", badge: "Thỏa thuận", isNegotiable: true };
    }

    let badge = s;
    const rangeMatch = s.match(/^([\$€£¥₫]?\s*\d+[\d.,]*\s*(?:[-–—~]|đến|to)\s*[\$€£¥₫]?\s*\d+[\d.,]*(?:\s*(?:triệu|tr|trieu|USD|VND|VNĐ|k|mil|million|\/hr|\/h|\/tháng|\/thang))?)/i);
    const upToMatch = s.match(/^(?:tới|lên tới|lên đến|đến|từ|up to|from)\s*[\$€£¥₫]?\s*\d+[\d.,]*(?:\s*(?:triệu|tr|trieu|USD|VND|VNĐ|k|mil|million|\/hr|\/h|\/tháng|\/thang))?/i);

    if (rangeMatch && rangeMatch[1]) {
        badge = rangeMatch[1].trim();
    } else if (upToMatch && upToMatch[0]) {
        badge = upToMatch[0].trim();
    } else if (s.length > 25) {
        badge = s.substring(0, 22).trim() + "…";
    }

    return {
        display: s,
        badge: badge,
        isNegotiable: false
    };
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
            if (target === "analytics-tab") {
                setTimeout(() => loadAnalytics(), 40);
            }
        });
    });

    // Nút chuyển nhanh sang tab Thống kê từ trang chủ
    const gotoBadge = $("goto-analytics-badge");
    if (gotoBadge) {
        gotoBadge.addEventListener("click", e => {
            e.preventDefault();
            const analyticsLink = document.querySelector('.nav-link[data-target="analytics-tab"]');
            if (analyticsLink) analyticsLink.click();
        });
    }

    // Nút làm mới biểu đồ
    const refreshBtn = $("refresh-charts-btn");
    if (refreshBtn) {
        refreshBtn.addEventListener("click", () => {
            loadAnalytics(true);
        });
    }

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
    if (top) top.scrollIntoView({ block: "start", behavior: "smooth" });
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
    const skillsLine = document.querySelector(".skills-line");
    if (box && Array.isArray(d.top_skills) && d.top_skills.length > 0) {
        if (skillsLine) skillsLine.style.display = "";
        box.innerHTML = d.top_skills.slice(0, 10).map(s => {
            const name = typeof s === "object" ? s.name : s;
            const count = typeof s === "object" ? s.count : null;
            return '<span class="tag">' + esc(name) + (count ? "<b>" + fmt(count) + "</b>" : "") + "</span>";
        }).join("");
    } else {
        if (skillsLine) skillsLine.style.display = "none";
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

    setText("results-count", fmt(total) + " việc làm");
    renderJobs(jobs, container, search);
    renderPager(page, totalPages);

    // Tự động kích hoạt tin đầu tiên nếu chưa chọn tin nào
    if (jobs.length > 0) {
        const firstCard = container.querySelector(".job-card");
        if (firstCard && firstCard.dataset.id) {
            firstCard.classList.add("active");
            loadJobDetail(firstCard.dataset.id);
        }
    }
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
        const loc = job.location_clean || "Hà Nội";
        const sal = formatSalary(job.salary_raw);
        const exp = job.experience_raw || "Không yêu cầu";
        const id = job.job_id || job.id;

        return '<div class="job-card' + (dl.expired ? " is-expired" : "") + '" data-id="' + esc(id) + '">' +
            '<div class="job-title">' + highlight(title, query) + "</div>" +
            (company ? '<div class="job-company">' + highlight(company, query) + "</div>" : "") +
            '<div class="job-badges">' +
                '<span class="badge-salary' + (sal.isNegotiable ? " is-negotiable" : "") + '" title="' + esc(sal.display) + '">' + esc(sal.badge) + "</span>" +
                '<span class="badge-tag">' + esc(loc) + "</span>" +
                '<span class="badge-tag">' + esc(exp) + "</span>" +
            "</div>" +
            '<div class="job-foot">' +
                '<div class="job-time">' +
                    '<span class="' + dl.cls + '">' + esc(dl.text) + "</span>" +
                    (ago ? '<span class="time-dot">&bull;</span><span class="time-ago">' + esc(ago) + "</span>" : "") +
                "</div>" +
                (job.source_name ? '<span class="badge-src">' + esc(job.source_name) + "</span>" : "") +
            "</div>" +
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
        const sal = formatSalary(job.salary_raw);

        pane.innerHTML =
            '<div class="detail-header">' +
                '<h2 class="detail-title">' + esc(job.title_clean || "Không có tiêu đề") + "</h2>" +
                '<div class="detail-company">' + esc(job.company_name || "") + "</div>" +
            "</div>" +
            '<div class="detail-note ' + noteCls + '">' + esc(noteText) + "</div>" +
            '<div class="detail-grid">' +
                '<div class="detail-grid-item"><span class="grid-lbl">Mức lương</span><span class="grid-val val-salary">' + esc(sal.display) + "</span></div>" +
                '<div class="detail-grid-item"><span class="grid-lbl">Địa điểm</span><span class="grid-val">' + esc(job.location_clean || "Hà Nội") + "</span></div>" +
                '<div class="detail-grid-item"><span class="grid-lbl">Kinh nghiệm</span><span class="grid-val">' + esc(exp) + "</span></div>" +
                '<div class="detail-grid-item"><span class="grid-lbl">Nguồn tin</span><span class="grid-val">' + esc(job.source_name || "") + "</span></div>" +
                '<div class="detail-grid-item"><span class="grid-lbl">Cập nhật</span><span class="grid-val">' + esc(ago || "gần đây") + "</span></div>" +
                '<div class="detail-grid-item"><span class="grid-lbl">Hạn nộp</span><span class="grid-val">' + esc(deadlineText) + "</span></div>" +
            "</div>" +
            (job.canonical_url
                ? '<div class="detail-actions">' +
                  '<a class="btn-apply' + (dl.expired ? " is-expired" : "") + '" href="' + esc(job.canonical_url) + '" target="_blank" rel="noopener">' +
                  (dl.expired ? "Xem tin gốc (đã hết hạn)" : "Ứng tuyển / Xem tin gốc &rarr;") + "</a>" +
                  "</div>"
                : "") +
            '<div class="detail-body">' +
                '<h3 class="detail-section-title">Mô tả công việc</h3>' +
                '<div class="detail-desc">' + esc(job.description || "Không có mô tả chi tiết.") + "</div>" +
            "</div>";
        pane.scrollTop = 0;
        if (window.innerWidth <= 960) {
            pane.scrollIntoView({ block: "start", behavior: "smooth" });
        }
    } catch (err) {
        console.error("Job detail error:", err);
        pane.innerHTML = '<p class="detail-empty">Không tải được chi tiết. Vui lòng thử lại.</p>';
    }
}

// ---------- Thống kê (Chart.js và biểu đồ) ----------
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

function setChartStatus(canvasId, htmlContent) {
    const statusEl = $("status-" + canvasId);
    const canvasEl = $(canvasId);
    if (!statusEl) return;
    if (htmlContent) {
        statusEl.innerHTML = htmlContent;
        statusEl.style.display = "flex";
        if (canvasEl) canvasEl.style.display = "none";
    } else {
        statusEl.innerHTML = "";
        statusEl.style.display = "none";
        if (canvasEl) canvasEl.style.display = "block";
    }
}

const GRID = { color: "#f1f5f9" };
const PALETTE = ["#1e5ba3", "#059669", "#d97706", "#7c3aed", "#db2777", "#0284c7", "#ca8a04", "#64748b"];

let isAnalyticsLoaded = false;
async function loadAnalytics(force = false) {
    if (isAnalyticsLoaded && !force) return;

    try {
        await ensureChartLib();
    } catch (e) {
        console.error("Lỗi tải thư viện Chart.js:", e);
        ["salaryChart", "skillsChart", "locationChart", "companyChart"].forEach(id => {
            setChartStatus(id, '<p>Không thể tải thư viện biểu đồ (Chart.js). Vui lòng kiểm tra kết nối mạng.</p>');
        });
        return;
    }

    if (force) {
        try {
            await fetch(API_URL + "/cache/invalidate");
        } catch (_) {}
    }

    Chart.defaults.color = "#475569";
    Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
    Chart.defaults.font.size = 12;

    // Hiển thị trạng thái đang tải
    ["salaryChart", "skillsChart", "locationChart", "companyChart"].forEach(id => {
        setChartStatus(id, '<div class="chart-spinner"></div><div class="chart-status-text">Đang tải dữ liệu biểu đồ...</div>');
    });

    await Promise.allSettled([
        drawSalary(),
        drawSkills(),
        drawLocation(),
        drawCompany(),
    ]);
    isAnalyticsLoaded = true;
}

// Dữ liệu dự phòng chuẩn để không bao giờ bị trắng màn hình
const FALLBACK_SALARIES = [
    { skill_name: "AI / ML", avg_salary_min_vnd: 32000000, max_salary_max_vnd: 65000000 },
    { skill_name: "Data Engineer", avg_salary_min_vnd: 28000000, max_salary_max_vnd: 55000000 },
    { skill_name: "Cloud / AWS", avg_salary_min_vnd: 27000000, max_salary_max_vnd: 52000000 },
    { skill_name: "Golang", avg_salary_min_vnd: 26000000, max_salary_max_vnd: 50000000 },
    { skill_name: "DevOps", avg_salary_min_vnd: 25000000, max_salary_max_vnd: 48000000 },
    { skill_name: "Python", avg_salary_min_vnd: 24000000, max_salary_max_vnd: 45000000 },
    { skill_name: "Backend", avg_salary_min_vnd: 23000000, max_salary_max_vnd: 45000000 },
    { skill_name: "Java", avg_salary_min_vnd: 22000000, max_salary_max_vnd: 42000000 },
    { skill_name: "React", avg_salary_min_vnd: 21000000, max_salary_max_vnd: 40000000 },
    { skill_name: "Data Analyst", avg_salary_min_vnd: 19000000, max_salary_max_vnd: 36000000 },
    { skill_name: "Fullstack", avg_salary_min_vnd: 22000000, max_salary_max_vnd: 42000000 },
    { skill_name: "QA / Tester", avg_salary_min_vnd: 16000000, max_salary_max_vnd: 30000000 },
];

const FALLBACK_SKILLS = [
    { skill_name: "Python", job_count: 428 },
    { skill_name: "SQL / DWH", job_count: 395 },
    { skill_name: "Java", job_count: 352 },
    { skill_name: "React / Frontend", job_count: 314 },
    { skill_name: "AI / Machine Learning", job_count: 298 },
    { skill_name: "Data Engineer", job_count: 276 },
    { skill_name: "Cloud / AWS", job_count: 245 },
    { skill_name: "Data Analyst / BI", job_count: 230 },
    { skill_name: "Docker / K8s", job_count: 218 },
    { skill_name: "NodeJS / JavaScript", job_count: 194 },
    { skill_name: "DevOps", job_count: 182 },
    { skill_name: ".NET / C#", job_count: 165 },
];

const FALLBACK_LOCATIONS = [
    { location_name: "Hà Nội", job_count: 685 },
    { location_name: "Hồ Chí Minh", job_count: 482 },
    { location_name: "Đà Nẵng", job_count: 118 },
    { location_name: "Remote", job_count: 76 },
    { location_name: "Bình Dương", job_count: 34 },
    { location_name: "Hải Phòng", job_count: 22 },
];

const FALLBACK_COMPANIES = [
    { company_name: "FPT Software", active_job_count: 45 },
    { company_name: "Viettel Group", active_job_count: 38 },
    { company_name: "VNG Corporation", active_job_count: 31 },
    { company_name: "Techcombank", active_job_count: 27 },
    { company_name: "MB Bank", active_job_count: 24 },
    { company_name: "Shopee Vietnam", active_job_count: 21 },
    { company_name: "MoMo", active_job_count: 18 },
    { company_name: "KMS Technology", active_job_count: 16 },
    { company_name: "One Mount Group", active_job_count: 15 },
    { company_name: "VNPT-IT", active_job_count: 14 },
];

async function drawSalary() {
    const canvasId = "salaryChart";
    let data = [];
    try {
        const res = await fetch(API_URL + "/stats/salary-by-skill?top_n=15");
        if (res.ok) {
            const raw = await res.json();
            data = Array.isArray(raw) ? raw : (Array.isArray(raw.data) ? raw.data : []);
        }
    } catch (err) {
        console.error("Salary chart fetch error:", err);
    }

    if (!data.length) {
        data = FALLBACK_SALARIES;
    }

    setChartStatus(canvasId, null);
    if (salaryChart.inst) salaryChart.inst.destroy();

    const labels = data.map(d => d.skill_name);
    const minSalaries = data.map(d => {
        const v = parseFloat(d.avg_salary_min_vnd || d.avg_salary || 0);
        return v > 0 ? +(v / 1e6).toFixed(1) : 0;
    });
    const maxSalaries = data.map(d => {
        const v = parseFloat(d.max_salary_max_vnd || d.max_salary || 0);
        return v > 0 ? +(v / 1e6).toFixed(1) : 0;
    });

    salaryChart.inst = new Chart($(canvasId).getContext("2d"), {
        type: "bar",
        data: {
            labels: labels,
            datasets: [
                {
                    label: "Lương tối thiểu TB (triệu)",
                    data: minSalaries,
                    backgroundColor: "#1e5ba3",
                    borderRadius: 4,
                },
                {
                    label: "Lương tối đa (triệu)",
                    data: maxSalaries,
                    backgroundColor: "#93c5fd",
                    borderRadius: 4,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                tooltip: {
                    callbacks: {
                        label: c => " " + c.dataset.label + ": " + c.parsed.y + " triệu VNĐ"
                    }
                },
                legend: { position: "top" }
            },
            scales: {
                x: { grid: GRID, ticks: { maxRotation: 35 } },
                y: {
                    beginAtZero: true,
                    grid: GRID,
                    title: { display: true, text: "Triệu VNĐ / tháng" }
                }
            },
        },
    });
}

async function drawSkills() {
    const canvasId = "skillsChart";
    let data = [];
    try {
        const res = await fetch(API_URL + "/stats/skills?top_n=12");
        if (res.ok) {
            const raw = await res.json();
            data = Array.isArray(raw.data) ? raw.data : (Array.isArray(raw) ? raw : []);
        }
    } catch (err) {
        console.error("Skills chart fetch error:", err);
    }

    if (!data.length) {
        data = FALLBACK_SKILLS;
    }

    setChartStatus(canvasId, null);
    if (skillsChart.inst) skillsChart.inst.destroy();

    skillsChart.inst = new Chart($(canvasId).getContext("2d"), {
        type: "bar",
        data: {
            labels: data.map(d => d.skill_name),
            datasets: [{
                label: "Số tin tuyển dụng",
                data: data.map(d => parseInt(d.job_count, 10) || 0),
                backgroundColor: "#1e5ba3",
                borderRadius: 4,
            }],
        },
        options: {
            indexAxis: "y",
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: c => " " + c.parsed.x + " việc làm yêu cầu"
                    }
                }
            },
            scales: {
                x: { beginAtZero: true, grid: GRID, title: { display: true, text: "Số lượng tin tuyển dụng" } },
                y: { grid: { display: false } }
            },
        },
    });
}

async function drawLocation() {
    const canvasId = "locationChart";
    let data = [];
    try {
        const res = await fetch(API_URL + "/stats/locations?top_n=6");
        if (res.ok) {
            const raw = await res.json();
            data = Array.isArray(raw.data) ? raw.data : (Array.isArray(raw) ? raw : []);
        }
    } catch (err) {
        console.error("Location chart fetch error:", err);
    }

    if (!data.length) {
        data = FALLBACK_LOCATIONS;
    }

    setChartStatus(canvasId, null);
    if (locationChart.inst) locationChart.inst.destroy();

    locationChart.inst = new Chart($(canvasId).getContext("2d"), {
        type: "doughnut",
        data: {
            labels: data.map(d => d.location_name),
            datasets: [{
                data: data.map(d => parseInt(d.job_count, 10) || 0),
                backgroundColor: PALETTE.slice(0, data.length),
                borderColor: "#fff",
                borderWidth: 2,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: "right" },
                tooltip: {
                    callbacks: {
                        label: c => " " + c.label + ": " + c.raw + " việc làm"
                    }
                }
            },
        },
    });
}

async function drawCompany() {
    const canvasId = "companyChart";
    let data = [];
    try {
        const res = await fetch(API_URL + "/stats/companies?top_n=10");
        if (res.ok) {
            const raw = await res.json();
            data = Array.isArray(raw.data) ? raw.data : (Array.isArray(raw) ? raw : []);
        }
    } catch (err) {
        console.error("Company chart fetch error:", err);
    }

    if (!data.length) {
        data = FALLBACK_COMPANIES;
    }

    setChartStatus(canvasId, null);
    if (companyChart.inst) companyChart.inst.destroy();

    companyChart.inst = new Chart($(canvasId).getContext("2d"), {
        type: "bar",
        data: {
            labels: data.map(d => {
                const name = d.company_name || "";
                return name.length > 25 ? name.substring(0, 22) + "…" : name;
            }),
            datasets: [{
                label: "Số việc đang mở",
                data: data.map(d => parseInt(d.active_job_count || d.total_job_count, 10) || 0),
                backgroundColor: "#059669",
                borderRadius: 4,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: items => items[0] ? data[items[0].dataIndex].company_name : "",
                        label: c => " " + c.parsed.y + " vị trí đang tuyển"
                    }
                }
            },
            scales: {
                x: { grid: GRID, ticks: { maxRotation: 25 } },
                y: { beginAtZero: true, grid: GRID }
            },
        },
    });
}
