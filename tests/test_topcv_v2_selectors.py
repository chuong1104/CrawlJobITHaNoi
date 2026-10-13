"""
test_topcv_v2_selectors.py — Unit test kiểm tra parse_job_detail với HTML TopCV giao diện mới (V2 layout)
"""
from src.extract.topcv import TopCVScraper

SAMPLE_TOPCV_V2_HTML = """
<div class="job-detail__body-left">
    <div class="v2-box-header-job ">
    <div class="container">
        
            <div class="box-header-job ">
                            <div class="box-company-info  company-pro ">
                <a rel="nofollow" class="box-company-info__image" href="https://www.topcv.vn/cong-ty/ngan-hang-shb/199009.html" title="Ngân hàng SHB">
                    <img src="https://cdn-new.topcv.vn/unsafe/60x/https://static.topcv.vn/company_logos/69fc4fb9a9a231778143161.png" alt="Ngân hàng SHB" loading="lazy">
                </a>
                <div class="box-company-info__detail">
                    
                                            <a rel="nofollow" href="https://www.topcv.vn/cong-ty/ngan-hang-shb/199009.html" class="name">Ngân hàng SHB</a>
                                    </div>
            </div>
            <div class="box-header-job__group-top">
                <h1 class="box-header-job__title">
                    <a href="https://www.topcv.vn/tim-viec-lam-ai-engineer" title="Việc làm AI Engineer" class="text-highlight" target="_blank">AI Engineer</a> - <a href="https://www.topcv.vn/tim-viec-lam-du-an" title="Việc làm Dự Án" class="text-highlight" target="_blank">Dự Án</a> CNTT
                    <span class="icon-verified-employer level-five">
<i class="fa-solid fa-circle-check icon-verified-employer-tooltip" data-toggle="tooltip" data-container="body" data-html="true" title="" data-placement="top" data-original-title="verified"></i></span>
                </h1>

                <div class="box-header-job__salary-and-report-salary">
                    <div class="box-header-job__salary">
                        <span class="box-header-job__salary--title">
                            Thoả thuận
                        </span>
                    </div>
                </div>
            </div>

            <div class="box-header-job-list-info">
                <div class="box-header-job-list-info__item">
                    <div class="box-header-job-list-info__item--content list-info__content">
                        <div class=" list-info__content__title">
                            Địa điểm
                        </div>
                        <div class="list-info__content__desc">
                            <span><a href="https://www.topcv.vn/tim-viec-lam-ai-engineer-tai-ha-noi-kl1" title="Việc làm AI Engineer tại Hà Nội" target="_blank">Hà Nội</a></span>
                        </div>
                    </div>
                </div>
                <div class="box-header-job-list-info__item">
                    <div class="box-header-job-list-info__item--content list-info__content">
                        <div class=" list-info__content__title">
                            Kinh nghiệm
                        </div>
                        <div class="list-info__content__desc">
                            4 năm
                        </div>
                    </div>
                </div>
                <div class="box-header-job-list-info__item">
                    <div class="box-header-job-list-info__item--content list-info__content">
                        <div class=" list-info__content__title">
                            Hạn ứng tuyển
                        </div>
                        <div class="list-info__content__desc">
                            28/10/2026
                        </div>
                    </div>
                </div>
            </div>

            <div class="box-group-button-apply box-apply-current">
                <div id="box-save-job-2315254" class="box-save-job box-save-job-2315254  job-notsave ">
                    <button class="btn btn-save save btn-topcv-text-normal btn-topcv-gray btn-save-job" data-id="2315254" data-title="AI Engineer - Dự Án CNTT">
                        <i class="fa-regular fa-heart"></i>
                        <span> Lưu tin </span>
                    </button>
                </div>
            </div>
    </div>
</div>
<div class="job-detail__box--left">
    <div class="box-job-information-detail" id="box-job-information-detail">
        <div class="not-line box-job-information-detail__collapsed content-preview--collapsed">
            <div class="box-job-information-detail-item">
                <div class="box-job-information-detail-item__title">
                    <h2 class="box-job-information-detail-item__title--title">
                        Tổng quan
                    </h2>
                </div>
                <div class="job-tags">
                    <div class="job-tags__group">
                        <h3 class="job-tags__group-name">
                            Yêu cầu:
                        </h3>
                        <div class="job-tags__group-list-tag">
                            <div class="job-tags__group-list-tag-scroll">
                                <a class="item search-from-tag ">4 năm kinh nghiệm chuyên môn</a>
                                <a class="item search-from-tag ">Đại Học trở lên</a>
                            </div>
                        </div>
                    </div>
                    <div class="job-tags__group">
                        <h3 class="job-tags__group-name">
                            Chuyên môn:
                        </h3>
                        <div class="job-tags__group-list-tag">
                            <div class="job-tags__group-list-tag-scroll">
                                <a class="item search-from-tag link" title="AI Engineer">AI Engineer</a>
                                <a class="item search-from-tag link" title="Ngân hàng">Ngân hàng</a>
                                <a class="item search-from-tag link" title="Tài chính">Tài chính</a>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="box-job-information-detail-item">
                <div class="box-job-information-detail-item__title">
                    <h2 class="box-job-information-detail-item__title--title">
                        Mô tả công việc
                    </h2>
                </div>
                <div class="box-job-information-detail-item__text">
                    <p><strong>1. Phát triển và tối ưu giải pháp AI</strong></p>
                    <ul>
                        <li><strong>Xây dựng và tối ưu hóa mô hình:</strong> Tinh chỉnh và tối ưu hóa các mô hình Machine Learning và Deep Learning.</li>
                        <li><strong>Phát triển ứng dụng mô hình ngôn ngữ lớn (LLM) &amp; RAG:</strong> Xây dựng các ứng dụng LLM và RAG.</li>
                    </ul>
                </div>
            </div>

            <div class="box-job-information-detail-item box-job-information-required-candidate">
                <div class="box-job-information-detail-item__title">
                    <h2 class="box-job-information-detail-item__title--title">
                        Yêu cầu ứng viên
                    </h2>
                </div>
                <div class="box-job-information-detail-item__text">
                    <p><strong>1. Trình độ &amp; Kinh nghiệm</strong></p>
                    <ul>
                        <li>Tốt nghiệp đại học chuyên ngành CNTT. Có tối thiểu 4 năm kinh nghiệm AI Engineer.</li>
                        <li>Thành thạo Python, PyTorch, TensorFlow.</li>
                    </ul>
                </div>
            </div>

            <div class="box-job-information-detail-item box-job-information-benefit">
                <div class="box-job-information-detail-item__title">
                    <h2 class="box-job-information-detail-item__title--title">
                        Quyền lợi ứng viên
                    </h2>
                </div>
                <div class="box-job-information-detail-item__text">
                    <p><strong>1. Chế độ đãi ngộ hấp dẫn</strong></p>
                    <ul>
                        <li>Lương hàng tháng cạnh tranh, thưởng cuối năm hấp dẫn.</li>
                        <li>Bảo hiểm SHB care, du lịch 2 lần/năm.</li>
                    </ul>
                </div>
            </div>

            <div class="box-job-information-detail-item box-job-information-address-and-time">
                <div class="box-job-information-detail-item__title">
                    <h2 class="box-job-information-detail-item__title--title">
                        Địa điểm và thời gian
                    </h2>
                </div>
                <div class="box-job-information-address-and-time-list">
                    <div class="box-job-information-address-and-time-list__item">
                        <h3 class="box-job-information-address-and-time-list__item--title">
                            Địa điểm làm việc
                        </h3>
                        <div class="box-job-information-address-and-time-list__item--content">
                            <ul>
                                <li><strong>Hà Nội:</strong> Phường Hai Bà Trưng (Quận Hai Bà Trưng cũ)</li>
                            </ul>
                        </div>
                    </div>
                    <div class="box-job-information-address-and-time-list__item">
                        <h3 class="box-job-information-address-and-time-list__item--title">
                            Thời gian làm việc
                        </h3>
                        <div class="box-job-information-address-and-time-list__item--content">
                            <ul>
                                <li>Thứ 2 - Thứ 6 (từ 08:00 đến 17:00)</li>
                            </ul>
                        </div>
                    </div>
                </div>
                <div class="box-applied-cv">
                    <p>Hạn ứng tuyển: <span class="date">28/10/2026</span></p>
                </div>
            </div>
        </div>
    </div>
</div>
</div>
"""


def test_topcv_v2_parsing():
    scraper = TopCVScraper()
    url = "https://www.topcv.vn/viec-lam/ai-engineer-du-an-cntt/2315254.html"
    
    # 1. Kiểm tra xác thực HTML hợp lệ
    assert scraper._is_valid_html(SAMPLE_TOPCV_V2_HTML, url) is True, "HTML phải được nhận diện là hợp lệ"

    # 2. Bóc tách chi tiết job
    data = scraper.parse_job_detail(SAMPLE_TOPCV_V2_HTML, url)

    # 3. Kiểm tra tiêu đề (Title) KHÔNG bị bỏ qua
    assert data["title"] is not None, "Tiêu đề không được là None"
    assert "AI Engineer - Dự Án CNTT" in data["title"], f"Tiêu đề không chính xác: {data['title']}"
    assert data["company"] == "Ngân hàng SHB", f"Công ty không chính xác: {data['company']}"
    assert data["salary"] == "Thoả thuận", f"Mức lương không chính xác: {data['salary']}"
    assert "Hai Bà Trưng" in data["location"], f"Địa điểm không chính xác: {data['location']}"
    assert data["experience_level"] == "4 năm", f"Kinh nghiệm không chính xác: {data['experience_level']}"
    assert "28/10/2026" in data["job_deadline"], f"Hạn nộp không chính xác: {data['job_deadline']}"
    assert data["job_description"] is not None and len(data["job_description"]) > 20, "Mô tả công việc bị thiếu"
    assert data["requirements"] is not None and len(data["requirements"]) > 20, "Yêu cầu ứng viên bị thiếu"
    assert data["benefits"] is not None and len(data["benefits"]) > 20, "Quyền lợi ứng viên bị thiếu"
    assert "AI Engineer" in data["job_industry"], f"Ngành nghề không chính xác: {data['job_industry']}"
    assert "08:00" in data["job_type"], f"Thời gian làm việc không chính xác: {data['job_type']}"

    print(" Tất cả các bài kiểm tra TopCV V2 parse_job_detail đều THÀNH CÔNG!")
    print(f"-> Title: {data['title']}")
    print(f"-> Company: {data['company']}")
    print(f"-> Salary: {data['salary']}")
    print(f"-> Location: {data['location']}")
    print(f"-> Experience: {data['experience_level']}")
    print(f"-> Deadline: {data['job_deadline']}")
    print(f"-> Working time: {data['job_type']}")
    print(f"-> Industry tags: {data['job_industry']}")


if __name__ == "__main__":
    test_topcv_v2_parsing()
