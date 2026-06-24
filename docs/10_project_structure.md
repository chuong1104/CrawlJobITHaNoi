# 14. Project Structure (Local AWS Lakehouse)

## 1. Mục tiêu

Kiến trúc thư mục mới được tinh gọn tối đa để phục vụ cho mô hình **ELT (Extract, Load, Transform)** sử dụng Data Lakehouse.

Mục tiêu của cấu trúc:
* **Tách biệt Storage và Compute:** Không lưu dữ liệu rác (JSON, CSV) trong thư mục code. Mọi dữ liệu đẩy thẳng lên Floci S3.
* **Quy hoạch rõ ràng:** Phân biệt rõ phần code cào dữ liệu (Python/Playwright) và phần code xử lý dữ liệu (dbt/SQL).
* **Chuẩn hóa Enterprise:** Thư mục giống hệt cách các công ty công nghệ tổ chức project Data Engineering thực tế.
* **Hỗ trợ Docker và Airflow:** Đóng gói dễ dàng.

---

# 2. Cấu trúc tổng thể

```text
job-it-data-platform/
├── dags/                  # Airflow DAGs (Điều phối)
├── dbt_jobitvn/           # dbt Project (Data Transformation)
├── docs/                  # Tài liệu thiết kế hệ thống
├── logs/                  # Log files của hệ thống
├── plugins/               # Airflow Plugins & Custom Operators
├── src/                   # Mã nguồn Python (Crawler & AWS Utils)
├── tests/                 # Unit Tests cho Python
├── docker-compose.yml     # Khởi chạy toàn bộ hệ thống
├── README.md              # Giới thiệu dự án
├── requirements.txt       # Các thư viện Python
└── run_scrapers_once.py   # Script chạy tất cả scrapers song song cùng lúc
```

---

# 3. Thư mục `src` (Python Layer)

Phần này chỉ chịu trách nhiệm **Extract & Load** (Cào dữ liệu và đẩy lên Data Lake). Không có logic làm sạch dữ liệu ở đây.

```text
src/
├── extract/               # Code thu thập dữ liệu
│   ├── base/              # Các class nền tảng (BaseCrawler)
│   └── job_online/        # Logic cào từng trang cụ thể
│       ├── topcv.py
│       ├── linkedin.py
│       └── itviec.py
└── aws/                   # Các hàm tương tác với AWS S3
    ├── s3_client.py       # Helper functions dùng boto3
    └── exceptions.py
```

*Lưu ý:* Các thư mục cũ như `src/transform` (làm sạch dữ liệu bằng Pandas) hay `src/load` (lưu vào Postgres) đã bị xóa bỏ vì dbt đảm nhận toàn bộ vai trò này.

---

# 4. Thư mục `dbt_jobitvn` (Transformation Layer)

Đây là "bộ não" xử lý dữ liệu của toàn bộ dự án, sử dụng `dbt-duckdb` để biến đổi dữ liệu trên S3.

```text
dbt_jobitvn/
├── models/
│   ├── staging/           # Tầng Silver: Làm sạch, parse salary, format date
│   │   ├── stg_topcv.sql
│   │   └── stg_itviec.sql
│   ├── intermediate/      # Lọc trùng lặp (Deduplication), nối các nguồn
│   │   └── int_deduped_jobs.sql
│   └── marts/             # Tầng Gold: Dimension và Fact tables
│       ├── dim_company.sql
│       ├── dim_skill.sql
│       └── fct_job_posting.sql
├── seeds/                 # Dữ liệu tĩnh (CSV) như danh sách kỹ năng chuẩn
│   └── dim_skill_mapping.csv
├── tests/                 # Các bài test chất lượng dữ liệu (Data Quality)
├── macros/                # Các hàm Jinja tái sử dụng
├── dbt_project.yml        # Cấu hình chính của dbt project
└── profiles.yml           # Thông tin kết nối DuckDB -> S3
```

---

# 5. Thư mục `dags` (Orchestration Layer)

Chứa mã nguồn định nghĩa luồng chạy của Apache Airflow.

```text
dags/
├── daily_job_pipeline.py  # DAG chính chạy hàng ngày
└── scripts/               # Các shell script hỗ trợ cho DAG
```

Một DAG chuẩn sẽ kích hoạt theo trình tự:
1. Gọi script Python trong `src/extract/` để cào dữ liệu.
2. Gọi `BashOperator` để chạy lệnh `dbt run --project-dir dbt_jobitvn` làm sạch dữ liệu.

---

# 6. Các thay đổi quan trọng so với kiến trúc cũ

### Đã loại bỏ thư mục `data/`
Trong các kiến trúc cũ, thường có thư mục `data/raw/` và `data/processed/` để lưu file CSV, JSON trên máy tính cá nhân. Việc này làm thư mục project rất nặng và dễ vô tình push data nhạy cảm lên Github.
Với kiến trúc Lakehouse, mọi dữ liệu thô cào về được `boto3` đẩy thẳng lên **Floci S3** (một Docker container riêng mô phỏng AWS S3).

### Đã loại bỏ thư mục `sql/`
Các file SQL DDL (Create Table) truyền thống đã bị loại bỏ vì `dbt` tự động tạo bảng hoặc view trong quá trình chạy. Không cần viết script tạo bảng thủ công nữa.

---

# 7. Deployment / Khởi chạy
Chỉ cần chạy file `docker-compose.yml`, các service sau sẽ được khởi tạo:
* `floci`: Local AWS (Cung cấp endpoint S3 ở cổng 4566).
* `airflow-webserver`: Giao diện điều phối (Cổng 8080).
* `airflow-scheduler`: Động cơ lập lịch.
* `api-serving`: FastAPI để cung cấp dữ liệu cho ứng dụng bên ngoài.
