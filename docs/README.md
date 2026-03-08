# Tài liệu dự án - Job Scraper DE Project

| # | File | Nội dung |
|---|---|---|
| 01 | [01_architecture.md](01_architecture.md) | Kiến trúc tổng thể, sơ đồ pipeline, schema thống nhất, công nghệ |
| 02 | [02_extract.md](02_extract.md) | Chi tiết 11 scrapers, BaseScraper, cơ chế retry/proxy, output format |
| 03 | [03_transform.md](03_transform.md) | Cleaner, Normalizer, Pydantic Schema, ví dụ end-to-end |
| 04 | [04_load.md](04_load.md) | Database schema, upsert strategy, batch loading, xử lý lỗi |
| 05 | [05_airflow_dags.md](05_airflow_dags.md) | DAG config, task graph, ScrapeOperator, Variables, Connections |
| 06 | [06_infrastructure.md](06_infrastructure.md) | Docker services, Dockerfile, env vars, khởi động, troubleshooting |
| 07 | [07_testing.md](07_testing.md) | Unit tests, fixtures, coverage targets, CI/CD |
| 08 | [08_scrapling_portals_reference.md](08_scrapling_portals_reference.md) | Selector/reference chi tiết cho các portal dùng Scrapling |
| 09 | [09_scrapling_usage_guide.md](09_scrapling_usage_guide.md) | Hướng dẫn thực hành Scrapling từ quickstart đến tích hợp production |
| 10 | [10_website_source_analysis.md](10_website_source_analysis.md) | Nhật ký phân tích nguồn website theo từng portal để cập nhật dần |
