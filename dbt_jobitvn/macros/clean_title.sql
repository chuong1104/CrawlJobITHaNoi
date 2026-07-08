{% macro clean_title(title_raw_column) %}
    -- Loại bỏ các từ khóa quảng cáo/marketing để lấy title chuyên môn
    -- Sử dụng REGEXP_REPLACE nhiều lần hoặc lồng nhau
    TRIM(
        REGEXP_REPLACE(
            REGEXP_REPLACE(
                REGEXP_REPLACE(
                    {{ title_raw_column }},
                    '(?i)(\[.*?\]|\(.*?\)|hot|tuyển gấp|lương cao|đi làm ngay|thu nhập khủng|cơ hội hấp dẫn|hấp dẫn|urgent)',
                    '',
                    'g'
                ),
                '\s+', ' ', 'g'
            ),
            '^[\-\|\,\.]+|[\-\|\,\.]+$', '', 'g'
        )
    )
{% endmacro %}
