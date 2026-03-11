# JobInsight Platform — Tài liệu Tổng quan Dự án

> **Phiên bản:** 1.0 — **Cập nhật:** 2026-03-11  
> **Mục tiêu:** Xây dựng nền tảng thu thập, xử lý, và khai thác dữ liệu việc làm Việt Nam, kết hợp NLP, Information Retrieval, Recommendation System và Learning Path Guidance phục vụ sinh viên mới tốt nghiệp và người có ít kinh nghiệm (0–2 năm).

---

## Mục lục

1. [Tầm nhìn & Mục tiêu Chiến lược](#1-tầm-nhìn--mục-tiêu-chiến-lược)
2. [Kiến trúc Tổng thể Hệ thống](#2-kiến-trúc-tổng-thể-hệ-thống)
3. [Data Collection Layer — Thu thập Dữ liệu](#3-data-collection-layer--thu-thập-dữ-liệu)
4. [Data Pipeline & Warehouse](#4-data-pipeline--warehouse)
5. [NLP Processing Layer](#5-nlp-processing-layer)
6. [Information Retrieval System — Tìm kiếm Ngữ nghĩa](#6-information-retrieval-system--tìm-kiếm-ngữ-nghĩa)
7. [Recommendation System — Hệ thống Gợi ý Việc làm](#7-recommendation-system--hệ-thống-gợi-ý-việc-làm)
8. [Skill Gap Analysis & Learning Path](#8-skill-gap-analysis--learning-path)
9. [Web Application — Giao diện Người dùng](#9-web-application--giao-diện-người-dùng)
10. [Cold Start Strategy — Khởi động Lạnh](#10-cold-start-strategy--khởi-động-lạnh)
11. [Data Model Tổng thể](#11-data-model-tổng-thể)
12. [Lộ trình Phát triển (Roadmap)](#12-lộ-trình-phát-triển-roadmap)
13. [Công nghệ Đề xuất](#13-công-nghệ-đề-xuất)
14. [Các Thách thức & Hướng Xử lý](#14-các-thách-thức--hướng-xử-lý)

---

## 1. Tầm nhìn & Mục tiêu Chiến lược

### 1.1 Tuyên bố Sứ mệnh

JobInsight Platform hướng đến việc trở thành **nền tảng tình báo thị trường việc làm** (Job Market Intelligence Platform) dành riêng cho thị trường Việt Nam, với trọng tâm phục vụ hai nhóm đối tượng chính: sinh viên mới tốt nghiệp và người đi làm có ít kinh nghiệm (1–2 năm). Thay vì chỉ là một trang tổng hợp việc làm thông thường, nền tảng cung cấp **trải nghiệm tìm kiếm thông minh**, **gợi ý cá nhân hóa**, và **lộ trình học tập có định hướng** dựa trên nhu cầu thực tế của thị trường lao động.

### 1.2 Các Mục tiêu Cốt lõi

**Mục tiêu về Dữ liệu:**
- Thu thập toàn diện việc làm từ ≥ 11 portal tuyển dụng lớn tại Việt Nam và từ career page trực tiếp của các công ty.
- Xây dựng kho dữ liệu thống nhất, cập nhật tự động theo lịch, phục vụ phân tích dài hạn.
- Đảm bảo chất lượng dữ liệu qua quy trình làm sạch và chuẩn hóa nghiêm ngặt.

**Mục tiêu về Tính năng:**
- Tìm kiếm ngữ nghĩa: người dùng tìm theo kỹ năng/công cụ xuất hiện trong mô tả, không chỉ theo tiêu đề.
- Gợi ý việc làm liên quan dựa trên hồ sơ người dùng và hành vi tương tác.
- Trích xuất tự động danh sách kỹ năng cần thiết từ mô tả công việc.
- Cung cấp lộ trình học cụ thể, có nguồn học, khóa học, chứng chỉ được cá nhân hóa.

**Mục tiêu về Người dùng:**
- Giúp sinh viên mới ra trường định vị được bản thân trong thị trường lao động.
- Rút ngắn khoảng cách giữa năng lực hiện tại và yêu cầu công việc mục tiêu.
- Cung cấp góc nhìn tổng quan về xu hướng kỹ năng theo ngành và địa điểm.

---

## 2. Kiến trúc Tổng thể Hệ thống

Hệ thống được chia thành sáu lớp chức năng độc lập nhưng liên kết chặt chẽ:

```
┌─────────────────────────────────────────────────────────────────────┐
│              ORCHESTRATION LAYER (Apache Airflow)                   │
│  ETL DAG · NLP Processing DAG · Recommendation Update DAG          │
└────────────────────────────┬────────────────────────────────────────┘
                             │
          ┌──────────────────▼──────────────────┐
          │         DATA COLLECTION LAYER        │
          │  Portal Scrapers + Company Crawlers  │
          └──────────────────┬──────────────────┘
                             │
          ┌──────────────────▼──────────────────┐
          │      DATA PIPELINE & WAREHOUSE       │
          │  Raw Storage → Transform → PostgreSQL│
          └──────────────────┬──────────────────┘
                             │
          ┌──────────────────▼──────────────────┐
          │         NLP PROCESSING LAYER         │
          │  Skill Extraction · Text Embedding   │
          │  Entity Recognition · Classification │
          └──────────────────┬──────────────────┘
                             │
       ┌─────────────────────▼─────────────────────┐
       │      INTELLIGENCE & SEARCH LAYER           │
       │  Information Retrieval · Recommendation    │
       │  Skill Gap Analysis · Learning Path Engine │
       └─────────────────────┬─────────────────────┘
                             │
          ┌──────────────────▼──────────────────┐
          │          WEB APPLICATION LAYER       │
          │  FastAPI Backend · Next.js Frontend  │
          └─────────────────────────────────────┘
```

---

## 3. Data Collection Layer — Thu thập Dữ liệu

### 3.1 Nguồn Dữ liệu Portal (Tier 1)

Các portal tuyển dụng trực tuyến là nguồn dữ liệu chính, bao gồm:

| Portal | Phương thức | Đặc điểm kỹ thuật |
|---|---|---|
| TopCV | HTTP + HTML parsing | Dữ liệu phong phú, ít chống bot |
| ITViec | HTTP + JSON API | Có API nội bộ, tập trung IT |
| VietnamWorks | HTTP + JSON | Structured JSON, token auth |
| CareerBuilder | HTTP | Nhiều ngành nghề |
| JobsGO | HTTP + HTML | Có danh sách công ty |
| Glints | HTTP + GraphQL | API GraphQL |
| JobStreet | Playwright | JavaScript challenge |
| LinkedIn | Playwright + Session | Login required, rate limit nghiêm ngặt |
| MyWork | HTTP | Nhiều việc làm mới |
| TimViecNhanh | HTTP | Volume lớn |
| Bất cẩn.vn / Topcv clone | HTTP | Dữ liệu phụ |

### 3.2 Nguồn Dữ liệu Company Career Page (Tier 2)

Đây là điểm khác biệt quan trọng so với các nền tảng thông thường. Quy trình thu thập từ career page công ty gồm bốn bước:

**Bước 1 — Xây dựng Company Master List:**  
Thu thập danh sách công ty từ JobsGO (jobsgo.vn/cong-ty.html), bao gồm tên công ty, URL chi tiết, số lượng tin tuyển dụng, và lĩnh vực hoạt động. Kết quả được lưu vào bảng `companies` trong database làm nguồn gốc.

**Bước 2 — Cào Chi tiết Công ty:**  
Với mỗi công ty, thu thập địa chỉ, website chính thức, lĩnh vực, quy mô. Trường `website` là đầu ra quan trọng nhất để thực hiện bước tiếp theo.

**Bước 3 — Khám phá Career Page:**  
Từ website chính thức, áp dụng chiến lược đa tầng để tìm trang tuyển dụng:
- Kiểm tra các đường dẫn phổ biến: `/careers`, `/jobs`, `/tuyen-dung`, `/work-with-us`, `/join-us`
- Phân tích sitemap.xml nếu có
- Quét menu navigation tìm từ khóa tuyển dụng
- Nhận diện hệ thống ATS (Workable, Greenhouse, Lever, BambooHR, SmartRecruiters) qua các đặc điểm URL và DOM structure đặc trưng

**Bước 4 — Thu thập Dữ liệu Tuyển dụng:**  
Cào toàn bộ thông tin từ career page, chuẩn hóa về `JobSchema` thống nhất, đánh dấu `source = "direct"` để phân biệt với dữ liệu từ portal.

### 3.3 Chiến lược Chống Phát hiện

Hệ thống áp dụng nhiều kỹ thuật chống phát hiện theo mức độ tăng dần:
- **Cơ bản:** Random User-Agent, Random Delay (1–3 giây), Retry với Exponential Backoff
- **Trung bình:** Block tài nguyên không cần thiết (ảnh, font, CSS), Deduplication trước khi request
- **Nâng cao:** Proxy Rotation, Playwright Stealth Mode, Session Cookie management

---

## 4. Data Pipeline & Warehouse

### 4.1 Luồng ETL Tổng thể

Toàn bộ pipeline được điều phối bởi Apache Airflow, chạy theo lịch hàng ngày hoặc theo sự kiện. Luồng xử lý theo ba giai đoạn kinh điển:

**Extract:** Thu thập dữ liệu thô từ các nguồn, lưu dưới dạng JSON tại `data/raw/{portal}/{YYYY-MM-DD}.json`. Giai đoạn này ưu tiên tốc độ và độ đầy đủ, chấp nhận dữ liệu "bẩn".

**Transform:** Làm sạch HTML tags, chuẩn hóa encoding, chuẩn hóa lương về đơn vị VND, chuẩn hóa tên địa điểm, phân loại job_type và level qua Enum. Pydantic v2 đảm bảo type safety và validation ở cuối giai đoạn này.

**Load:** Upsert dữ liệu vào PostgreSQL sử dụng `INSERT ON CONFLICT` với `job_id` là SHA256 hash của (source + job_url), đảm bảo idempotency.

### 4.2 Schema Dữ liệu Cốt lõi

Ngoài bảng `jobs` cơ bản đã được định nghĩa trong tài liệu kiến trúc, hệ thống mở rộng thêm các bảng phục vụ tính năng NLP và AI:

**Bảng `jobs`** — Lưu trữ thông tin cơ bản đã chuẩn hóa (xem JobSchema trong tài liệu kiến trúc).

**Bảng `job_skills`** — Lưu mapping nhiều-nhiều giữa job và skill (job_id, skill_id, confidence_score, extracted_by).

**Bảng `skills`** — Danh mục kỹ năng chuẩn hóa (skill_id, skill_name, skill_category, aliases).

**Bảng `job_embeddings`** — Lưu vector embedding của mỗi job (job_id, embedding vector, model_version, created_at).

**Bảng `companies`** — Thông tin công ty (company_id, name, website, career_url, industry, size, location).

**Bảng `users`** — Hồ sơ người dùng (user_id, target_role, current_skills, experience_years, location_preference).

**Bảng `user_interactions`** — Log tương tác (user_id, job_id, action_type: view/save/apply/skip, timestamp).

**Bảng `learning_resources`** — Nguồn học liệu (resource_id, title, url, platform, resource_type, skills_covered, cost).

### 4.3 Data Quality Framework

Hệ thống áp dụng kiểm tra chất lượng dữ liệu theo ba lớp:
- **Schema Validation:** Pydantic v2 kiểm tra type và format
- **Business Rules:** Kiểm tra logic nghiệp vụ (salary_min ≤ salary_max, posted_date ≤ today)
- **Statistical Monitoring:** Phát hiện anomaly về volume, tỷ lệ missing values theo ngày

---

## 5. NLP Processing Layer

Đây là lớp tạo ra giá trị trí tuệ từ văn bản thô, là nền tảng cho mọi tính năng AI của hệ thống.

### 5.1 Skill Extraction — Trích xuất Kỹ năng

**Vấn đề:** Mô tả công việc chứa kỹ năng ở nhiều dạng khác nhau: tên công nghệ ("Python", "Apache Spark"), kỹ năng mềm ("teamwork", "problem solving"), chứng chỉ ("AWS Certified", "PMP"), và kinh nghiệm ngầm định ("xây dựng data pipeline" → Airflow/Spark).

**Phương pháp đề xuất:**

*Named Entity Recognition (NER) có domain-specific:*  
Huấn luyện hoặc fine-tune mô hình NER trên tập dữ liệu việc làm Việt Nam để nhận diện các thực thể kỹ năng. Cần xây dựng tập nhãn gồm: TECH_SKILL (Python, SQL), SOFT_SKILL (leadership), CERTIFICATION (AWS), TOOL (Jira, Tableau), FRAMEWORK (React, Django).

*Dictionary-based Matching kết hợp NER:*  
Xây dựng skill ontology (cây phân cấp kỹ năng) với hơn 2000 kỹ năng phổ biến trong thị trường Việt Nam. Dùng fuzzy matching để xử lý biến thể chính tả và viết tắt. Phương pháp này có precision cao và dễ bảo trì.

*Regex Pattern Matching:*  
Xử lý các mẫu có cấu trúc rõ ràng như số năm kinh nghiệm ("3+ years of Python"), tên chứng chỉ chuẩn hóa, và phiên bản công nghệ ("Python 3.x").

**Output:** Mỗi job được gắn danh sách kỹ năng với confidence score, lưu vào bảng `job_skills`.

### 5.2 Text Embedding — Mã hóa Ngữ nghĩa

**Mục tiêu:** Chuyển đổi toàn bộ mô tả và yêu cầu công việc thành vector số trong không gian ngữ nghĩa, phục vụ tìm kiếm và gợi ý.

**Lựa chọn mô hình:**
- Với văn bản tiếng Việt thuần túy: `VinAI/phobert-base` hoặc `VinAI/phobert-large` đã được pre-train trên corpus tiếng Việt lớn.
- Với văn bản hỗn hợp Việt-Anh (phổ biến trong JD IT): `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` hoặc `intfloat/multilingual-e5-base`.
- Nội dung được mã hóa: concatenation của title, skills, description, requirements.

**Chiến lược lưu trữ vector:** Với volume lớn (hàng trăm nghìn jobs), cần sử dụng vector database chuyên dụng. `pgvector` extension của PostgreSQL là lựa chọn tự nhiên vì đã có sẵn PostgreSQL trong stack, phù hợp với quy mô dự án. Khi scale lớn hơn có thể migrate sang Qdrant hoặc Milvus.

### 5.3 Job Category Classification

Phân loại việc làm tự động vào các ngành nghề và chuyên môn chuẩn hóa (dựa trên taxonomy của O*NET hoặc tự xây dựng cho thị trường Việt Nam). Mục tiêu là tạo nhãn ngành nghề nhất quán dù nguồn dữ liệu và cách đặt tên khác nhau giữa các portal.

### 5.4 Salary Normalization & Analysis

Xử lý đa dạng format lương: "15–20 triệu", "negotiate", "competitive", "1000–1500 USD". Áp dụng NLP để trích xuất range lương, quy đổi về VND, phân loại vào các bracket chuẩn phục vụ phân tích thống kê theo ngành, địa điểm, và cấp độ kinh nghiệm.

---

## 6. Information Retrieval System — Tìm kiếm Ngữ nghĩa

### 6.1 Vấn đề với Tìm kiếm Từ khóa Truyền thống

Tìm kiếm từ khóa (keyword search) có giới hạn lớn: tìm "data warehouse" sẽ không trả về jobs có mô tả "BigQuery", "Redshift", "Snowflake" dù chúng đều là data warehouse. Tương tự, "machine learning" và "ML" là hai từ khóa khác nhau nhưng cùng ngữ nghĩa.

### 6.2 Kiến trúc Tìm kiếm Hỗn hợp (Hybrid Search)

Hệ thống kết hợp ba phương pháp tìm kiếm:

**Sparse Retrieval (BM25):**  
Tìm kiếm dựa trên tần suất từ xuất hiện, nhanh và hiệu quả cho tên công nghệ chính xác. BM25 có ưu điểm là không cần training và xử lý tốt các thuật ngữ kỹ thuật ít phổ biến.

**Dense Retrieval (Semantic Search):**  
Tìm kiếm dựa trên vector embedding. Khi người dùng nhập "data warehouse", hệ thống encode query thành vector, sau đó tìm các job có vector gần nhất trong không gian ngữ nghĩa. Phương pháp này xử lý tốt synonym, paraphrase, và khái niệm liên quan.

**Structured Filter:**  
Lọc theo các trường có cấu trúc: địa điểm, mức lương, loại hình công việc, cấp bậc kinh nghiệm. Đây là lớp lọc cứng áp dụng sau khi đã có kết quả từ hai phương pháp trên.

**Kết hợp kết quả (Reciprocal Rank Fusion):**  
Điểm cuối cùng của mỗi job = α × BM25_score + β × semantic_score, với α và β được điều chỉnh theo loại query. Query chứa tên công nghệ cụ thể nên ưu tiên α cao, query mô tả công việc nên ưu tiên β cao.

### 6.3 Các Trường hợp Tìm kiếm Đặc thù

**Tìm kiếm theo kỹ năng ẩn:**  
Người dùng gõ "xây dựng ETL pipeline" → hệ thống mở rộng query thành các kỹ năng liên quan (Airflow, Spark, dbt, SQL) trước khi tìm kiếm.

**Tìm kiếm theo role tương đương:**  
"Data Analyst" và "Business Intelligence Analyst" thường có yêu cầu tương tự. Xây dựng role synonym graph để mở rộng kết quả tìm kiếm.

**Tìm kiếm theo mức độ phù hợp:**  
Sau khi người dùng khai báo hồ sơ, kết quả tìm kiếm được re-rank theo độ phù hợp giữa kỹ năng người dùng và yêu cầu công việc.

---

## 7. Recommendation System — Hệ thống Gợi ý Việc làm

### 7.1 Kiến trúc Gợi ý Đa tầng

Hệ thống gợi ý kết hợp nhiều phương pháp để tạo ra gợi ý vừa chính xác vừa đa dạng:

**Tầng 1 — Content-based Filtering:**  
Gợi ý dựa trên nội dung job đã tương tác. Nếu người dùng đã xem nhiều job Data Engineer, hệ thống gợi ý các job có embedding tương tự. Ưu điểm: không cần dữ liệu người dùng khác, xử lý tốt cold start. Nhược điểm: bị "filter bubble" — chỉ gợi ý những thứ giống nhau.

**Tầng 2 — Collaborative Filtering:**  
Gợi ý dựa trên hành vi của những người dùng tương tự. "Người dùng có hồ sơ giống bạn cũng quan tâm đến những job này." Cần đủ lượng tương tác người dùng để hoạt động hiệu quả.

**Tầng 3 — Knowledge-based Recommendation:**  
Gợi ý dựa trên quy tắc nghiệp vụ và ontology kỹ năng. Người dùng có kỹ năng Python + SQL + Statistics → gợi ý các role Data Analyst, Data Scientist, Business Analyst. Đây là tầng hoạt động tốt nhất trong giai đoạn đầu khi chưa có nhiều dữ liệu tương tác.

**Tầng 4 — Hybrid Ensemble:**  
Kết hợp điểm từ ba tầng trên bằng học có giám sát (Gradient Boosting hoặc Neural Network), sử dụng click-through rate và apply rate làm nhãn.

### 7.2 Đặc trưng Đầu vào cho Gợi ý

Mỗi job được biểu diễn qua vector đặc trưng gồm: embedding ngữ nghĩa, one-hot encoding ngành nghề, salary bracket, location encoding, skill vector (binary: có/không từng kỹ năng trong ontology), freshness score (job mới được ưu tiên hơn).

Mỗi người dùng được biểu diễn qua: kỹ năng hiện có (tự khai báo + suy diễn từ tương tác), target role, năm kinh nghiệm, địa điểm ưu tiên, salary expectation, lịch sử tương tác (xem, lưu, apply, bỏ qua).

### 7.3 Diversity & Serendipity

Để tránh gợi ý đơn điệu, hệ thống áp dụng:
- **Maximal Marginal Relevance (MMR):** Cân bằng giữa relevance và diversity trong danh sách kết quả.
- **Exploration Band:** Dành 10–20% slot gợi ý cho jobs ở các ngành/role liền kề để mở rộng tầm nhìn người dùng.
- **Temporal Diversity:** Tránh gợi ý cùng công ty nhiều lần trong thời gian ngắn.

---

## 8. Skill Gap Analysis & Learning Path

### 8.1 Phân tích Khoảng cách Kỹ năng (Skill Gap Analysis)

**Quy trình:**

*Bước 1 — Xây dựng Job Skill Profile:*  
Với mỗi role (ví dụ: Data Engineer), tổng hợp kỹ năng từ tất cả job thuộc role đó trong database. Tính tần suất xuất hiện của từng kỹ năng. Phân loại thành: Core Skills (xuất hiện > 70% job), Common Skills (30–70%), Nice-to-have Skills (< 30%).

*Bước 2 — Xây dựng User Skill Profile:*  
Thu thập kỹ năng người dùng qua ba kênh: tự khai báo trong khảo sát onboarding, upload CV (parse bằng NLP), và suy diễn từ khóa học/chứng chỉ đã hoàn thành.

*Bước 3 — Gap Calculation:*  
Gap = Core Skills(role) ∪ Common Skills(role) — User Skills. Mỗi kỹ năng trong gap được gắn: mức độ ưu tiên (dựa trên tần suất trong JD), độ khó học (phân loại: fundamental/intermediate/advanced), và thời gian ước tính.

### 8.2 Learning Path Engine

**Mục tiêu:** Chuyển hóa danh sách kỹ năng cần học thành lộ trình học có thứ tự hợp lý, kèm nguồn học cụ thể.

**Xây dựng Skill Dependency Graph:**  
Các kỹ năng có quan hệ phụ thuộc nhau: học Spark cần biết Python trước; học Machine Learning cần biết Statistics và Python trước. Xây dựng DAG (Directed Acyclic Graph) biểu diễn quan hệ tiên quyết giữa các kỹ năng. Topological sort trên DAG này cho ra thứ tự học hợp lý.

**Cá nhân hóa Lộ trình:**  
Lộ trình được điều chỉnh theo: thời gian khả dụng (bán thời gian vs toàn thời gian), ngân sách (ưu tiên tài nguyên miễn phí nếu cần), phong cách học (video, đọc, thực hành), và deadline mục tiêu (muốn ứng tuyển trong 3 tháng hay 1 năm).

**Nguồn Học liệu (Learning Resources Database):**  
Hệ thống duy trì cơ sở dữ liệu học liệu bao gồm:

- *Khóa học trực tuyến:* Coursera, edX, Udemy, Pluralsight, DataCamp, LinkedIn Learning — với metadata: kỹ năng dạy, thời lượng, giá, ngôn ngữ, rating.
- *Tài liệu miễn phí:* Official documentation, GitHub repos, YouTube channels, blogs kỹ thuật uy tín.
- *Chứng chỉ:* AWS Certified, Google Cloud, Microsoft Azure, Databricks, Snowflake, CFA, PMP — với thông tin: nhà cung cấp, chi phí thi, thời hạn hiệu lực, độ phổ biến trong JD.
- *Cộng đồng & Thực hành:* Kaggle competitions, GitHub projects mẫu, hackathon, contribution vào open source.

**Output của Learning Path:**  
Mỗi lộ trình học được trình bày dưới dạng timeline với: milestone rõ ràng, tài nguyên học cho từng milestone, bài tập thực hành, và checkpoint để tự đánh giá tiến độ.

### 8.3 Market Trend Analysis

Phân tích xu hướng kỹ năng theo thời gian từ dữ liệu thu thập được:
- Kỹ năng nào đang tăng nhu cầu (trending up) và kỹ năng nào đang giảm.
- Mức lương trung bình theo kỹ năng và theo sự kết hợp kỹ năng.
- Tỷ lệ remote work theo ngành nghề và địa điểm.
- Phân phối kinh nghiệm yêu cầu theo role và công ty.

---

## 9. Web Application — Giao diện Người dùng

### 9.1 Kiến trúc Ứng dụng

**Backend:** FastAPI (Python) — REST API + WebSocket cho real-time notifications. Phù hợp vì toàn bộ AI/NLP stack đã dùng Python.

**Frontend:** Next.js (React) — Server-side rendering cho SEO, TypeScript cho type safety.

**Search Engine:** Elasticsearch hoặc pgvector tích hợp trong PostgreSQL tùy quy mô.

**Cache:** Redis — Cache kết quả tìm kiếm phổ biến, session data, và recommendation results.

### 9.2 Các Trang và Tính năng Chính

**Trang Tìm kiếm (Search Page):**
- Thanh tìm kiếm thông minh với auto-suggest (gợi ý kỹ năng, role, công ty khi gõ).
- Bộ lọc động: địa điểm, lương, loại hình, cấp bậc, ngành nghề, đăng trong vòng X ngày.
- Kết quả hiển thị với highlight kỹ năng match trong mô tả.
- Chế độ xem: danh sách và bản đồ (geolocate jobs).
- Lưu tìm kiếm và nhận email alert khi có job mới phù hợp.

**Trang Chi tiết Job (Job Detail Page):**
- Thông tin đầy đủ về job, công ty.
- Panel "Skill Match": so sánh kỹ năng yêu cầu với kỹ năng người dùng (nếu đã đăng nhập).
- Phần "Để ứng tuyển job này, bạn cần học thêm:": link trực tiếp đến learning path cho các kỹ năng còn thiếu.
- Jobs tương tự từ cùng công ty và từ các công ty khác.
- Lịch sử lương trung bình cho role này theo thời gian.

**Trang Hồ sơ & Skill Assessment (Profile Page):**
- Dashboard kỹ năng: visualization hình mạng nhện (radar chart) so sánh kỹ năng hiện tại với yêu cầu của role mục tiêu.
- Progress tracker cho từng learning path đang theo đuổi.
- Lịch sử tương tác với jobs (đã xem, đã lưu, đã apply).
- Cài đặt thông báo và alert.

**Trang Learning Path (Career Guide Page):**
- Chọn role mục tiêu (hoặc được gợi ý dựa trên hồ sơ).
- Skill gap visualization: kỹ năng đã có (xanh) vs cần học (đỏ/vàng).
- Timeline học tập tương tác với thể kéo thả để điều chỉnh.
- Thư viện tài nguyên học được lọc theo kỹ năng và sở thích.

**Trang Market Insights (Analytics Page):**
- Dashboard xu hướng thị trường: top kỹ năng theo tháng, top ngành tuyển dụng nhiều, phân phối lương theo role và địa điểm.
- Công khai cho mọi người dùng, không cần đăng nhập.
- Cập nhật tự động theo dữ liệu mới nhất từ pipeline.

---

## 10. Cold Start Strategy — Khởi động Lạnh

### 10.1 Vấn đề Cold Start

Cold start xảy ra ở hai cấp độ: người dùng mới (chưa có lịch sử tương tác) và hệ thống mới (chưa đủ dữ liệu tương tác tổng thể). Cả hai đều ảnh hưởng đến chất lượng gợi ý.

### 10.2 Khảo sát Onboarding (Giải pháp chính)

Khi người dùng đăng ký lần đầu, thực hiện khảo sát ngắn (không quá 5 phút) theo dạng wizard từng bước:

**Bước 1 — Tình trạng Hiện tại:**
- Bạn đang là: Sinh viên / Mới tốt nghiệp / Đang đi làm (muốn chuyển ngành) / Thất nghiệp
- Chuyên ngành học / Ngành làm hiện tại
- Số năm kinh nghiệm (nếu có)

**Bước 2 — Mục tiêu:**
- Role mong muốn (chọn từ danh sách có search/filter)
- Địa điểm làm việc ưu tiên
- Mức lương kỳ vọng
- Timeline: muốn đi làm trong bao lâu

**Bước 3 — Kỹ năng Hiện có (Multi-select với search):**
- Kỹ năng kỹ thuật (từ danh sách 200+ kỹ năng phổ biến)
- Kỹ năng mềm
- Chứng chỉ đã có
- Upload CV (optional, auto-parse)

**Bước 4 — Sở thích Học tập:**
- Hình thức học ưu tiên: Video / Đọc / Thực hành dự án
- Thời gian học mỗi tuần: < 5h / 5–10h / > 10h
- Ngân sách: Chỉ miễn phí / Có thể trả phí có chọn lọc / Linh hoạt

### 10.3 Các Chiến lược Bổ sung

**Popularity-based Fallback:**  
Khi chưa đủ thông tin cá nhân hóa, gợi ý dựa trên các jobs phổ biến nhất trong role/ngành người dùng quan tâm, ưu tiên jobs mới đăng và từ công ty uy tín.

**Progressive Profiling:**  
Dần dần cập nhật hồ sơ người dùng qua tương tác. Mỗi lần người dùng click xem job, lưu job, hoặc skip job → hệ thống ngầm hiểu thêm về sở thích và điều chỉnh gợi ý.

**A/B Testing cho Onboarding:**  
Thử nghiệm nhiều phiên bản khảo sát onboarding để tối ưu tỷ lệ hoàn thành và chất lượng dữ liệu thu thập được.

---

## 11. Data Model Tổng thể

```
companies (company_id, name, website, career_url, industry, size, founded_year, location, description, source, crawled_at)
    │
    ├─── jobs (job_id, company_id, source, title, location, salary_min, salary_max,
    │         salary_currency, job_type, level, description, requirements, benefits,
    │         posted_date, deadline, job_url, scraped_at, is_active, embedding_id)
    │         │
    │         └─── job_skills (job_id, skill_id, confidence, position: title/desc/req)
    │
skills (skill_id, name, category, aliases[], parent_skill_id, difficulty_level)
    │
    └─── skill_prerequisites (skill_id, prerequisite_skill_id, is_hard_requirement)

users (user_id, email, name, target_role, experience_years, location_pref,
       salary_expectation, created_at, last_active_at)
    │
    ├─── user_skills (user_id, skill_id, proficiency_level, source: declared/inferred)
    │
    ├─── user_interactions (interaction_id, user_id, job_id, action_type,
    │                       session_id, timestamp, device_type)
    │
    └─── user_learning_paths (user_id, target_role_id, created_at, progress_percentage,
                              milestone_completions[])

learning_resources (resource_id, title, url, platform, resource_type,
                   duration_hours, cost, language, rating, skills_covered[],
                   last_verified_at)

job_embeddings (job_id, embedding VECTOR(768), model_name, created_at)
```

---

## 12. Lộ trình Phát triển (Roadmap)

### Giai đoạn 1 — Nền tảng (Tháng 1–2)
**Mục tiêu:** Có dữ liệu sạch và pipeline ổn định.
- Xây dựng và kiểm thử toàn bộ scrapers cho 11 portal.
- Triển khai ETL pipeline trên Airflow, chạy ổn định hàng ngày.
- Thiết lập PostgreSQL schema, đảm bảo upsert đúng logic.
- Thu thập company list từ JobsGO, xây dựng company crawler cơ bản.
- Deliverable: ≥ 50,000 jobs trong database, pipeline chạy tự động.

### Giai đoạn 2 — NLP & Search (Tháng 3–4)
**Mục tiêu:** Có tính năng tìm kiếm thông minh hoạt động.
- Xây dựng skill ontology với ≥ 1000 kỹ năng.
- Triển khai skill extraction pipeline (NER + dictionary matching).
- Tạo embeddings cho toàn bộ jobs, lưu vào pgvector.
- Xây dựng hybrid search API.
- Deliverable: API tìm kiếm nhận query ngôn ngữ tự nhiên, trả kết quả ngữ nghĩa.

### Giai đoạn 3 — Web App MVP (Tháng 5–6)
**Mục tiêu:** Có sản phẩm để người dùng thực sự sử dụng.
- Xây dựng FastAPI backend với các endpoint cần thiết.
- Xây dựng Next.js frontend: trang search, job detail, profile.
- Triển khai hệ thống onboarding và cold start.
- Tích hợp learning resources database cơ bản.
- Deliverable: Web app có thể demo và thu thập người dùng beta.

### Giai đoạn 4 — Recommendation & Learning Path (Tháng 7–8)
**Mục tiêu:** Cá nhân hóa trải nghiệm người dùng.
- Triển khai content-based recommendation.
- Xây dựng skill gap analysis engine.
- Xây dựng learning path generator với dependency graph.
- Thu thập và tích hợp ≥ 500 learning resources.
- Deliverable: Mỗi người dùng nhận gợi ý việc làm và lộ trình học cá nhân hóa.

### Giai đoạn 5 — Scale & Intelligence (Tháng 9–12)
**Mục tiêu:** Cải thiện chất lượng và mở rộng.
- Collaborative filtering khi đã có đủ dữ liệu tương tác.
- Market trend dashboard công khai.
- Company career page crawler mở rộng (≥ 200 công ty lớn).
- A/B testing framework cho recommendation.
- Email alert và notification system.
- Deliverable: Nền tảng hoàn chỉnh với ≥ 1000 người dùng đăng ký.

---

## 13. Công nghệ Đề xuất

| Thành phần | Công nghệ | Lý do lựa chọn |
|---|---|---|
| Orchestration | Apache Airflow 2.8.x | Scheduling, monitoring, retry |
| Scraping (HTTP) | Scrapling | Nhanh, ít fingerprint |
| Scraping (JS) | Playwright | Xử lý JS challenge |
| Data Validation | Pydantic v2 | Type safety, performance |
| Data Processing | pandas + polars | pandas quen thuộc, polars nhanh |
| NLP — Vietnamese | PhoBERT (VinAI) | Pre-train tiếng Việt tốt nhất |
| NLP — Multilingual | multilingual-e5 | Hỗn hợp Việt-Anh |
| NLP — NER | spaCy + custom model | Production-ready, extensible |
| Vector Storage | pgvector | Tích hợp PostgreSQL, đơn giản |
| Full-text Search | PostgreSQL FTS | Đã có sẵn trong stack |
| Database | PostgreSQL 15 | Mọi dữ liệu, pgvector extension |
| Cache | Redis 7.2 | Session, search cache |
| Backend API | FastAPI | Async, type hints, tự generate docs |
| Frontend | Next.js 14 | SSR, SEO, React ecosystem |
| Container | Docker + Compose | Portability, isolation |
| Monitoring | Prometheus + Grafana | Pipeline health, performance metrics |
| Testing | pytest | Unit và integration tests |

---

## 14. Các Thách thức & Hướng Xử lý

### 14.1 Thách thức Kỹ thuật

**Anti-scraping ngày càng tinh vi:**  
Các portal lớn như LinkedIn, JobStreet đầu tư mạnh vào hệ thống phát hiện bot. Hướng xử lý: Playwright Stealth, proxy rotation, giả lập hành vi người dùng thực (random delay, mouse movement), và tuân thủ robots.txt để tránh vi phạm ToS.

**Chất lượng NLP cho tiếng Việt hỗn hợp:**  
JD công nghệ thường pha trộn Việt-Anh, thuật ngữ kỹ thuật dùng tiếng Anh nhưng ngữ pháp tiếng Việt. Hướng xử lý: Dùng multilingual model, xây dựng domain-specific dictionary, fine-tune trên tập dữ liệu JD Việt Nam tự thu thập.

**Scalability của Vector Search:**  
Khi số lượng jobs tăng lên hàng triệu, tìm kiếm vector sẽ chậm nếu không có index phù hợp. Hướng xử lý: Dùng HNSW index trong pgvector, xem xét migrate sang Qdrant khi cần, và implement Approximate Nearest Neighbor (ANN) search.

### 14.2 Thách thức Nghiệp vụ

**Dữ liệu lương thiếu và không đồng nhất:**  
Nhiều công ty không công bố lương hoặc chỉ ghi "Thỏa thuận". Hướng xử lý: Tổng hợp từ nhiều nguồn, dùng ML để impute salary range dựa trên role/company/location, hiển thị "Ước tính" rõ ràng.

**Cold Start cho Recommendation:**  
Hướng xử lý đã trình bày chi tiết ở mục 10 — kết hợp khảo sát onboarding, popularity-based fallback, và progressive profiling.

**Giữ chân người dùng (User Retention):**  
Đây là thách thức lớn nhất với nền tảng tìm việc — người dùng thường chỉ dùng khi đang tìm việc. Hướng xử lý: Cung cấp giá trị liên tục ngay cả khi không tìm việc qua Market Insights, learning path tracking, và skill assessment định kỳ.

### 14.3 Thách thức Pháp lý & Đạo đức

**Terms of Service các portal:**  
Tuân thủ robots.txt, giới hạn tốc độ request hợp lý, không cache dữ liệu quá lâu, và ưu tiên thu thập từ career page trực tiếp (nguồn gốc) thay vì portal trung gian.

**Bảo mật Dữ liệu Người dùng:**  
Mã hóa dữ liệu nhạy cảm, không chia sẻ hồ sơ cá nhân, tuân thủ quy định bảo vệ dữ liệu cá nhân theo Nghị định 13/2023/NĐ-CP của Việt Nam.

---

## Phụ lục A — Skill Ontology (Danh mục Kỹ năng Mẫu)

### Nhóm Data & Analytics
- **Languages:** Python, R, SQL, Scala, Julia
- **Data Engineering:** Apache Spark, Apache Kafka, Apache Airflow, dbt, Flink, NiFi
- **Data Warehouse:** BigQuery, Snowflake, Redshift, Databricks, ClickHouse, PostgreSQL
- **Orchestration:** Airflow, Prefect, Dagster, Luigi
- **Visualization:** Tableau, Power BI, Looker, Metabase, Grafana, Apache Superset
- **ML/DS:** scikit-learn, TensorFlow, PyTorch, XGBoost, MLflow, Kubeflow

### Nhóm Software Engineering
- **Backend:** Python (FastAPI/Django/Flask), Java (Spring), Node.js, Go, .NET
- **Frontend:** React, Vue.js, Angular, Next.js, TypeScript
- **Mobile:** React Native, Flutter, Swift, Kotlin
- **DevOps/Cloud:** Docker, Kubernetes, AWS, GCP, Azure, Terraform, CI/CD

### Nhóm Business & Soft Skills
- **Analytical:** Critical thinking, Problem solving, Data-driven decision making
- **Communication:** Presentation, Technical writing, Stakeholder management
- **Project Management:** Agile/Scrum, Jira, Confluence, PMP

---

## Phụ lục B — Chứng chỉ Phổ biến theo Ngành

| Ngành | Chứng chỉ | Nhà cung cấp | Mức độ |
|---|---|---|---|
| Data Engineering | AWS Data Engineer Associate | AWS | Entry-Mid |
| Data Engineering | Google Professional Data Engineer | GCP | Mid-Senior |
| Data Engineering | Databricks Certified Associate | Databricks | Entry-Mid |
| Data Science | TensorFlow Developer Certificate | Google | Mid |
| Data Science | Databricks ML Professional | Databricks | Senior |
| Cloud | AWS Solutions Architect Associate | AWS | Mid |
| Cloud | Google Cloud Professional Cloud Architect | GCP | Senior |
| Analytics | Google Data Analytics Certificate | Coursera/Google | Entry |
| Analytics | Microsoft Power BI Data Analyst | Microsoft | Entry-Mid |
| Project Mgmt | PMP | PMI | Mid-Senior |

---

*Tài liệu này là living document, cập nhật liên tục theo tiến độ phát triển dự án.*  
*Phiên bản tiếp theo sẽ bổ sung: chi tiết API specification, database migration strategy, và deployment architecture.*
