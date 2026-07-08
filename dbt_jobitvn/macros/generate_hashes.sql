{% macro generate_identity_hash(source_code, company_name, location_code, job_family, salary_bucket, skills_array) %}
    -- Identity Hash: dùng để xác định 1 job duy nhất (không phụ thuộc nội dung có thể thay đổi như title)
    -- Hàm băm MD5 lấy 16 ký tự đầu
    -- Note: DuckDB MD5 trả về HEX string.
    SUBSTRING(
        MD5(
            COALESCE(LOWER(TRIM({{ source_code }})), '') || '|' ||
            COALESCE(LOWER(TRIM({{ company_name }})), '') || '|' ||
            COALESCE(LOWER(TRIM({{ location_code }})), '') || '|' ||
            COALESCE(LOWER(TRIM({{ job_family }})), '') || '|' ||
            COALESCE(LOWER(TRIM({{ salary_bucket }})), '') || '|' ||
            COALESCE(LOWER(TRIM({{ skills_array }}::TEXT)), '')
        ),
        1, 16
    )
{% endmacro %}

{% macro generate_content_hash(title_clean, description, requirements, salary_min, salary_max, experience_min, deadline) %}
    -- Content Hash: theo dõi nội dung thay đổi (SCD Type 2 CDC)
    SUBSTRING(
        MD5(
            COALESCE(LOWER(TRIM({{ title_clean }})), '') || '|' ||
            COALESCE(LOWER(TRIM({{ description }})), '') || '|' ||
            COALESCE(LOWER(TRIM({{ requirements }})), '') || '|' ||
            COALESCE({{ salary_min }}::TEXT, '') || '|' ||
            COALESCE({{ salary_max }}::TEXT, '') || '|' ||
            COALESCE({{ experience_min }}::TEXT, '') || '|' ||
            COALESCE({{ deadline }}::TEXT, '')
        ),
        1, 16
    )
{% endmacro %}
