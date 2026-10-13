{% macro parse_experience(exp_col, desc_col='NULL') %}
-- ============================================================
-- parse_experience: Chuyển đổi chuỗi kinh nghiệm → (min, max) năm
-- Input: "3 năm", "2 - 4 năm", "0.5 - 1 năm", "Trên 5 năm", "Không yêu cầu", "1 year"
-- Output: experience_min_years (SMALLINT), experience_max_years (SMALLINT)
-- Hỗ trợ extract từ description (desc_col) nếu mô tả chứa regex rõ ràng.
-- Bảo đảm min <= max bằng LEAST/GREATEST và hỗ trợ số thập phân (0.5, 1.5).
-- ============================================================

-- experience_min_years
COALESCE(
    -- 1. Ưu tiên trường thông tin kinh nghiệm chuẩn từ nguồn (exp_col)
    CASE
        WHEN {{ exp_col }} IS NULL OR TRIM({{ exp_col }}) = '' THEN NULL
        WHEN regexp_matches(LOWER({{ exp_col }}), 'không yêu cầu|chưa có kinh nghiệm|không cần kinh nghiệm|fresher|mới ra trường|no experience|entry') THEN 0
        -- Khoảng số thập phân hoặc nguyên: "0.5 - 1 năm", "0,5 - 1 năm", "1 - 2 năm", "2-4 years"
        WHEN regexp_matches(LOWER({{ exp_col }}), '(\d+(?:[.,]\d+)?)\s*[-–~]\s*(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)') THEN
            LEAST(
                CAST(FLOOR(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ exp_col }}), '(\d+(?:[.,]\d+)?)\s*[-–~]\s*(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)', 1), ',', '.') AS DOUBLE)) AS SMALLINT),
                CAST(FLOOR(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ exp_col }}), '(\d+(?:[.,]\d+)?)\s*[-–~]\s*(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)', 2), ',', '.') AS DOUBLE)) AS SMALLINT)
            )
        -- Tối thiểu / trên: "trên 5 năm", "từ 2 năm trở lên", "at least 3 years"
        WHEN regexp_matches(LOWER({{ exp_col }}), 'trên|trở lên|above|over|more than|>|at least') THEN
            CAST(FLOOR(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ exp_col }}), '(\d+(?:[.,]\d+)?)', 1), ',', '.') AS DOUBLE)) AS SMALLINT)
        -- Tối đa / dưới: "dưới 1 năm", "tới 2 năm", "up to 1 year"
        WHEN regexp_matches(LOWER({{ exp_col }}), 'tới|dưới|under|less than|<|up to') THEN 0
        -- Đơn vị tháng: "6 tháng", "6 months" (< 12 tháng quy về 0 năm)
        WHEN regexp_matches(LOWER({{ exp_col }}), '(\d+)\s*(?:tháng|months?|mos?)') THEN
            CAST(FLOOR(TRY_CAST(REGEXP_EXTRACT(LOWER({{ exp_col }}), '(\d+)', 1) AS DOUBLE) / 12.0) AS SMALLINT)
        -- Số đơn lẻ: "1 năm", "0.5 năm", "2 years"
        WHEN regexp_matches(LOWER({{ exp_col }}), '(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)') THEN
            CAST(FLOOR(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ exp_col }}), '(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)', 1), ',', '.') AS DOUBLE)) AS SMALLINT)
        ELSE NULL
    END,

    -- 2. Fallback sang bóc tách từ mô tả công việc (desc_col) nếu exp_col không có dữ liệu
    {% if desc_col != 'NULL' %}
    CASE
        -- Range (e.g. "2 - 4 năm kinh nghiệm", "2-4 years of experience")
        WHEN regexp_matches(LOWER({{ desc_col }}), '(\d+(?:[.,]\d+)?)\s*[-–~]\s*(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)') THEN
            LEAST(
                CAST(FLOOR(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(\d+(?:[.,]\d+)?)\s*[-–~]\s*(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)', 1), ',', '.') AS DOUBLE)) AS SMALLINT),
                CAST(FLOOR(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(\d+(?:[.,]\d+)?)\s*[-–~]\s*(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)', 2), ',', '.') AS DOUBLE)) AS SMALLINT)
            )
        -- Minimum Prefix (e.g. "ít nhất 2 năm kinh nghiệm", "minimum 2 years of experience")
        WHEN regexp_matches(LOWER({{ desc_col }}), '(?:tối thiểu|ít nhất|yêu cầu|có|với|từ|minimum|min|at least|require|required|having|with)[^\d]{0,30}(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)') THEN
            CAST(FLOOR(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(?:tối thiểu|ít nhất|yêu cầu|có|với|từ|minimum|min|at least|require|required|having|with)[^\d]{0,30}(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)', 1), ',', '.') AS DOUBLE)) AS SMALLINT)
        -- X+ years of experience ("2+ năm kinh nghiệm", "2+ years of experience")
        WHEN regexp_matches(LOWER({{ desc_col }}), '(\d+(?:[.,]\d+)?)\s*\+\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)') THEN
            CAST(FLOOR(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(\d+(?:[.,]\d+)?)\s*\+\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)', 1), ',', '.') AS DOUBLE)) AS SMALLINT)
        -- Reversed Range (e.g. "kinh nghiệm từ 2 - 4 năm", "experience: 2 - 4 years")
        WHEN regexp_matches(LOWER({{ desc_col }}), '(?:kinh nghiệm|experience)[^\d]{0,30}(\d+(?:[.,]\d+)?)\s*[-–~]\s*(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)') THEN
            LEAST(
                CAST(FLOOR(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(?:kinh nghiệm|experience)[^\d]{0,30}(\d+(?:[.,]\d+)?)\s*[-–~]\s*(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)', 1), ',', '.') AS DOUBLE)) AS SMALLINT),
                CAST(FLOOR(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(?:kinh nghiệm|experience)[^\d]{0,30}(\d+(?:[.,]\d+)?)\s*[-–~]\s*(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)', 2), ',', '.') AS DOUBLE)) AS SMALLINT)
            )
        -- Reversed Minimum (e.g. "kinh nghiệm tối thiểu 2 năm", "experience required: 2 years")
        WHEN regexp_matches(LOWER({{ desc_col }}), '(?:kinh nghiệm|experience)[^\d]{0,30}(?:từ|ít nhất|tối thiểu|yêu cầu|minimum|min|at least|require|required|>|>=)[^\d]{0,10}(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)') THEN
            CAST(FLOOR(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(?:kinh nghiệm|experience)[^\d]{0,30}(?:từ|ít nhất|tối thiểu|yêu cầu|minimum|min|at least|require|required|>|>=)[^\d]{0,10}(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)', 1), ',', '.') AS DOUBLE)) AS SMALLINT)
        -- Simple Exact match (e.g. "Kinh nghiệm: 2 năm", "Experience: 2 years")
        WHEN regexp_matches(LOWER({{ desc_col }}), '(?:kinh nghiệm|experience)\s*:\s*(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)') THEN
            CAST(FLOOR(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(?:kinh nghiệm|experience)\s*:\s*(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)', 1), ',', '.') AS DOUBLE)) AS SMALLINT)
        ELSE NULL
    END
    {% else %}
    NULL
    {% endif %}
) AS experience_min_years,

-- experience_max_years
COALESCE(
    -- 1. Ưu tiên trường thông tin kinh nghiệm chuẩn từ nguồn (exp_col)
    CASE
        WHEN {{ exp_col }} IS NULL OR TRIM({{ exp_col }}) = '' THEN NULL
        WHEN regexp_matches(LOWER({{ exp_col }}), 'không yêu cầu|chưa có kinh nghiệm|không cần kinh nghiệm|fresher|mới ra trường|no experience|entry') THEN 1
        -- Khoảng số thập phân hoặc nguyên: "0.5 - 1 năm", "0,5 - 1 năm", "1 - 2 năm", "2-4 years"
        WHEN regexp_matches(LOWER({{ exp_col }}), '(\d+(?:[.,]\d+)?)\s*[-–~]\s*(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)') THEN
            GREATEST(
                CAST(CEIL(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ exp_col }}), '(\d+(?:[.,]\d+)?)\s*[-–~]\s*(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)', 1), ',', '.') AS DOUBLE)) AS SMALLINT),
                CAST(CEIL(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ exp_col }}), '(\d+(?:[.,]\d+)?)\s*[-–~]\s*(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)', 2), ',', '.') AS DOUBLE)) AS SMALLINT)
            )
        -- Tối thiểu / trên: "trên 5 năm", "từ 2 năm trở lên" (+5 năm cho max)
        WHEN regexp_matches(LOWER({{ exp_col }}), 'trên|trở lên|above|over|more than|>|at least') THEN
            CAST(FLOOR(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ exp_col }}), '(\d+(?:[.,]\d+)?)', 1), ',', '.') AS DOUBLE)) AS SMALLINT) + 5
        -- Tối đa / dưới: "dưới 1 năm", "tới 2 năm", "up to 1 year"
        WHEN regexp_matches(LOWER({{ exp_col }}), 'tới|dưới|under|less than|<|up to') THEN
            CAST(CEIL(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ exp_col }}), '(\d+(?:[.,]\d+)?)', 1), ',', '.') AS DOUBLE)) AS SMALLINT)
        -- Đơn vị tháng: "6 tháng" (<= 12 tháng quy về max 1 năm)
        WHEN regexp_matches(LOWER({{ exp_col }}), '(\d+)\s*(?:tháng|months?|mos?)') THEN
            GREATEST(1::SMALLINT, CAST(CEIL(TRY_CAST(REGEXP_EXTRACT(LOWER({{ exp_col }}), '(\d+)', 1) AS DOUBLE) / 12.0) AS SMALLINT))
        -- Số đơn lẻ: "1 năm", "0.5 năm", "2 years"
        WHEN regexp_matches(LOWER({{ exp_col }}), '(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)') THEN
            CAST(CEIL(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ exp_col }}), '(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)', 1), ',', '.') AS DOUBLE)) AS SMALLINT)
        ELSE NULL
    END,

    -- 2. Fallback sang bóc tách từ mô tả công việc (desc_col) nếu exp_col không có dữ liệu
    {% if desc_col != 'NULL' %}
    CASE
        -- Range
        WHEN regexp_matches(LOWER({{ desc_col }}), '(\d+(?:[.,]\d+)?)\s*[-–~]\s*(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)') THEN
            GREATEST(
                CAST(CEIL(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(\d+(?:[.,]\d+)?)\s*[-–~]\s*(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)', 1), ',', '.') AS DOUBLE)) AS SMALLINT),
                CAST(CEIL(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(\d+(?:[.,]\d+)?)\s*[-–~]\s*(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)', 2), ',', '.') AS DOUBLE)) AS SMALLINT)
            )
        -- Minimum Prefix (+3 logic for max)
        WHEN regexp_matches(LOWER({{ desc_col }}), '(?:tối thiểu|ít nhất|yêu cầu|có|với|từ|minimum|min|at least|require|required|having|with)[^\d]{0,30}(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)') THEN
            CAST(FLOOR(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(?:tối thiểu|ít nhất|yêu cầu|có|với|từ|minimum|min|at least|require|required|having|with)[^\d]{0,30}(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)', 1), ',', '.') AS DOUBLE)) AS SMALLINT) + 3
        -- X+ years (+3 logic for max)
        WHEN regexp_matches(LOWER({{ desc_col }}), '(\d+(?:[.,]\d+)?)\s*\+\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)') THEN
            CAST(FLOOR(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(\d+(?:[.,]\d+)?)\s*\+\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)', 1), ',', '.') AS DOUBLE)) AS SMALLINT) + 3
        -- Reversed Range
        WHEN regexp_matches(LOWER({{ desc_col }}), '(?:kinh nghiệm|experience)[^\d]{0,30}(\d+(?:[.,]\d+)?)\s*[-–~]\s*(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)') THEN
            GREATEST(
                CAST(CEIL(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(?:kinh nghiệm|experience)[^\d]{0,30}(\d+(?:[.,]\d+)?)\s*[-–~]\s*(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)', 1), ',', '.') AS DOUBLE)) AS SMALLINT),
                CAST(CEIL(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(?:kinh nghiệm|experience)[^\d]{0,30}(\d+(?:[.,]\d+)?)\s*[-–~]\s*(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)', 2), ',', '.') AS DOUBLE)) AS SMALLINT)
            )
        -- Reversed Minimum (+3 logic for max)
        WHEN regexp_matches(LOWER({{ desc_col }}), '(?:kinh nghiệm|experience)[^\d]{0,30}(?:từ|ít nhất|tối thiểu|yêu cầu|minimum|min|at least|require|required|>|>=)[^\d]{0,10}(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)') THEN
            CAST(FLOOR(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(?:kinh nghiệm|experience)[^\d]{0,30}(?:từ|ít nhất|tối thiểu|yêu cầu|minimum|min|at least|require|required|>|>=)[^\d]{0,10}(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)', 1), ',', '.') AS DOUBLE)) AS SMALLINT) + 3
        -- Simple Exact match (max = min)
        WHEN regexp_matches(LOWER({{ desc_col }}), '(?:kinh nghiệm|experience)\s*:\s*(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)') THEN
            CAST(CEIL(TRY_CAST(REPLACE(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(?:kinh nghiệm|experience)\s*:\s*(\d+(?:[.,]\d+)?)\s*(?:năm|year|years|yrs?)', 1), ',', '.') AS DOUBLE)) AS SMALLINT)
        ELSE NULL
    END
    {% else %}
    NULL
    {% endif %}
) AS experience_max_years

{% endmacro %}
