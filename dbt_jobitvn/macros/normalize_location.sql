{% macro normalize_location(location_raw_column) %}
    -- Thay vì join trực tiếp trong model (phức tạp với chuỗi chứa nhiều tỉnh),
    -- macro này xử lý mapping string cơ bản. Để hoàn thiện hơn nên dùng
    -- UDF Python hoặc JOIN với regex, ở đây dùng string replace/regex đơn giản cho MVP.

    CASE
        WHEN {{ location_raw_column }} ILIKE '%Hà Nội%' OR {{ location_raw_column }} ILIKE '%Ha Noi%' OR {{ location_raw_column }} ILIKE '%HN%' THEN 'ha_noi'
        WHEN {{ location_raw_column }} ILIKE '%Hồ Chí Minh%' OR {{ location_raw_column }} ILIKE '%Ho Chi Minh%' OR {{ location_raw_column }} ILIKE '%HCM%' THEN 'ho_chi_minh'
        WHEN {{ location_raw_column }} ILIKE '%Đà Nẵng%' OR {{ location_raw_column }} ILIKE '%Da Nang%' OR {{ location_raw_column }} ILIKE '%DN%' THEN 'da_nang'
        WHEN {{ location_raw_column }} ILIKE '%Remote%' OR {{ location_raw_column }} ILIKE '%Từ xa%' THEN 'remote'
        ELSE 'other'
    END
{% endmacro %}
