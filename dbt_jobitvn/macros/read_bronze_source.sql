{% macro read_bronze_source(source_code) %}
  {#
     read_bronze_source.sql — Dynamic Bronze Source Loader for dbt + DuckDB
     
     Chiến lược:
     1. Ưu tiên 1 (s3_parquet - Mặc định): Đọc Parquet trực tiếp từ S3 Floci bằng read_parquet.
     2. Ưu tiên 2 (s3_delta): Đọc Delta Lake Table từ S3 bằng delta_scan.
     3. Fallback (local_jsonl): Đọc raw JSONL từ disk local khi S3 không khả dụng.
     
     Điều khiển qua biến dbt: --vars '{"bronze_source_mode": "s3_parquet"}' hoặc '{"bronze_source_mode": "local_jsonl"}'
     Hoặc qua biến môi trường: BRONZE_SOURCE_MODE
  #}
  {% set source_mode = var('bronze_source_mode', env_var('BRONZE_SOURCE_MODE', 's3_parquet')) %}
  {% set bronze_local_dir = env_var('DATA_BRONZE_DIR', '/opt/airflow/data/bronze') %}

  {% if source_mode == 's3_parquet' %}
    SELECT * 
    FROM read_parquet('s3://jobit-bronze/bronze/{{ source_code }}/**/*.parquet', union_by_name=true)
    WHERE job_id IS NOT NULL
  {% elif source_mode == 's3_delta' %}
    SELECT * 
    FROM delta_scan('s3://jobit-bronze/bronze/{{ source_code }}')
    WHERE job_id IS NOT NULL
  {% else %}
    SELECT * 
    FROM read_json_auto('{{ bronze_local_dir }}/{{ source_code }}/**/*_valid.jsonl', format='newline_delimited', ignore_errors=true)
    WHERE job_id IS NOT NULL
  {% endif %}
{% endmacro %}
