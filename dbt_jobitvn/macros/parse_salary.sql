{% macro parse_salary(salary_raw_column) %}
    -- Logic extract mức lương cơ bản (triệu VND) từ chuỗi text
    -- Dùng Regex để tìm min và max.
    -- Xử lý các case: "15 - 20 triệu", "Tới 30 Tr", "Thoả thuận"

    CASE 
        WHEN {{ salary_raw_column }} ILIKE '%thoả thuận%' 
          OR {{ salary_raw_column }} ILIKE '%cạnh tranh%'
          OR {{ salary_raw_column }} ILIKE '%thỏa thuận%' THEN NULL
        -- Range (e.g. 15 - 20 triệu)
        WHEN {{ salary_raw_column }} ~ '(\d+)\s*(?:-|đến|tới)\s*(\d+)\s*(triệu|tr|m)' THEN
            CAST(SUBSTRING({{ salary_raw_column }} FROM '(\d+)\s*(?:-|đến|tới)\s*\d+\s*(?:triệu|tr|m)') AS NUMERIC) * 1000000
        -- Up to (e.g. Tới 30 triệu)
        WHEN {{ salary_raw_column }} ~ '(?i)(tới|lên đến|up to)\s*(\d+)\s*(triệu|tr|m)' THEN
            NULL -- min is NULL
        -- Fixed (e.g. 20 triệu)
        WHEN {{ salary_raw_column }} ~ '(\d+)\s*(triệu|tr|m)' THEN
            CAST(SUBSTRING({{ salary_raw_column }} FROM '(\d+)\s*(?:triệu|tr|m)') AS NUMERIC) * 1000000
        -- USD (e.g. $500 - $1000)
        WHEN {{ salary_raw_column }} ~ '\$(\d+)\s*(?:-|đến|tới)\s*\$?(\d+)' THEN
            CAST(SUBSTRING({{ salary_raw_column }} FROM '\$(\d+)\s*(?:-|đến|tới)') AS NUMERIC) * 25000 -- Tỉ giá cứng MVP
        ELSE NULL
    END AS salary_min,

    CASE 
        WHEN {{ salary_raw_column }} ILIKE '%thoả thuận%' 
          OR {{ salary_raw_column }} ILIKE '%cạnh tranh%'
          OR {{ salary_raw_column }} ILIKE '%thỏa thuận%' THEN NULL
        -- Range (e.g. 15 - 20 triệu)
        WHEN {{ salary_raw_column }} ~ '(\d+)\s*(?:-|đến|tới)\s*(\d+)\s*(triệu|tr|m)' THEN
            CAST(SUBSTRING({{ salary_raw_column }} FROM '\d+\s*(?:-|đến|tới)\s*(\d+)\s*(?:triệu|tr|m)') AS NUMERIC) * 1000000
        -- Up to (e.g. Tới 30 triệu)
        WHEN {{ salary_raw_column }} ~ '(?i)(tới|lên đến|up to)\s*(\d+)\s*(triệu|tr|m)' THEN
            CAST(SUBSTRING({{ salary_raw_column }} FROM '(?i)(?:tới|lên đến|up to)\s*(\d+)\s*(?:triệu|tr|m)') AS NUMERIC) * 1000000
        -- Fixed (e.g. 20 triệu)
        WHEN {{ salary_raw_column }} ~ '(\d+)\s*(triệu|tr|m)' THEN
            CAST(SUBSTRING({{ salary_raw_column }} FROM '(\d+)\s*(?:triệu|tr|m)') AS NUMERIC) * 1000000
        -- USD (e.g. $500 - $1000)
        WHEN {{ salary_raw_column }} ~ '\$(\d+)\s*(?:-|đến|tới)\s*\$?(\d+)' THEN
            CAST(SUBSTRING({{ salary_raw_column }} FROM '\$\d+\s*(?:-|đến|tới)\s*\$?(\d+)') AS NUMERIC) * 25000
        ELSE NULL
    END AS salary_max,

    CASE 
        WHEN {{ salary_raw_column }} ILIKE '%thoả thuận%' 
          OR {{ salary_raw_column }} ILIKE '%cạnh tranh%' 
          OR {{ salary_raw_column }} ILIKE '%thỏa thuận%' THEN TRUE
        ELSE FALSE
    END AS salary_is_negotiable,

    CASE
        WHEN {{ salary_raw_column }} ~ '\$' OR {{ salary_raw_column }} ILIKE '%usd%' THEN 'USD'
        ELSE 'VND'
    END AS salary_currency

{% endmacro %}
