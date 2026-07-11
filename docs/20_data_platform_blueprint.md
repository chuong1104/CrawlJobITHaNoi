# 20. JobITVN Data Platform — Blueprint Toàn Diện

> **Phiên bản:** 2.0 | **Ngày cập nhật:** 2026-06-24
> Stack: Airflow · Floci S3 · DuckDB · dbt · Parquet · FastAPI · Elasticsearch · Power BI · ML/RAG

---

## Mục lục

1. [Tổng quan kiến trúc](#1-tổng-quan-kiến-trúc)
2. [Tầng 0 — Extract & Ingestion](#2-tầng-0--extract--ingestion)
3. [Tầng 1 — Bronze (Raw Lake)](#3-tầng-1--bronze-raw-lake)
4. [Tầng 2 — Silver (Staging / Cleaned)](#4-tầng-2--silver-staging--cleaned)
5. [Tầng 3 — Gold (Warehouse + Marts)](#5-tầng-3--gold-warehouse--marts)
6. [Tầng 4 — Serving Layer](#6-tầng-4--serving-layer)
7. [Tầng 5 — AI/ML & Search](#7-tầng-5--aiml--search)
8. [Orchestration — Airflow](#8-orchestration--airflow)
9. [Lượng tử hóa & Đo lường hiệu suất vận hành](#9-lượng-tử-hóa--đo-lường-hiệu-suất-vận-hành)
10. [Kỹ thuật tối ưu DE tổng hợp](#10-kỹ-thuật-tối-ưu-de-tổng-hợp)
11. [Security & Governance](#11-security--governance)
12. [Cấu trúc thư mục hoàn chỉnh](#12-cấu-trúc-thư-mục-hoàn-chỉnh)
13. [Checklist triển khai theo phase](#13-checklist-triển-khai-theo-phase)

---

## 1. Tổng quan kiến trúc

### 1.1 Sơ đồ luồng dữ liệu

Dữ liệu di chuyển qua 6 tầng chính theo hướng một chiều, từ nguồn thô đến các consumer cuối cùng:

```
[Nguồn: 11 job portals]
        ↓  (Playwright / Scrapling HTTP)
[Tầng 0 — Extract]  →  Validate schema, tính content hash
        ↓  (JSONL upload lên Floci S3)
[Tầng 1 — Bronze]   →  Raw lake, immutable, partition theo ngày
        ↓  (dbt + DuckDB đọc JSON, transform, ghi Parquet)
[Tầng 2 — Silver]   →  Cleaned, parsed, deduped, Parquet
        ↓  (dbt build Gold models)
[Tầng 3 — Gold]     →  Star Schema + Data Marts, Parquet
        ↓
[Tầng 4 — Serving]  →  FastAPI · Power BI · Elasticsearch
        ↓
[Tầng 5 — AI/ML]    →  Recommendation · RAG · Salary Prediction
```

### 1.2 Nguyên tắc thiết kế nền tảng

**ELT thay vì ETL:** Dữ liệu thô được đẩy vào storage trước, việc transform diễn ra sau đó trong DuckDB và dbt. Không có logic làm sạch nào trong scraper ngoài validate cơ bản.

**Immutable Bronze:** Tầng Bronze chỉ ghi thêm (append-only), không bao giờ sửa hay xóa. Đây là bảo hiểm để replay lại toàn bộ pipeline bất cứ lúc nào nếu phát sinh lỗi ở tầng sau.

**Parquet từ Silver trở lên:** Bronze lưu JSONL để giữ nguyên raw, còn từ Silver trở đi toàn bộ dữ liệu lưu dạng Parquet có nén Snappy — nhỏ hơn JSON khoảng 5–8 lần và DuckDB đọc nhanh hơn nhiều vì columnar format.

**Partition theo ngày:** Mọi S3 path đều có cấu trúc `year=/month=/day=/` để DuckDB có thể tự động bỏ qua các partition không liên quan khi query, giảm lượng data scan xuống đáng kể.

**Incremental mặc định:** Không có tác vụ nào chạy full refresh hàng ngày trừ bảng dimension nhỏ. Tất cả fact table và staging model đều chạy incremental, chỉ xử lý data mới hơn lần chạy cuối.

**Schema-first:** Pydantic validate mọi record ngay tại điểm scrape. Record nào không qua validate bị đưa vào hàng đợi reject riêng, không được phép vào Bronze.

---

## 2. Tầng 0 — Extract & Ingestion

### 2.1 Nhiệm vụ và trách nhiệm

Tầng này là điểm tiếp xúc đầu tiên với dữ liệu thô từ bên ngoài. Nhiệm vụ duy nhất là **lấy dữ liệu và đẩy vào Bronze** — không transform, không làm sạch, không phân tích.

Tuy nhiên, trước khi đẩy vào Bronze, tầng này phải làm hai việc quan trọng: validate schema để đảm bảo record đủ các trường bắt buộc và tính toán **content hash** — một chuỗi fingerprint ngắn đại diện cho nội dung của record. Content hash này là cơ sở để phát hiện thay đổi về sau (thay thế CDC truyền thống).

### 2.2 Kiến trúc scrapers

Toàn bộ scrapers được xây dựng theo mô hình **Abstract Base Class**. Lớp cha (`BaseCrawler`) chứa toàn bộ logic chung: retry khi fail, rate limiting ngẫu nhiên giữa các request để tránh bị block, batch upload lên S3, và xử lý reject queue. Mỗi scraper con chỉ cần implement hai hàm: một hàm lấy danh sách URL từ listing page, và một hàm parse HTML/JSON trả về dict raw fields.

**Cơ chế retry:** Mỗi request được thử lại tối đa 3 lần với thời gian chờ tăng dần theo hàm mũ (exponential backoff) — 2 giây, 4 giây, 8 giây. Sau 3 lần thất bại, record được đưa vào reject log chứ không làm crash toàn bộ pipeline.

**Rate limiting:** Giữa mỗi request, scraper chờ một khoảng thời gian ngẫu nhiên trong khoảng cho phép (ví dụ 1–3 giây) để mô phỏng hành vi người dùng thật và tránh bị phát hiện.

**Proxy rotation:** LinkedIn và JobStreet có anti-bot rất mạnh, cần rotate IP qua danh sách proxy. ProxyManager sẽ tự động chọn proxy khác khi proxy hiện tại bị block.

### 2.3 Schema validation — Pydantic

Mỗi record từ scraper được validate qua một Pydantic model (`RawJobPosting`) trước khi upload. Model này định nghĩa:

- **Trường bắt buộc:** `job_id_raw`, `title`, `company_name`, `source`, `url`. Bất kỳ record nào thiếu một trong các trường này sẽ bị reject.
- **Trường tùy chọn:** `salary_raw`, `location_raw`, `skills_raw`, `posted_date_raw`, v.v. Giữ nguyên dạng string thô, chưa parse ở tầng này.
- **Validator tự động:** `title` không được rỗng hoặc chỉ chứa khoảng trắng. `source` phải nằm trong danh sách cho phép. `url` phải bắt đầu bằng `http`.
- **Content hash:** Sau khi validate xong, model tự động tính SHA-256 hash trên các trường quan trọng (`title`, `company_name`, `salary_raw`, `location_raw`, `skills_raw`), rút gọn còn 16 ký tự. Hash này được lưu vào field `_content_hash`.
- **System fields:** `_scraped_at` (timestamp UTC), `_pipeline_version` được gán tự động.

Records không qua validate được lưu vào `s3://jobit-bronze/rejected/{source}/{date}_rejected.jsonl` kèm theo thông báo lỗi cụ thể để debug.

### 2.4 Upload lên S3

Sau khi validate xong một batch, toàn bộ records hợp lệ được serialize thành JSONL (mỗi record một dòng) và upload một lần duy nhất lên S3. Path tuân theo convention: `raw/{source}/year={Y}/month={M}/day={D}/{source}_{date}.jsonl`.

Kèm theo file JSONL là một file metadata JSON nhỏ ghi lại: tổng số records scraped, số validated, số rejected, thời gian scrape, kích thước file, và MD5 checksum của file data.

### 2.5 Chạy song song

Tất cả scrapers được chạy song song qua `ThreadPoolExecutor` với số worker có thể cấu hình (mặc định 4 worker). Mỗi source chạy độc lập, lỗi ở source này không ảnh hưởng source khác.

---

## 3. Tầng 1 — Bronze (Raw Lake)

### 3.1 Triết lý: Nguồn sự thật bất biến

Bronze là bản ghi vĩnh viễn của mọi thứ hệ thống đã thu thập được. Nguyên tắc cốt lõi: **không bao giờ xóa, không bao giờ sửa**. Đây là điểm duy nhất trong hệ thống mà dữ liệu được coi là hoàn toàn raw và đáng tin cậy.

Giá trị thực tiễn: nếu logic transform ở Silver hay Gold có bug, ta có thể rollback về Bronze và replay lại toàn bộ pipeline mà không mất dữ liệu nào. Đây là lợi thế lớn nhất của kiến trúc ELT so với ETL truyền thống.

---

## 4. Tầng 2 — Silver (Cleaned / 3NF Operational DB)

### 4.1 Nhiệm vụ và Triết lý
Tầng Silver không chỉ đơn thuần là nơi làm sạch dữ liệu phẳng, mà nó được thiết kế như một **Cơ sở dữ liệu nghiệp vụ chuẩn hóa (Operational Database - 3NF DB)** lưu trữ trong PostgreSQL (schema `silver`). 

**Ảnh hưởng đến kiến trúc 3 tầng (Operational / 3NF DB → DWH → Data Marts):**
Việc sử dụng PostgreSQL làm hệ quản trị cơ sở dữ liệu nghiệp vụ cho Silver schema **hoàn toàn không làm ảnh hưởng hay phá vỡ kiến trúc 3 tầng**, mà ngược lại, nó **củng cố và làm rõ ràng hơn** ranh giới giữa tầng lưu trữ nghiệp vụ Operational (Silver 3NF) và tầng phân tích Analytical (Gold/DWH và Marts). Dữ liệu được phân tách vật lý qua các schema khác nhau trên PostgreSQL (`silver` -> `dwh` -> `mart`), giúp tối ưu hóa hiệu năng ghi-đọc và duy trì tính toàn vẹn dữ liệu thông qua các ràng buộc khóa ngoại (Foreign Keys) ở Silver mà các hệ thống tệp phẳng (Lakehouse Parquet) rất khó thực thi triệt để.

Tầng Silver chịu trách nhiệm cốt lõi cho các nhiệm vụ:
* Lưu trữ dữ liệu tuyển dụng đã được làm sạch và chuẩn hóa cấu trúc nghiệp vụ hoàn toàn.
* Thực thi cơ chế quản lý vòng đời tin tuyển dụng (Job Lifecycle) chặt chẽ.
* Theo dõi lịch sử biến động nội dung tin tuyển dụng qua mô hình phiên bản (SCD Type 2).
* Nhận diện và gom nhóm các tin tuyển dụng trùng lặp chéo giữa các nguồn (Cross-source deduplication).
* Cung cấp nguồn dữ liệu ổn định và sạch tuyệt đối để nạp vào Data Warehouse ở tầng sau.

### 4.2 Staging Layer — Làm sạch dữ liệu thô
Trước khi dữ liệu được nạp vào cấu trúc 3NF phức tạp, nó đi qua một vùng đệm gọi là schema `staging` trong PostgreSQL. Tiến trình dbt (chạy trên PostgreSQL) đọc dữ liệu từ Bronze (S3 JSONL) thông qua các bảng ngoại hoặc tệp Parquet trung gian để thực hiện các bước làm sạch cơ bản cho từng nguồn tuyển dụng:

* **Phân tích mức lương (Salary parsing):** Sử dụng các biểu thức chính quy (Regex) và logic điều kiện để bóc tách chuỗi lương tự do (ví dụ: "15 - 20 triệu", "$500 - $1000", "Thỏa thuận") thành các cột số chuẩn: mức lương tối thiểu (VND), mức lương tối đa (VND), đơn vị tiền tệ gốc, và cờ đánh dấu lương thỏa thuận.
* **Chuẩn hóa địa điểm (Location normalization):** Đối chiếu văn bản địa điểm thô của bài đăng với danh mục chuẩn hóa thông qua bảng ánh xạ địa điểm (ví dụ: quy đổi "Ha Noi", "HN", "Hà Nội" về một chuỗi chuẩn "Hà Nội").
* **Phân tích số năm kinh nghiệm:** Trích xuất yêu cầu kinh nghiệm thô thành số năm tối thiểu và tối đa. Quy đổi các cụm từ "không yêu cầu" hoặc "dưới 1 năm" thành số 0.
* **Chuẩn hóa cấp bậc & hình thức làm việc:** Đưa các văn bản thô về danh mục chuẩn hóa của hệ thống (Intern, Fresher, Junior... và Onsite, Hybrid, Remote).
* **Khử trùng lặp nội bộ nguồn:** Loại bỏ các tin tuyển dụng bị trùng lặp ID hoặc URL ngay trong cùng một nguồn tin trong ngày quét.

### 4.3 Schema Testing & Kiểm soát chất lượng (Quality Gate)
Mỗi bảng trong vùng đệm `staging` được kiểm tra tính toàn vẹn dữ liệu qua các bài test dbt tự động trước khi cho phép nạp vào lớp nghiệp vụ 3NF:
* **Kiểm tra khóa chính:** Đảm bảo trường mã định danh nguồn (`source_job_id`) kết hợp với mã nguồn (`source_id`) là duy nhất và không được rỗng.
* **Kiểm tra miền giá trị:** Ràng buộc mức lương tối thiểu không được lớn hơn mức lương tối đa, và các cờ trạng thái chỉ nhận giá trị logic (Đúng/Sai).
* **Kiểm tra độ mới dữ liệu (Recency test):** Cảnh báo hệ thống nếu một nguồn tin không có dữ liệu mới được nạp trong vòng 3 ngày liên tiếp.

### 4.4 Cấu trúc Cơ sở dữ liệu nghiệp vụ (Silver/3NF Schema)
Sau khi vượt qua vòng kiểm tra chất lượng tại Staging, dữ liệu được đồng bộ vào hệ thống bảng chuẩn hóa 3NF trong schema `silver` bao gồm các bảng cốt lõi:
* **Bảng tin tuyển dụng (`jobs`):** Lưu thông tin định danh tĩnh của công việc (ID nguồn, URL chuẩn hóa, khóa công ty, mã vân tay định danh) và trạng thái vòng đời hiện tại (`job_status`, `is_active`, các mốc thời gian lần đầu/lần cuối nhìn thấy).
* **Bảng phiên bản tin tuyển dụng (`job_snapshots`):** Lưu trữ thông tin nội dung động (tiêu đề, mô tả, lương, kinh nghiệm) áp dụng kỹ thuật SCD Type 2 để theo dõi lịch sử cập nhật.
* **Bảng công ty (`companies`) & Bí danh (`company_aliases`):** Quản lý thông tin doanh nghiệp tập trung, hỗ trợ quy đổi nhiều cách viết tên công ty khác nhau về một ID duy nhất.
* **Bảng nhóm trùng lặp (`job_duplicate_groups` & `job_duplicate_group_members`):** Gom cụm các tin tuyển dụng giống nhau từ nhiều nguồn tin khác nhau để phục vụ hiển thị và phân tích.
* **Bảng nhật ký sự kiện (`job_events`):** Lưu vết chi tiết từng biến động trạng thái và nội dung của tin tuyển dụng để phục vụ kiểm toán và giám sát pipeline.
* **Bảng từ điển chuẩn hóa (`skills`, `locations`):** Danh mục kỹ năng công nghệ và địa giới hành chính làm quy chuẩn liên kết.

### 4.5 Quản Lý Vòng Đời Tin Tuyển Dụng (Job Lifecycle) & Tiến trình đồng bộ hằng ngày

#### Quy trình xử lý đồng bộ nghiệp vụ
Mỗi ngày, sau khi Staging hoàn tất, một tiến trình chạy ngầm sẽ thực thi logic đồng bộ dữ liệu Staging vào lớp 3NF theo các bước:
1. **Khớp nối thực thể:** Đối chiếu tin mới quét với bảng `jobs` thông qua mã định danh nguồn hoặc đường dẫn chuẩn hóa.
2. **Xử lý tin mới (NEW):** Nếu chưa tồn tại, chèn bản ghi mới vào bảng `jobs` (trạng thái `NEW`) và tạo snapshot đầu tiên trong bảng `job_snapshots`.
3. **Xử lý cập nhật nội dung (UPDATED):** Nếu đã tồn tại nhưng mã băm nội dung (`content_hash`) thay đổi, tiến hành đóng hiệu lực snapshot cũ và tạo snapshot mới, đồng thời chuyển trạng thái tin chính sang `UPDATED` và ghi nhận sự kiện vào `job_events`.
4. **Xử lý tin biến mất (NOT_FOUND / CLOSED):** Với các tin đang hoạt động nhưng không thấy trong lượt quét mới:
   - Tăng số lần không tìm thấy `not_found_count` thêm 1.
   - Nếu chạm ngưỡng 3 lần liên tiếp, chuyển trạng thái tin sang `CLOSED` và tắt cờ hoạt động.
5. **Xử lý hết hạn (EXPIRED):** Chuyển trạng thái sang `EXPIRED` đối với các tin có ngày hết hạn nhỏ hơn ngày hiện tại hoặc trang chi tiết báo hết hạn.
6. **Xử lý đăng lại (REOPENED):** Nếu tin đã đóng xuất hiện lại trong vòng 14 ngày, kích hoạt lại trạng thái hoạt động.

#### Phân tích sự cần thiết của mô hình chuẩn hóa 3NF trong bài toán tuyển dụng
Một câu hỏi thiết kế quan trọng là: *Hệ thống có thực sự cần một lớp cơ sở dữ liệu nghiệp vụ chuẩn hóa 3NF (Silver Schema) hay có thể đi trực tiếp từ file phẳng Parquet lên kho dữ liệu?* 

Dưới đây là phân tích chi tiết về sự cần thiết của 3NF trong bài toán này:

##### 1. Bản chất đặc thù của dữ liệu tin tuyển dụng
Khác với dữ liệu bán hàng có các giao dịch cố định và ID hóa đơn rõ ràng, tin tuyển dụng cực kỳ "hỗn loạn" và không ổn định. Một tin tuyển dụng có thể bị đổi tiêu đề, cập nhật lương, đóng tuyển, mở lại, hoặc bị spam trùng lặp trên 3-4 trang web khác nhau.
Nếu chỉ sử dụng mô hình Lakehouse phẳng (Parquet files) và chạy dbt trực tiếp từ Bronze lên Gold:
* **Lỗi đếm phồng số liệu (Bloated Counts):** Khi một tin tuyển dụng xuất hiện trên 3 nguồn khác nhau, hệ thống phân tích sẽ đếm thành 3 cơ hội việc làm thực tế, làm sai lệch nghiêm trọng các báo cáo xu hướng nhu cầu thị trường.
* **Mất dấu lịch sử thay đổi (SCD Type 2):** Khi đơn vị tuyển dụng thay đổi mức lương từ "10M" sang "12M", nếu chỉ cập nhật đè trên file phẳng hoặc phân tích dạng log append-only thông thường, hệ thống sẽ rất khó để truy vấn chính xác "mức lương trung bình tại ngày X là bao nhiêu" và "xu hướng lương tăng/giảm của công việc Y thế nào".
* **Lỗi đóng tin hàng loạt (Mass Closing Anomaly):** Nếu một ngày bộ quét bị lỗi phân trang hoặc bị website chặn, dữ liệu quét hôm đó bị thiếu. Nếu không có một hệ quản trị trạng thái lưu vết như `not_found_count` trong database nghiệp vụ, hệ thống dbt incremental sẽ hiểu nhầm các tin thiếu đó đã bị đóng và xóa/đánh dấu đóng hàng loạt tin đang hoạt động.

##### 2. Vai trò của lớp chuẩn hóa 3NF
Thiết kế Silver Schema theo chuẩn 3NF (với các thực thể tách biệt như `jobs`, `job_snapshots`, `companies`, `company_aliases`, `job_events`) mang lại các giá trị cốt lõi:
* **Single Source of Truth (SSOT):** Đóng vai trò là nguồn sự thật duy nhất về mặt nghiệp vụ tuyển dụng. Hệ thống có thể truy vấn trạng thái hiện tại của bất kỳ tin tuyển dụng nào một cách nhanh nhất mà không cần quét lại toàn bộ lịch sử dữ liệu.
* **Tối ưu hóa lưu trữ lịch sử:** Tách thông tin định danh tĩnh (`jobs`) khỏi thông tin biến động (`job_snapshots`) giúp tránh nhân bản các trường văn bản dài (như mô tả công việc) khi chỉ thay đổi một trường nhỏ như mức lương hay hạn nộp hồ sơ.
* **Nhất quán danh mục (Data Consistency):** Giải quyết triệt để bài toán chuẩn hóa tên công ty viết lệch format qua bảng bí danh (`company_aliases`) và chuẩn hóa kỹ năng qua danh mục kỹ năng (`skills`). Nếu dùng file phẳng, việc mapping này sẽ phải thực hiện lại nhiều lần ở nhiều bảng, tăng nguy cơ bất đồng bộ dữ liệu.
* **Khả năng kiểm toán (Auditing):** Bảng `job_events` lưu lại từng sự kiện thay đổi trạng thái (ví dụ: chuyển từ ACTIVE sang CLOSED lúc mấy giờ, do lý do gì). Đây là thông tin vô giá để đội ngũ Data Engineer kiểm tra lỗi của pipeline và tối ưu hóa bộ crawler.

##### 3. Kết luận thiết kế
Đối với một dự án mang tính chất demo hoặc thử nghiệm nhanh (MVP), việc bỏ qua 3NF và đi thẳng bằng dbt snapshots trên file phẳng Parquet có thể chấp nhận được để rút ngắn thời gian phát triển.
Tuy nhiên, đối với một **hệ thống Data Engineering thực tế và chuyên nghiệp**, việc thiết lập lớp cơ sở dữ liệu nghiệp vụ chuẩn hóa 3NF là **cực kỳ cần thiết**. Nó là nền móng vững chắc giúp giải quyết triệt để các vấn đề về chất lượng dữ liệu, loại bỏ trùng lặp chéo, quản lý vòng đời tin một cách an toàn và cung cấp nguồn dữ liệu lịch sử sạch tuyệt đối cho Data Warehouse và các phân vùng Data Marts phía sau.

### 4.6 Các tác vụ làm sạch, chuẩn hóa và khử trùng lặp (Từ cơ bản đến phức tạp)

Để dữ liệu thô biến đổi thành dữ liệu nghiệp vụ sạch tuyệt đối trong schema `silver`, pipeline thực thi một chuỗi các tác vụ được phân loại theo độ phức tạp tăng dần:

#### 1. Các tác vụ cơ bản (Basic Tasks)
* **Kiểm tra dữ liệu rỗng và lọc bỏ (Null filtering):** Loại bỏ các bản ghi bị rỗng các trường thông tin bắt buộc phải có để định danh tin tuyển dụng như: tiêu đề công việc, đường dẫn nguồn, mã nguồn tuyển dụng.
* **Làm sạch chuỗi ký tự (String trimming & HTML removal):** Cắt bỏ khoảng trắng thừa ở hai đầu chuỗi, loại bỏ các thẻ HTML rác còn sót lại trong tiêu đề hoặc mô tả, quy đổi các thực thể HTML mã hóa (như `&amp;` thành `&`).
* **Quy đổi kiểu dữ liệu (Type casting):** Ép kiểu các chuỗi văn bản ngày tháng thô thu thập được từ web thành kiểu DATE chuẩn, các trường thông tin số lượng (kinh nghiệm, lương) thành kiểu số nguyên (INT) hoặc số thực (NUMERIC).
* **Loại bỏ tham số URL (URL cleaning):** Cắt bỏ tất cả các tham số truy vấn quảng cáo và theo dõi chiến dịch (như `utm_source`, `utm_medium`, `ref`, `fbclid`) để tạo ra đường dẫn chuẩn hóa (`canonical_url`) duy nhất.

#### 2. Các tác vụ trung bình (Intermediate Tasks)
* **Phân tích mức lương (Salary parsing):** Sử dụng các biểu thức chính quy (Regex) và logic chia nhánh để tách chuỗi lương tự do thành: mức lương tối thiểu (VND), mức lương tối đa (VND) và cờ đánh dấu lương thỏa thuận/cạnh tranh. Xử lý quy đổi các đơn vị tiền tệ ngoại tệ (USD sang VND) theo tỷ giá quy định.
* **Chuẩn hóa địa điểm (Location mapping):** Ánh xạ văn bản địa điểm tự do từ nguồn tin về danh sách thành phố chuẩn hóa (ví dụ: quy đổi "Ha Noi", "HN", "Hà Nội" về một chuỗi chuẩn "Hà Nội").
* **Tính toán số năm kinh nghiệm (Experience mapping):** Quy đổi các văn bản yêu cầu kinh nghiệm thô thành số năm kinh nghiệm tối thiểu dạng số để phục vụ tính toán.
* **Bí danh và chuẩn hóa tên công ty (Company alias resolution):** Lọc bỏ các tiếp vĩ ngữ pháp lý (như TNHH, Cổ phần, Co Ltd, JSC) và sử dụng bảng bí danh (`company_aliases`) để quy đổi tất cả các cách viết tên khác nhau của doanh nghiệp về một ID công ty duy nhất.

#### 3. Các tác vụ phức tạp (Complex Tasks)
* **Làm sạch tiêu đề tiếp thị (Marketing/SEO word removal):** Tự động phát hiện và cắt bỏ các từ ngữ quảng cáo, tiếp thị rác trong tiêu đề tin tuyển dụng (như "Tuyển gấp", "Lương cao đi làm ngay", "Thu nhập khủng", "Cơ hội hấp dẫn") để thu về tiêu đề chuyên môn sạch sẽ.
* **Trích xuất kỹ năng công nghệ nâng cao (Advanced skills extraction):** Sử dụng bộ lọc biểu thức chính quy nâng cao kết hợp từ điển kỹ năng để trích xuất danh sách các từ khóa công nghệ (Python, SQL, AWS, Airflow...) từ mô tả công việc. Có logic loại trừ từ ngữ phủ định (ví dụ mô tả ghi "không yêu cầu Java" thì Java không được trích xuất).
* **Gom cụm trùng lặp chéo nguồn (Cross-source deduplication):** Áp dụng thuật toán tính toán độ tương đồng mô tả công việc (TF-IDF Cosine Similarity) giữa các tin của cùng một công ty tại các nguồn tuyển dụng khác nhau để liên kết chúng vào một nhóm trùng lặp (`duplicate_groups`).
* **Phát hiện mâu thuẫn yêu cầu (Conflict requirement flag):** Phân tích sự mâu thuẫn giữa tiêu đề bài đăng (ví dụ ghi "Intern" hoặc "Fresher") với nội dung yêu cầu kinh nghiệm trong mô tả (yêu cầu trên 2 năm kinh nghiệm). Nếu phát hiện mâu thuẫn, gắn cờ cảnh báo chất lượng dữ liệu để điều chỉnh điểm thân thiện với sinh viên.
* **Phân loại nhóm ngành nghề (Job Family classification):** Sử dụng bộ phân loại quy tắc (Rule-based classifier) để tự động gán tin tuyển dụng vào các nhóm công việc chuẩn (Data Engineer, Data Analyst, Software Engineer...) và loại bỏ các tin tuyển dụng không thuộc nhóm ngành CNTT lọt vào do trùng từ khóa (ví dụ: nhân viên nhập liệu - data entry).

---

## 5. Tầng 3 — Gold (Warehouse + Marts)

### 5.1 Triết lý: Star Schema + Mart-per-consumer

Gold là tầng cuối cùng trong data lake, là nơi dữ liệu đã sẵn sàng để business sử dụng. Thiết kế theo **Star Schema** với Fact table ở trung tâm và các Dimension table xung quanh.

Thay vì có một Warehouse duy nhất, Gold được tổ chức thêm các **Data Mart** — mỗi mart được tối ưu riêng cho một consumer cụ thể. Cùng một dữ liệu, Power BI cần dạng aggregate nhỏ gọn, FastAPI cần flat table đã JOIN sẵn, ML cần feature vector — mỗi mart phục vụ đúng nhu cầu đó.

### 5.2 Dimension tables

**`dim_date`:** Bảng ngày cố định, generated một lần từ 2020 đến 2030, bao gồm tất cả thuộc tính thời gian: năm, tháng, tuần, ngày trong tuần, quý, flag cuối tuần, flag ngày lễ Việt Nam. Đây là một bảng tĩnh (materialized table), không cần incremental.

**`dim_company`** (SCD Type 2): Công ty có thể thay đổi quy mô, ngành nghề, địa chỉ theo thời gian. SCD Type 2 lưu lịch sử thay đổi bằng cách thêm row mới với `valid_from/valid_to` thay vì overwrite. Được implement qua **dbt snapshot** — dbt tự động phát hiện thay đổi trong các cột được chỉ định (`industry`, `company_size`) và tạo bản ghi lịch sử.

Ngoài ra, company được phân loại vào `size_category`: Startup (1–10), Small (11–50), Medium (51–200), Medium-Large (201–500), Enterprise (500+).

**`dim_skill`** (SCD Type 1 — overwrite): Skill ít thay đổi và lịch sử thay đổi không quan trọng. Join với seed `dim_skill_mapping.csv` để chuẩn hóa: "nodejs", "node.js", "Node JS" → đều về "Node.js", và phân loại vào `skill_category` (Language, Framework, Cloud, Database, Tool, Soft Skill) + `skill_subcategory`.

**`dim_location`:** Danh sách các địa điểm chuẩn hóa với tọa độ GPS để sau này dùng cho map visualization trong Power BI.

### 5.3 Fact tables

**`fct_job_posting`** (incremental, partition by `posted_date_key`): Fact table trung tâm, mỗi row là một job posting unique. Chứa tất cả các foreign key đến dimensions, các measure số (`salary_min_vnd`, `salary_max_vnd`, `salary_midpoint_vnd`, `days_to_deadline`), và các flag boolean (`is_new_this_week`, `is_still_open`, `has_salary_info`). Chạy `ANALYZE` sau mỗi lần merge để DuckDB có statistics mới nhất cho query optimizer.

**`fct_job_skill`** (bridge table, incremental): Bảng trung gian giải quyết quan hệ nhiều-nhiều giữa job và skill. Mỗi row là một cặp `(global_job_id, skill_key)` kèm `skill_position` (vị trí skill trong danh sách) và flag `is_primary_skill` (3 skill đầu tiên). Bảng này là nền tảng cho các phân tích skill demand, skill co-occurrence, và recommendation.

### 5.4 Data Mart cho Power BI (`mart_bi/`)

Các model trong mart này là các bảng aggregate nhỏ gọn, được tính toán sẵn, Power BI chỉ cần đọc và visualize mà không cần tính toán thêm. Tất cả là `materialized='table'` (full refresh hàng ngày vì nhỏ).

- **`agg_demand_trend`:** Số lượng job theo skill × thành phố × tháng. Đây là dataset chính cho biểu đồ xu hướng tuyển dụng theo thời gian.
- **`agg_salary_by_skill`:** Trung bình, trung vị, phân vị 25/75 của salary theo skill và level kinh nghiệm. Dùng cho biểu đồ so sánh mức lương.
- **`agg_jobs_by_city`:** Số lượng job đang mở, mới trong tuần, theo thành phố — dùng cho map chart và tổng quan thị trường.
- **`kpi_daily_summary`:** Một row mỗi ngày với các KPI tổng hợp: tổng job mới, tổng job đang mở, số source active, tỉ lệ job có salary, v.v. Dùng cho dashboard KPI overview.

### 5.5 Data Mart cho FastAPI (`mart_api/`)

Thiết kế nguyên tắc: **denormalize hoàn toàn** để API chỉ cần scan một bảng, không cần JOIN runtime.

- **`latest_jobs_flat`:** Mỗi row là một job đầy đủ thông tin — job title, company, location, salary display string, skills dưới dạng array, job type, experience, deadline, flags. Chỉ giữ các job `is_still_open = true`. Đây là bảng chính cho endpoint `GET /jobs`.
- **`company_profiles`:** Thông tin công ty tổng hợp: số job đang đăng, mức lương trung bình, top skills, lịch sử tuyển dụng.
- **`skill_stats`:** Thống kê mỗi skill: số job yêu cầu, mức lương trung bình, thành phố có nhiều nhu cầu nhất, xu hướng 30 ngày so với 30 ngày trước (tăng hay giảm %).

### 5.6 Data Mart cho ML (`mart_ml/`)

- **`job_features`:** Feature table đầy đủ cho model training. Mỗi row là một job với tất cả features đã được biến đổi: binary flags cho từng skill quan trọng, encoded categorical features (location, job_type, industry, company_size_category), temporal features (tháng đăng, ngày trong tuần). Chỉ giữ records có `salary_midpoint_vnd` không null để làm training data cho salary prediction.
- **`skill_cooccurrence`:** Ma trận co-occurrence giữa các skill — skill A và skill B thường xuất hiện cùng nhau bao nhiêu lần. Dùng cho recommendation "nếu bạn biết Python thì cũng nên học SQL, Airflow...".
- **`salary_prediction_input`:** Subset của `job_features` với feature selection tối ưu cho salary prediction model, bao gồm cả label `salary_target`.

---

## 6. Tầng 4 — Serving Layer

### 6.1 FastAPI — Web API

FastAPI là lớp phục vụ dữ liệu cho ứng dụng web frontend và mobile. Thiết kế stateless, scale ngang, và có caching.

**DuckDB singleton service:** Một DuckDB connection duy nhất được khởi tạo khi server start, kết nối tới Floci S3, tạo sẵn các view trỏ vào Gold Parquet files. Mọi request đều dùng chung connection này. DuckDB đọc Parquet trực tiếp từ S3 rất nhanh nên không cần import vào database riêng.

**Các endpoints chính:**
- `GET /jobs` với filter theo city, skill, salary, job_type, page
- `GET /jobs/{id}` lấy chi tiết một job
- `GET /companies/{name}` profile công ty
- `GET /skills/trending` skill đang tăng nhanh nhất
- `POST /search` full-text search qua Elasticsearch
- `POST /recommend` gợi ý jobs tương tự dựa trên content-based filtering

**Caching:** Các query phổ biến (danh sách job mặc định, skill trending) được cache trong Redis với TTL 30 phút. Sau mỗi pipeline chạy xong, Airflow trigger một task xóa cache để data mới được serve ngay.

**Authentication:** Mọi endpoint đều yêu cầu API key qua header `X-API-Key`. Middleware kiểm tra key trước khi request đến router.

**Rate limiting:** Mỗi API key bị giới hạn 100 requests/phút để tránh abuse.

### 6.2 Power BI

Power BI kết nối với DuckDB qua Python connector trong Power Query. Script Python chạy DuckDB query đọc Parquet từ S3 và trả về DataFrame. Power BI scheduled refresh chạy hàng ngày sau khi Airflow pipeline hoàn thành.

Dữ liệu cho Power BI đến từ `mart_bi` — các bảng đã aggregate sẵn nên refresh rất nhanh (vài giây). Power BI không cần query trực tiếp fact table lớn.

**Các dashboard chính:**
- Overview: tổng số jobs đang mở, mới hôm nay, theo thành phố
- Skill demand: top skills theo lượt tuyển dụng, xu hướng theo thời gian
- Salary benchmark: so sánh salary theo skill, level, thành phố
- Source analysis: hiệu suất từng portal (số job, chất lượng, tỉ lệ có salary)

---

## 7. Tầng 5 — AI/ML & Search

### 7.1 Elasticsearch — Full-text Search

Elasticsearch (ES) là search engine chuyên biệt, phục vụ use case tìm kiếm nhanh theo text và các filter phức tạp mà DuckDB không tối ưu bằng.

**Index design:** Mỗi job là một document trong ES. Các trường text như `job_title` và `company` được index với analyzer tiếng Việt (xử lý dấu, tokenize phù hợp). Các trường categorical như `location`, `skills`, `job_type` dùng `keyword` type để filter chính xác. Ngoài ra, có một `dense_vector` field 768 chiều lưu embedding của job description cho semantic search.

**Settings tối ưu:** Index config với `number_of_replicas=0` trong môi trường local (không cần HA), `refresh_interval=30s` thay vì mặc định 1s — giảm overhead khi bulk indexing.

**Sync Gold → ES:** Airflow chạy một task sau khi Gold mart build xong, đọc `latest_jobs_flat` từ Parquet và bulk index vào ES. Chỉ sync records có `_gold_processed_at` mới hơn lần sync cuối (incremental). Dùng ES Bulk API với batch_size=500 để tối ưu throughput.

**Full-text search API:** Endpoint `POST /search` nhận query text và các filter, xây dựng ES query với multi-match (`job_title^3`, `skills^2`, `company^1` — boosting theo độ quan trọng), fuzziness để chịu lỗi chính tả, và filter phần boolean. Kết quả có highlighting để frontend bold phần match.

### 7.2 Semantic Search — RAG

**Embedding generation:** Dùng Vietnamese SBERT model (`keepitreal/vietnamese-sbert`) để tạo vector embedding 768 chiều cho mỗi job. Text input là concatenation của `job_title + skills + industry + location`. Model chạy batch encode (64 records/batch) với `normalize_embeddings=True` để dùng cosine similarity. Airflow chạy embedding task hàng tuần (không cần hàng ngày vì compute nặng).

**KNN Vector Search:** Khi user nhập query kiểu "tìm việc data engineer remote lương cao", hệ thống encode query này thành vector, rồi dùng ES KNN search tìm `k` job gần nhất về cosine similarity. Kết hợp lexical search (BM25) và vector search (ANN) cho kết quả tốt nhất.

**RAG pipeline:** Người dùng hỏi câu như "Tôi biết Python và SQL, nên học thêm gì để lương tăng?". Hệ thống dùng retriever để tìm các job phù hợp từ ES, rồi đưa context đó vào LLM để tạo câu trả lời có căn cứ từ dữ liệu thực tế.

### 7.3 Recommendation System

**Content-based filtering:** Dựa trên skill similarity. Mỗi job được biểu diễn bằng TF-IDF vector của skills. Cosine similarity giữa hai job vector cho biết độ tương tự. Khi user xem một job, hệ thống tìm `k` job có vector gần nhất để gợi ý.

**Salary Prediction:** Model regression (Gradient Boosting hoặc XGBoost) trained trên `mart_ml/salary_prediction_input`. Features: skill flags, location, industry, company_size, experience_years, job_type. Predict salary range cho jobs không có thông tin lương. Airflow train lại model hàng tuần.

**Weekly ML DAG:** Một DAG riêng chạy mỗi Chủ nhật: load `mart_ml/job_features`, train TF-IDF model cho recommendation, train salary prediction model, lưu model artifacts vào S3 (`s3://jobit-models/`), cập nhật embeddings mới cho jobs trong tuần.

---

## 8. Orchestration — Airflow

### 8.1 Triết lý orchestration

Airflow là bộ não điều phối toàn bộ pipeline. Mỗi task là một đơn vị nhỏ nhất có thể retry độc lập. Khi một task fail, chỉ task đó được retry, không chạy lại toàn bộ pipeline.

### 8.2 Các DAG chính

**`daily_job_pipeline`** (6h sáng mỗi ngày): DAG chính, chạy toàn bộ pipeline ELT hàng ngày theo sequence:
1. Extract song song tất cả sources
2. S3KeySensor — chờ Bronze có data (timeout 5 phút)
3. dbt Silver: staging → intermediate (tuần tự)
4. dbt test Silver — fail fast, không tiếp tục nếu có data quality issue
5. dbt Gold: snapshots → warehouse → marts (tuần tự)
6. dbt test Gold
7. Sync song song: Elasticsearch + cache invalidation

**`weekly_ml_training`** (Chủ nhật 2h sáng): Train lại recommendation model, salary prediction model, cập nhật embeddings.

**`monthly_full_refresh`** (Ngày 1 mỗi tháng 3h sáng): Full refresh `dim_date` và các dimension nhỏ để đảm bảo tính nhất quán. Chạy tất cả dbt tests một lần toàn bộ.

### 8.3 Cơ chế an toàn

**`max_active_runs=1`:** Không bao giờ chạy song song hai ngày cùng lúc. Nếu ngày hôm nay fail và chưa xong, ngày mai sẽ không start.

**`depends_on_past=False`:** Mỗi ngày chạy độc lập. Nếu hôm qua fail, hôm nay vẫn chạy bình thường.

**Data quality gate:** Airflow không tiến sang bước Gold nếu Silver tests fail. Đây là guardrail quan trọng để tránh đẩy bad data vào production.

**On-failure callback:** Mọi DAG đều có callback gửi Slack alert kèm link log khi task nào đó fail.

**SLA miss alert:** Nếu `daily_job_pipeline` chưa hoàn thành sau 3 tiếng, Airflow gửi SLA miss alert.

---

## 9. Lượng tử hóa & Đo lường hiệu suất vận hành

> **Mục đích:** Biết chính xác pipeline đang chạy như thế nào, phần nào là bottleneck, và tối ưu hóa có thực sự hiệu quả không — thay vì phỏng đoán.

### 9.1 Triết lý đo lường

Đo lường phải diễn ra **tự động, liên tục, và gắn liền với pipeline** — không phải việc chạy benchmark riêng. Mỗi lần pipeline chạy là một lần thu thập metrics. Theo thời gian, ta có lịch sử để so sánh và phát hiện regression (hiệu suất tệ đi sau một thay đổi nào đó).

Có 4 loại metrics quan trọng:

| Loại | Ví dụ | Câu hỏi trả lời |
|---|---|---|
| **Thời gian (Latency)** | Thời gian mỗi task, mỗi tầng | Task nào chậm nhất? |
| **Khối lượng (Volume)** | Số records, kích thước file | Hôm nay scrape được bao nhiêu? |
| **Chất lượng (Quality)** | Tỉ lệ reject, null rate | Dữ liệu có tốt không? |
| **Tài nguyên (Resource)** | RAM, CPU, S3 storage | Hệ thống đang chịu tải như thế nào? |

### 9.2 Metrics tầng Extract (Tầng 0)

**Scrape metrics — ghi vào metadata file Bronze:**

- `total_scraped`: tổng records thu thập được từ scraper
- `total_validated`: số records qua Pydantic validate
- `total_rejected`: số records bị reject (và lý do reject theo category)
- `rejection_rate_pct`: `(total_rejected / total_scraped) * 100` — nếu > 10% cần review scraper
- `scrape_duration_seconds`: thời gian toàn bộ scraping session
- `avg_time_per_record_ms`: thời gian trung bình xử lý 1 record
- `pages_scraped`: số trang listing đã duyệt
- `proxy_errors`: số lần proxy bị block/timeout
- `retry_count`: tổng số lần retry (nếu cao = website đang anti-bot mạnh hơn)

**Ngưỡng cảnh báo:**
- `rejection_rate > 15%` → scraper có thể bị thay đổi format HTML
- `scrape_duration > 90 phút` → có thể proxy đang chậm, cần review
- `total_scraped < 100` → source có thể bị block hoàn toàn

**Nơi lưu:** File `.meta.json` kèm mỗi Bronze JSONL, và Airflow task log.

### 9.3 Metrics tầng Silver — dbt Staging (Tầng 2)

**Volume metrics:**

- `rows_inserted`: số records mới được thêm vào staging table trong lần chạy này
- `rows_updated`: số records bị update (do incremental merge)
- `rows_processed_total`: tổng records đã xử lý (kể cả filtered out)
- `dedup_removed_count`: số records bị loại bởi deduplication (trong `int_deduped_jobs`)
- `cross_source_overlap_pct`: % jobs xuất hiện trên nhiều hơn 1 portal

**Quality metrics:**

- `null_rate_per_column`: % null của từng cột quan trọng (salary, location, skills, posted_date)
- `salary_parse_success_rate`: % records salary_raw được parse thành công ra số
- `skill_array_avg_length`: trung bình số skills mỗi job listing — nếu giảm đột ngột có thể scraper bị lỗi
- `invalid_date_count`: số `posted_date` không parse được sang DATE
- `changed_jobs_count`: số jobs bị detect thay đổi nội dung (từ `int_changed_jobs`)

**Performance metrics:**

- `dbt_model_duration_seconds`: thời gian execute từng dbt model — lấy từ `dbt run` output JSON (`run_results.json`)
- `bytes_read_from_bronze`: lượng data đọc từ S3 Bronze (đo qua DuckDB profiling)
- `bytes_written_to_silver`: kích thước Parquet output

**Lấy metrics từ dbt:** Sau mỗi `dbt run`, file `dbt_jobitvn/target/run_results.json` chứa `execution_time`, `rows_affected`, và `status` cho từng model. Một Python script nhỏ parse file này và push metrics vào bảng monitoring.

### 9.4 Metrics tầng Gold — Warehouse & Marts (Tầng 3)

**Fact table health:**

- `fct_job_posting_total_rows`: tổng số records trong fact table (tăng mỗi ngày)
- `fct_job_posting_new_today`: số job mới thêm hôm nay
- `active_jobs_count`: số jobs `is_still_open = true`
- `avg_salary_midpoint_vnd`: mức lương trung bình — nếu thay đổi đột ngột cần kiểm tra
- `jobs_with_salary_pct`: % jobs có thông tin lương (KPI chất lượng data)

**Dimension health:**

- `dim_company_scd_changes_today`: số lần SCD Type 2 tạo bản ghi mới (công ty đổi thông tin)
- `dim_skill_total_distinct`: tổng số skill unique — tăng tự nhiên theo thời gian
- `new_skills_this_week`: skill mới xuất hiện trong tuần (chỉ số trend)

**Mart freshness:**

- `mart_bi_last_built_at`: timestamp lần cuối mart_bi được rebuild
- `mart_api_row_count`: số records trong `latest_jobs_flat` — so sánh với `active_jobs_count`
- `lag_bi_vs_gold_minutes`: chênh lệch thời gian giữa Gold và mart_bi built

**Performance:**

- `gold_build_duration_seconds`: thời gian build toàn bộ Gold layer
- `fct_job_posting_scan_mb`: MB data DuckDB phải scan để build fact table (giảm nhờ partitioning)
- `partition_pruning_efficiency`: % partitions được skip nhờ predicate pushdown

### 9.5 Metrics tầng Serving — API & Power BI (Tầng 4)

**API performance:**

- `p50_response_time_ms`, `p95_response_time_ms`, `p99_response_time_ms`: phân vị latency
- `requests_per_minute`: throughput
- `cache_hit_rate_pct`: % requests được serve từ cache — nếu thấp (<50%) cần review TTL
- `duckdb_query_duration_ms`: thời gian DuckDB thực thi query trong mỗi request
- `error_rate_pct`: % requests trả về 4xx/5xx

**DuckDB serving health:**

- `parquet_files_scanned_per_query`: số files Parquet phải đọc — giảm nhờ partition pruning
- `bytes_scanned_per_query_mb`: data scan per query — chỉ số tốt cho columnar efficiency
- `memory_peak_mb`: peak memory DuckDB dùng khi execute query

**Power BI:**

- `refresh_duration_minutes`: thời gian Power BI dataset refresh
- `rows_loaded`: số rows load vào Power BI per table

### 9.6 Metrics tầng Search & ML (Tầng 5)

**Elasticsearch:**

- `es_index_size_gb`: kích thước index
- `es_docs_total`: tổng số documents indexed
- `bulk_indexing_duration_seconds`: thời gian bulk sync Gold → ES
- `bulk_indexing_throughput_docs_per_sec`: tốc độ indexing
- `search_query_latency_p95_ms`: latency search query ở percentile 95
- `embedding_generation_duration_minutes`: thời gian tạo embeddings cho toàn bộ jobs

**ML metrics:**

- `recommendation_model_accuracy`: độ chính xác model trên validation set
- `salary_prediction_mae_vnd`: Mean Absolute Error của salary prediction (triệu VND)
- `training_duration_minutes`: thời gian train model
- `model_artifact_size_mb`: kích thước file model

### 9.7 Pipeline-level Metrics — Airflow

**SLA tracking:**

- `pipeline_total_duration_minutes`: tổng thời gian từ start đến end của DAG
- `task_duration_by_name`: duration từng task — phát hiện task nào chiếm nhiều thời gian nhất
- `pipeline_success_rate_30d`: tỉ lệ thành công trong 30 ngày — KPI reliability

**Data freshness SLA:**

- `bronze_latest_ingestion_lag_hours`: số giờ kể từ lần Bronze nhận data cuối
- `gold_freshness_hours`: số giờ kể từ Gold được rebuild lần cuối
- `es_sync_lag_hours`: chênh lệch giữa Gold build và ES sync xong

### 9.8 Bảng monitoring tập trung

Tạo một bảng `pipeline_run_metrics` trong DuckDB (persistent, không trong S3) để lưu metrics mỗi lần chạy. Airflow task cuối cùng trong DAG (`collect_metrics`) parse dbt `run_results.json`, đọc Airflow XCom từ các task trước, và insert một row vào bảng này.

**Schema bảng:**

| Cột | Ý nghĩa |
|---|---|
| `run_id` | Airflow run ID (unique) |
| `run_date` | Ngày chạy |
| `layer` | Tên tầng: 'extract', 'silver', 'gold', 'serving', 'ml' |
| `metric_name` | Tên metric |
| `metric_value` | Giá trị số |
| `metric_unit` | Đơn vị: 'seconds', 'rows', 'bytes', 'pct' |
| `recorded_at` | Timestamp ghi nhận |

Dùng DuckDB query hoặc Power BI để visualize lịch sử metrics này — tạo dashboard "Pipeline Health".

### 9.9 Dashboard Pipeline Health — Power BI

Một trang Power BI riêng cho engineering team (không phải business users) hiển thị:

- **Trend biểu đồ:** Pipeline duration theo ngày — phát hiện trend tăng dần (data grows → slower?)
- **Bar chart:** Duration từng task — bottleneck identification
- **KPI cards:** Data freshness, success rate 7 ngày, active jobs count
- **Table:** Rejection rate theo source — source nào đang có vấn đề
- **Alert markers:** Ngày nào có SLA miss hoặc data quality fail

### 9.10 Phán đoán tối ưu từ metrics

Bảng dưới mô tả cách đọc metrics để ra quyết định:

| Metric | Giá trị → Vấn đề | Giải pháp |
|---|---|---|
| `dbt_model_duration > 5 phút` | Model quá chậm | Kiểm tra partition pruning, thêm index |
| `rejection_rate > 15%` | Scraper lỗi hoặc site thay format | Review HTML parser của source đó |
| `null_rate_salary > 70%` | Salary parsing fail | Cập nhật regex pattern |
| `cache_hit_rate < 40%` | Cache không hiệu quả | Tăng TTL, review cache key design |
| `bytes_scanned_per_query > 500MB` | Partition pruning không hoạt động | Kiểm tra lại WHERE clause có dùng partition key không |
| `pipeline_duration > 3h` | Tổng pipeline quá chậm | Tăng parallelism, review bottleneck task |
| `es_search_p95 > 500ms` | Search chậm | Kiểm tra ES heap, index sharding |
| `salary_mae > 5 triệu` | ML model kém | Thu thập thêm training data, tune hyperparams |

---

## 10. Kỹ thuật tối ưu DE tổng hợp

### 10.1 Storage Optimization — Parquet + Snappy

Parquet là định dạng columnar — thay vì lưu row-by-row như CSV/JSON, dữ liệu được nhóm theo cột. Khi query chỉ cần 5 cột trong bảng 50 cột, Parquet chỉ đọc 5 cột đó, bỏ qua 45 cột còn lại. Kết hợp với Snappy compression, file nhỏ hơn JSON khoảng 5–8 lần.

**Quy tắc:** Bronze = JSONL (giữ nguyên raw), Silver trở lên = Parquet Snappy. Không dùng Gzip cho Parquet dù nén tốt hơn Snappy vì Gzip không splittable — ảnh hưởng parallel read.

### 10.2 Partitioning — Predicate Pushdown

Cấu trúc S3 path `year=/month=/day=/` cho phép DuckDB và Spark bỏ qua các partition không liên quan mà không cần đọc. Khi query `WHERE posted_date >= '2026-06-01'`, DuckDB chỉ scan từ partition `month=06` trở đi, bỏ qua toàn bộ 5 tháng trước.

**Nguyên tắc chọn partition key:** Chọn trường thường xuất hiện trong WHERE clause của query phổ biến nhất. Với job data, `posted_date` là lựa chọn tự nhiên vì hầu hết query đều lọc theo ngày gần đây.

### 10.3 Incremental Load — Không Full Refresh Hàng Ngày

Toàn bộ staging và fact models đều chạy incremental với strategy `merge`. Chỉ xử lý records có `_scraped_at` mới hơn `MAX(_scraped_at)` trong bảng hiện tại. Với 500 jobs/ngày và tổng 50,000 jobs, incremental chỉ xử lý 1% data mỗi ngày thay vì toàn bộ.

### 10.4 SCD Type 2 — Lịch sử thay đổi Dimension

Thay vì overwrite khi công ty thay đổi thông tin, dbt snapshot tự động thêm row mới với `valid_from = hôm nay` và đóng bản ghi cũ bằng `valid_to = hôm nay`. Query luôn join với `WHERE is_current = true` để lấy bản hiện tại. Dùng `WHERE valid_from <= some_date AND valid_to > some_date` để point-in-time analysis.

### 10.5 Content Hash — Pseudo-CDC

Vì nguồn dữ liệu là web scraping (không phải database có CDC), ta dùng content hash làm giải pháp thay thế: hash một số trường quan trọng của mỗi record. Nếu hash của cùng `job_id` thay đổi giữa hai lần scrape, job đó đã được cập nhật. Kỹ thuật này cho phép track salary change, requirements change mà không cần Debezium hay Kafka.

### 10.6 DuckDB Query Optimization

DuckDB tự động thực hiện nhiều tối ưu: predicate pushdown (đẩy filter xuống file scan level), projection pushdown (chỉ đọc cột cần thiết), vectorized execution (xử lý batch rows thay vì từng row), và parallel query execution (multi-threaded). Để tận dụng tối đa:

- Luôn dùng partition key trong WHERE clause khi có thể
- Tránh `SELECT *` trong production queries — chỉ select cột cần thiết
- Chạy `ANALYZE` sau mỗi merge lớn để DuckDB có statistics mới nhất
- Set `memory_limit` và `threads` phù hợp với máy chủ

### 10.7 dbt Macros — Tái sử dụng Logic

Thay vì copy-paste logic parse salary hay normalize location vào 11 staging models, gói chúng thành dbt macros (tương đương stored procedures trong SQL). Macro được gọi bằng Jinja syntax trong SQL và được compile trước khi chạy. Ưu điểm: sửa một chỗ, áp dụng cho tất cả.

### 10.8 Elasticsearch Optimization

Index được tạo với `refresh_interval=30s` thay vì mặc định 1s — trong quá trình bulk indexing, tắt refresh hoàn toàn rồi bật lại sau, tăng tốc indexing 5–10 lần. Sau khi index xong, chạy `_forcemerge` để giảm số segments, cải thiện search performance.

---

## 11. Security & Governance

### 11.1 Credential Management

Tất cả credentials (S3 keys, API keys, Elasticsearch passwords, proxy list) được lưu trong file `.env` và không bao giờ commit lên Git. File `.gitignore` phải bao gồm `.env`, `*.json` raw data, `*.parquet`. Khi deploy lên production cloud, dùng AWS Secrets Manager hoặc Airflow Variables/Connections thay vì file `.env`.

### 11.2 API Security

Mọi endpoint FastAPI đều protected bởi API key middleware. API key được hash và so sánh, không lưu dạng plaintext. Rate limiting ngăn một client gửi quá nhiều requests. Khi cần nhiều cấp độ quyền (public vs internal), dùng JWT token với claims.

### 11.3 Data Lineage

dbt tự động build lineage graph — biểu đồ DAG hiển thị mỗi model phụ thuộc vào nguồn nào. Chạy `dbt docs generate` và `dbt docs serve` để xem lineage qua web UI tại port 8081. Đây là công cụ không thể thiếu khi debug data issue: truy ngược từ mart bị sai về tận Bronze source.

### 11.4 Data Quality Governance

dbt tests là tầng đầu tiên của data governance. Kết quả test được lưu trong Airflow log và có thể query qua `dbt test --store-failures` (lưu records bị fail vào table riêng). Theo thời gian, thêm custom tests cho business rules phức tạp hơn.

### 11.5 Alerting

Slack webhook nhận alert khi: task Airflow fail, dbt test fail, rejection rate vượt ngưỡng, SLA miss. Alert message bao gồm DAG name, task name, error message, và link trực tiếp đến Airflow log. Không dùng email vì chậm và dễ bỏ sót.

---

## 12. Cấu trúc thư mục hoàn chỉnh

```
job_scraper_de_project/
│
├── dags/
│   ├── daily_pipeline.py                  ← DAG chính ELT hàng ngày
│   ├── weekly_ml_training.py              ← Train ML model mỗi tuần
│   ├── monthly_full_refresh.py            ← Full refresh dims mỗi tháng
│   └── utils/
│       ├── slack_alerts.py                ← On-failure Slack notification
│       ├── data_quality_checks.py         ← Custom Airflow sensors
│       └── metrics_collector.py           ← Parse dbt results, push metrics
│
├── dbt_jobitvn/
│   ├── dbt_project.yml
│   ├── profiles.yml                       ← DuckDB → Floci S3 connection
│   ├── models/
│   │   ├── staging/                       ← SILVER: 1 model/source
│   │   │   ├── stg_topcv.sql
│   │   │   ├── stg_itviec.sql
│   │   │   ├── stg_linkedin.sql
│   │   │   ├── stg_vietnamworks.sql
│   │   │   ├── stg_jobsgo.sql
│   │   │   ├── stg_123job.sql
│   │   │   ├── stg_careerviet.sql
│   │   │   ├── stg_careerlink.sql
│   │   │   ├── stg_ybox.sql
│   │   │   ├── stg_jobstreet.sql
│   │   │   ├── stg_joboko.sql
│   │   │   ├── sources.yml               ← Khai báo Bronze S3 sources
│   │   │   └── schema.yml               ← Data tests cho mỗi staging model
│   │   ├── intermediate/
│   │   │   ├── int_all_jobs_unioned.sql  ← UNION ALL 11 sources (ephemeral)
│   │   │   ├── int_deduped_jobs.sql      ← Cross-source dedup (incremental)
│   │   │   ├── int_job_skills_exploded.sql ← Explode skill arrays (ephemeral)
│   │   │   ├── int_changed_jobs.sql      ← Pseudo-CDC: detect thay đổi
│   │   │   └── schema.yml
│   │   └── marts/
│   │       ├── warehouse/               ← GOLD: Star Schema
│   │       │   ├── dim_date.sql
│   │       │   ├── dim_company.sql      ← Đọc từ SCD snapshot
│   │       │   ├── dim_skill.sql
│   │       │   ├── dim_location.sql
│   │       │   ├── fct_job_posting.sql  ← Core fact, incremental
│   │       │   ├── fct_job_skill.sql    ← Bridge table
│   │       │   └── schema.yml
│   │       ├── mart_bi/                 ← Tối ưu cho Power BI
│   │       │   ├── agg_demand_trend.sql
│   │       │   ├── agg_salary_by_skill.sql
│   │       │   ├── agg_jobs_by_city.sql
│   │       │   └── kpi_daily_summary.sql
│   │       ├── mart_api/                ← Tối ưu cho FastAPI
│   │       │   ├── latest_jobs_flat.sql  ← Denormalized, JOIN sẵn
│   │       │   ├── company_profiles.sql
│   │       │   └── skill_stats.sql
│   │       └── mart_ml/                 ← Tối ưu cho ML/AI
│   │           ├── job_features.sql
│   │           ├── skill_cooccurrence.sql
│   │           └── salary_prediction_input.sql
│   ├── snapshots/
│   │   └── scd_company_snapshot.sql     ← SCD Type 2 cho dim_company
│   ├── seeds/
│   │   ├── dim_skill_mapping.csv        ← Chuẩn hóa tên skill
│   │   └── dim_location_mapping.csv     ← Chuẩn hóa tên địa điểm
│   ├── macros/
│   │   ├── parse_salary.sql             ← Macro tái sử dụng (stored proc)
│   │   └── normalize_location.sql
│   └── tests/
│       ├── assert_salary_min_le_max.sql  ← Custom data test
│       └── assert_no_future_postings.sql
│
├── src/
│   ├── extract/
│   │   ├── base/
│   │   │   ├── base_crawler.py          ← Abstract class + retry + rate limit
│   │   │   └── session_manager.py       ← Playwright session pool
│   │   ├── job_online/
│   │   │   ├── topcv.py
│   │   │   ├── itviec.py
│   │   │   ├── linkedin.py
│   │   │   └── ... (11 scrapers)
│   │   └── schemas/
│   │       ├── job_posting.py           ← Pydantic validate schema
│   │       └── reject_log.py
│   ├── aws/
│   │   ├── s3_client.py                 ← boto3 wrapper
│   │   ├── init_s3.py                   ← Tạo buckets lần đầu
│   │   └── exceptions.py
│   ├── serving/
│   │   ├── main.py                      ← FastAPI entry point
│   │   ├── routers/
│   │   │   ├── jobs.py
│   │   │   ├── companies.py
│   │   │   ├── skills.py
│   │   │   └── search.py
│   │   ├── services/
│   │   │   ├── duckdb_service.py        ← DuckDB singleton, query Gold
│   │   │   ├── elasticsearch_service.py ← ES client + sync
│   │   │   └── cache_service.py         ← Redis cache wrapper
│   │   └── middleware/
│   │       ├── auth.py                  ← API key middleware
│   │       └── rate_limit.py
│   └── ml/
│       ├── rag/
│       │   ├── embeddings.py            ← Vietnamese SBERT embedding
│       │   ├── vector_store.py          ← Upload embeddings vào ES
│       │   └── rag_pipeline.py          ← Retriever + LLM
│       └── recommendation/
│           ├── model_trainer.py         ← TF-IDF + cosine sim
│           └── recommender.py           ← Serving inference
│
├── elasticsearch/
│   └── setup/
│       ├── create_index.py              ← Tạo ES index với mapping
│       └── initial_bulk_load.py         ← Load lần đầu toàn bộ jobs vào ES
│
├── monitoring/
│   ├── pipeline_metrics.duckdb          ← DuckDB persistent file lưu metrics
│   └── dashboards/
│       └── pipeline_health.pbix         ← Power BI dashboard engineering
│
├── docs/
│   ├── 10_project_structure.md
│   └── 20_data_platform_blueprint.md   ← File này
│
├── docker-compose.yml                   ← Airflow + Floci + Elasticsearch + Redis
├── .env                                 ← Credentials (không commit)
├── .gitignore
├── requirements.txt
└── run_scrapers_once.py
```

---

## 13. Checklist triển khai theo phase

###  Phase 1 — Foundation (Tuần 1–2)

- [ ] Implement Pydantic validation trong tất cả scrapers (reject queue)
- [ ] Content hash trong mỗi record
- [ ] S3 path convention `year=/month=/day=/` cho Bronze
- [ ] Metadata file `.meta.json` kèm mỗi Bronze file (volume + timing metrics)
- [ ] `schema.yml` với `not_null`, `unique`, `accepted_values` tests
- [ ] dbt staging models cho tất cả 11 sources (incremental)
- [ ] Airflow DAG với TaskGroups và failure alerts

###  Phase 2 — Warehouse (Tuần 3–4)

- [ ] `dim_date` (static table, generate once)
- [ ] `dim_skill` + seed `dim_skill_mapping.csv`
- [ ] `dim_location` + seed `dim_location_mapping.csv`
- [ ] dbt snapshot cho `dim_company` (SCD Type 2)
- [ ] `fct_job_posting` (incremental, partitioned)
- [ ] `fct_job_skill` (bridge table)
- [ ] `int_changed_jobs` (pseudo-CDC)
- [ ] Bảng `pipeline_run_metrics` + task `collect_metrics` trong Airflow

###  Phase 3 — Marts & Serving (Tuần 5–6)

- [ ] `mart_bi`: agg_demand_trend, agg_salary_by_skill, kpi_daily
- [ ] `mart_api`: latest_jobs_flat (denormalized), company_profiles, skill_stats
- [ ] `mart_ml`: job_features, skill_cooccurrence, salary_prediction_input
- [ ] FastAPI với auth, rate limit, /jobs + /search endpoints
- [ ] DuckDB singleton service + Redis cache
- [ ] Power BI connection + Operational dashboard
- [ ] Power BI Pipeline Health dashboard (từ `pipeline_run_metrics`)

###  Phase 4 — AI/ML & Search (Tuần 7–10)

- [ ] Elasticsearch docker service + index creation + bulk load
- [ ] Airflow task: sync Gold → ES (incremental)
- [ ] Full-text search API endpoint với boosting
- [ ] Vietnamese SBERT embeddings + upload dense_vector vào ES
- [ ] KNN semantic search endpoint
- [ ] TF-IDF skill similarity recommendation model
- [ ] Salary prediction model (Gradient Boosting)
- [ ] Weekly ML training DAG
- [ ] RAG pipeline (retriever + LLM integration)
- [ ] Elasticsearch performance metrics (p95 latency, indexing throughput)

---

> **Ghi chú:** Document này là thiết kế tham chiếu. Các quyết định cụ thể về implementation có thể thay đổi dựa trên constraints thực tế về tài nguyên và timeline. Ưu tiên Phase 1 & 2 trước khi nghĩ đến Phase 4.
