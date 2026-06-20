# Business Problem

## Project Name

JobITVN Data Platform

A Data Engineering Platform for Intern, Fresher and Entry-Level IT Career Intelligence in Vietnam.

---

# 1. Background

Trong những năm gần đây, số lượng sinh viên theo học các ngành:

* Công nghệ Thông tin
* Khoa học Máy tính
* Kỹ thuật Phần mềm
* Data Science
* Data Engineering
* Trí tuệ Nhân tạo

tăng nhanh tại Việt Nam.

Tuy nhiên, cơ hội việc làm dành riêng cho:

* Intern
* Fresher
* Entry-level
* Không yêu cầu kinh nghiệm

lại phân tán trên nhiều nền tảng tuyển dụng khác nhau.

Người tìm việc thường phải truy cập nhiều website để tìm kiếm cơ hội phù hợp.

Ví dụ:

* ITviec
* TopCV
* VietnamWorks
* CareerViet
* TopDev
* Glints
* JobsGO
* Vieclam24h
* JobOKO
* CareerLink
* YBOX
* Indeed

Mỗi nền tảng có:

* Giao diện khác nhau
* Cách mô tả khác nhau
* Quy chuẩn dữ liệu khác nhau
* Mức độ cập nhật khác nhau

Điều này làm cho việc tìm kiếm cơ hội nghề nghiệp trở nên khó khăn, đặc biệt đối với sinh viên chưa có kinh nghiệm.

---

# 2. Current Problems

## Problem 1: Job Data Is Fragmented

Thông tin tuyển dụng phân tán trên nhiều website.

Ví dụ:

Một vị trí:

Data Engineer Intern

có thể được đăng trên:

* TopCV
* ITviec
* VietnamWorks

Người tìm việc phải tìm kiếm nhiều lần trên từng website.

---

## Problem 2: Duplicate Jobs

Một công việc có thể xuất hiện trên nhiều nền tảng.

Ví dụ:

Company A đăng:

* ITviec
* TopCV
* VietnamWorks

Người dùng nhìn thấy:

3 job khác nhau

Trong thực tế:

1 job duy nhất.

Điều này gây:

* Nhiễu dữ liệu
* Khó thống kê
* Trải nghiệm tìm kiếm kém

---

## Problem 3: Job Lifecycle Is Unclear

Nhiều website:

* Không hiển thị trạng thái hết hạn
* Không xóa job cũ
* Không cập nhật trạng thái đóng tuyển

Người dùng:

* Nộp hồ sơ vào job đã hết hạn
* Tốn thời gian tìm hiểu

---

## Problem 4: Difficult Skill Discovery

Sinh viên thường không biết:

"Tôi muốn làm Data Engineer thì cần học gì?"

Hiện tại dữ liệu kỹ năng nằm trong mô tả công việc dưới dạng văn bản tự do.

Ví dụ:

* SQL
* Python
* Airflow
* Spark
* Power BI

không được chuẩn hóa.

Do đó khó phân tích:

* Kỹ năng phổ biến
* Kỹ năng đang tăng trưởng
* Kỹ năng theo từng nghề

---

## Problem 5: Lack of Career Intelligence

Hiện nay phần lớn website tuyển dụng chỉ cung cấp:

* Danh sách công việc

Nhưng không cung cấp:

* Xu hướng tuyển dụng
* Phân tích kỹ năng
* Phân tích mức lương
* Nhu cầu theo địa phương
* Nhu cầu theo thời gian

---

## Problem 6: Search Quality Is Limited

Người dùng tìm:

ETL

Nhưng nhiều hệ thống không trả về:

* Data Engineer Intern
* Data Pipeline Intern
* BI Intern

Mặc dù thực tế các vị trí này liên quan trực tiếp đến ETL.

---

## Problem 7: No Student-Focused Aggregation

Hầu hết nền tảng tuyển dụng phục vụ:

* Senior
* Mid-level
* Experienced candidates

Trong khi sinh viên cần:

* Intern
* Fresher
* No Experience
* Part-time IT

Một nền tảng chuyên biệt cho nhóm đối tượng này hiện còn hạn chế.

---

# 3. Root Cause Analysis

Nguyên nhân gốc của vấn đề không nằm ở việc thiếu dữ liệu.

Ngược lại:

Dữ liệu đang tồn tại rất nhiều.

Vấn đề nằm ở:

## Data Fragmentation

Dữ liệu nằm rải rác trên nhiều website.

---

## Data Standardization

Mỗi website dùng:

* Schema khác nhau
* Quy tắc khác nhau

---

## Lack of Data Engineering Infrastructure

Không có hệ thống:

* Thu thập
* Chuẩn hóa
* Đồng bộ
* Theo dõi vòng đời

dữ liệu tuyển dụng ở quy mô lớn.

---

## Lack of Analytical Layer

Dữ liệu chỉ phục vụ hiển thị.

Không phục vụ:

* Phân tích
* Thống kê
* Recommendation
* Search Intelligence

---

# 4. Project Vision

Xây dựng một nền tảng dữ liệu tập trung dành riêng cho:

* Sinh viên CNTT
* Sinh viên Khoa học Máy tính
* Sinh viên AI
* Sinh viên Data

giúp:

* Tổng hợp dữ liệu tuyển dụng
* Chuẩn hóa dữ liệu
* Loại bỏ dữ liệu trùng lặp
* Theo dõi vòng đời tuyển dụng
* Hỗ trợ tìm kiếm thông minh
* Hỗ trợ phân tích thị trường việc làm

---

# 5. Business Objectives

Hệ thống cần giải quyết các mục tiêu:

## Objective 1

Thu thập dữ liệu việc làm từ nhiều nguồn.

---

## Objective 2

Xây dựng cơ sở dữ liệu chuẩn hóa.

---

## Objective 3

Theo dõi vòng đời việc làm.

Ví dụ:

* New
* Active
* Updated
* Expired
* Closed
* Reposted

---

## Objective 4

Xác định và gom nhóm job trùng lặp.

---

## Objective 5

Phân tích nhu cầu tuyển dụng.

---

## Objective 6

Phân tích kỹ năng theo ngành nghề.

---

## Objective 7

Xây dựng công cụ tìm kiếm việc làm.

---

## Objective 8

Xây dựng hệ thống gợi ý việc làm.

---

# 6. Target Users

## User Group 1

Sinh viên năm 1–2

Mục tiêu:

* Tìm hiểu thị trường lao động
* Xác định kỹ năng cần học

---

## User Group 2

Sinh viên năm 3–4

Mục tiêu:

* Tìm thực tập
* Tìm việc làm thêm

---

## User Group 3

Fresher

Mục tiêu:

* Tìm việc đầu tiên

---

## User Group 4

Data Analysts

Mục tiêu:

* Phân tích xu hướng tuyển dụng

---

## User Group 5

Data Engineers

Mục tiêu:

* Thực hành Data Engineering end-to-end

---

# 7. Scope

## In Scope

### Data Collection

Thu thập dữ liệu từ:

* ITviec
* TopCV
* VietnamWorks
* CareerViet
* TopDev
* Glints
* JobsGO
* JobOKO
* CareerLink
* Vieclam24h
* YBOX
* Indeed

---

### Data Processing

* Cleaning
* Standardization
* Deduplication
* Lifecycle Management

---

### Data Warehouse

* Star Schema
* Fact Tables
* Dimension Tables

---

### Data Mart

* BI Mart
* Search Mart
* Recommendation Mart

---

### Analytics

* Skill Analysis
* Salary Analysis
* Source Analysis
* Market Analysis

---

### Search

Keyword Search

Skill Search

Semantic Matching (Future)

---

### Recommendation

Rule-based Recommendation

Content-based Recommendation

---

### Web Application

Job Portal

Dashboard

Search Interface

---

# 8. Out of Scope

Không nằm trong giai đoạn đầu:

* CV Parsing
* Resume Ranking
* Candidate Matching
* Real-time Streaming
* LLM Chatbot
* Company Intelligence
* Multi-country Expansion

---

# 9. Success Metrics

## Data Collection

* Số lượng nguồn crawl

Target:

> = 10 websites

---

## Coverage

Số lượng job active.

Target:

> = 10,000 active jobs

---

## Duplicate Detection

Tỷ lệ phát hiện duplicate.

Target:

> 90%

---

## Data Freshness

Độ trễ dữ liệu.

Target:

< 24 giờ

---

## Search

Thời gian phản hồi.

Target:

< 1 giây

---

## Recommendation

Top 10 recommendation relevance.

Target:

Được đánh giá thủ công bởi người dùng.

---

# 10. Data Engineering Learning Goals

Dự án được thiết kế để thực hành:

* Web Crawling
* Data Modeling
* Database Design
* Data Quality
* ETL
* ELT
* Incremental Load
* CDC
* SCD Type 2
* Data Warehouse
* Data Mart
* Airflow
* Docker
* Monitoring
* Search Systems
* Recommendation Systems

---

# 11. Expected Deliverables

Sau khi hoàn thành dự án sẽ có:

## Data Platform

* Data Lake
* Data Warehouse
* Data Mart

---

## Search Platform

* Search API
* Search UI

---

## Analytics Platform

* Power BI Dashboards

---

## Web Application

* Job Portal

---

## Portfolio

Một dự án Data Engineering end-to-end có độ phức tạp gần với môi trường thực tế.
