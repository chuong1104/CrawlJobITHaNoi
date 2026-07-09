// src/api/static/app.js
const API_URL = ''; // Relative path queries

let currentPage = 1;
let totalPages = 1;

// Initialize on DOM load
document.addEventListener("DOMContentLoaded", () => {
    loadSummaryStats();
    loadJobs();

    // Event listeners
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

    // Add listeners for all filter elements
    document.getElementById("filter-location").addEventListener("change", () => {
        currentPage = 1;
        loadJobs();
    });

    document.getElementById("filter-salary").addEventListener("change", () => {
        currentPage = 1;
        loadJobs();
    });

    document.getElementById("filter-experience").addEventListener("change", () => {
        currentPage = 1;
        loadJobs();
    });

    document.getElementById("filter-source").addEventListener("change", () => {
        currentPage = 1;
        loadJobs();
    });

    document.getElementById("filter-sort").addEventListener("change", () => {
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

    // Realtime update stats and jobs every 30 seconds
    setInterval(() => {
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
        document.getElementById("stat-total-companies").innerText = stats.total_companies.toLocaleString();

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
    const salaryVal = document.getElementById("filter-salary").value;
    const experienceVal = document.getElementById("filter-experience").value;
    const sourceVal = document.getElementById("filter-source").value;
    const sortVal = document.getElementById("filter-sort").value;
    
    let url = `${API_URL}/api/v1/jobs?page=${currentPage}&limit=10`;
    if (searchVal) url += `&search=${encodeURIComponent(searchVal)}`;
    if (locationVal) url += `&location=${encodeURIComponent(locationVal)}`;
    if (salaryVal) url += `&salary=${encodeURIComponent(salaryVal)}`;
    if (experienceVal) url += `&experience=${encodeURIComponent(experienceVal)}`;
    if (sourceVal) url += `&source=${encodeURIComponent(sourceVal)}`;
    if (sortVal) url += `&sort=${encodeURIComponent(sortVal)}`;

    try {
        const res = await fetch(url);
        const result = await res.json();

        renderJobsList(result.data);
        updatePagination(result.pagination);
    } catch (err) {
        console.error("Lỗi khi load danh sách jobs:", err);
    }
}

function getDeadlineInfo(job) {
    if (job.is_expired) {
        return `<span class="deadline-badge expired">🔴 Hết hạn</span>`;
    }
    if (!job.deadline_raw || job.deadline_raw === 'NaN') {
        return `<span class="deadline-badge">⏳ Thỏa thuận</span>`;
    }
    return `<span class="deadline-badge active">🟢 ${job.deadline_raw}</span>`;
}

function renderJobsList(jobs) {
    const container = document.getElementById("jobs-container");
    document.getElementById("results-count").innerText = jobs.length;
    
    if (jobs.length === 0) {
        container.innerHTML = `<p style="padding: 20px; font-style: italic; color: #94a3b8;">Không tìm thấy công việc nào phù hợp.</p>`;
        return;
    }

    container.innerHTML = jobs.map(job => {
        const sourceLower = (job.source_name || 'default').toLowerCase();
        return `
        <div class="job-card" onclick="loadJobDetail(${job.job_id}, this)">
            <div class="job-card-header">
                <h4>${job.title_clean}</h4>
                <span class="badge-source badge-${sourceLower}">${job.source_name || 'Tuyển dụng'}</span>
            </div>
            <div class="company">${job.company_display_name}</div>
            <div class="job-card-details">
                <span>
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M15 10.5a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
                        <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1 1 15 0Z" />
                    </svg>
                    ${job.location_clean || 'Hà Nội'}
                </span>
                <span>
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M12 6v12m-3-2.818.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                    </svg>
                    ${job.salary_raw || 'Thỏa thuận'}
                </span>
                <span>
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M20.25 14.15v4.25c0 .621-.504 1.125-1.125 1.125H4.875c-.621 0-1.125-.504-1.125-1.125v-4.25m16.5 0a2.25 2.25 0 0 0-2.25-2.25H5.625a2.25 2.25 0 0 0-2.25 2.25m16.5 0v-2.25A2.25 2.25 0 0 0 18 7.5H6A2.25 2.25 0 0 0 3.75 9.75v2.25A2.25 2.25 0 0 0 6 14.25h12a2.25 2.25 0 0 0 2.25-2.25ZM12 10.5v3.75m-3.75-3.75h7.5" />
                    </svg>
                    ${job.experience_raw || 'Không yêu cầu'}
                </span>
                <span>
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                    </svg>
                    ${getDeadlineInfo(job)}
                </span>
            </div>
        </div>
        `;
    }).join("");
}

function updatePagination(pagination) {
    currentPage = pagination.page;
    totalPages = pagination.total_pages;

    document.getElementById("page-num").innerText = `Trang ${currentPage} / ${totalPages || 1}`;
    document.getElementById("prev-btn").disabled = currentPage <= 1;
    document.getElementById("next-btn").disabled = currentPage >= totalPages;
}

function formatDescription(desc) {
    if (!desc) return 'Không có mô tả chi tiết.';
    
    // Replace standard section headings with stylized titles only when they stand alone on a line
    let formatted = desc
        .replace(/(?:^|\n)(?:Mô tả công việc|Job Description|MÔ TẢ CÔNG VIỆC)[:\-]?\s*(?=\n|$)/gi, '\n<h4 class="section-title">📋 Mô tả công việc</h4>')
        .replace(/(?:^|\n)(?:Yêu cầu công việc|Yêu cầu ứng viên|Yêu cầu tuyển dụng|Yêu cầu|Requirements|YÊU CẦU CÔNG VIỆC)[:\-]?\s*(?=\n|$)/gi, '\n<h4 class="section-title">🎯 Yêu cầu ứng viên</h4>')
        .replace(/(?:^|\n)(?:Quyền lợi được hưởng|Quyền lợi|Benefits|QUYỀN LỢI ĐƯỢC HƯỞNG)[:\-]?\s*(?=\n|$)/gi, '\n<h4 class="section-title">💎 Quyền lợi được hưởng</h4>')
        .replace(/(?:^|\n)(?:Cách thức ứng tuyển|Ứng tuyển)[:\-]?\s*(?=\n|$)/gi, '\n<h4 class="section-title">✉️ Cách thức ứng tuyển</h4>');
    
    // Split and format bullet points
    let lines = formatted.split('\n');
    let processedLines = lines.map(line => {
        let trimmed = line.trim();
        if (trimmed.startsWith('-') || trimmed.startsWith('+') || trimmed.startsWith('*') || trimmed.startsWith('•')) {
            let cleanLine = trimmed.replace(/^[\-\+\*•]\s*/, '');
            return `<li class="desc-bullet">${cleanLine}</li>`;
        }
        if (trimmed.startsWith('<h4')) {
            return trimmed;
        }
        if (trimmed === '') {
            return '';
        }
        return `<p class="desc-text">${trimmed}</p>`;
    });
    
    return processedLines.join('\n');
}

async function loadJobDetail(jobId, element) {
    // Select active card class
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
        const firstLetter = (job.company_name || 'C').charAt(0).toUpperCase();

        // Extract active card detail badges for matching tags
        const locationText = element ? element.querySelector(".job-card-details span:nth-child(1)").innerText.trim() : "Hà Nội";
        const salaryText = element ? element.querySelector(".job-card-details span:nth-child(2)").innerText.trim() : "Thỏa thuận";
        const experienceText = element ? element.querySelector(".job-card-details span:nth-child(3)").innerText.trim() : "Không yêu cầu";

        const deadlineTag = job.is_expired 
            ? `<div class="detail-tag expired-tag">🔴 Đã hết hạn</div>`
            : `<div class="detail-tag active-tag">🟢 Hạn nộp: ${job.deadline_raw || 'Liên hệ'}</div>`;

        detailPane.innerHTML = `
            <div class="job-detail-content">
                <div class="detail-header">
                    <div class="company-logo-placeholder">${firstLetter}</div>
                    <div class="detail-title-block">
                        <h3>${job.title_clean}</h3>
                        <div class="company">${job.company_name}</div>
                    </div>
                </div>
                
                <div class="detail-tags-row">
                    <div class="detail-tag">📍 ${locationText}</div>
                    <div class="detail-tag">💰 ${salaryText}</div>
                    <div class="detail-tag">💼 ${experienceText}</div>
                    ${deadlineTag}
                </div>

                <hr class="detail-divider">
                <div class="desc">${formatDescription(job.description)}</div>
                
                <div class="apply-container">
                    <a href="${job.canonical_url}" target="_blank" class="apply-btn">Ứng Tuyển Ngay ➔</a>
                </div>
            </div>
        `;
    } catch (err) {
        console.error("Lỗi khi load chi tiết công việc:", err);
        detailPane.innerHTML = `<div class="detail-placeholder"><p>Lỗi kết nối máy chủ.</p></div>`;
    }
}

