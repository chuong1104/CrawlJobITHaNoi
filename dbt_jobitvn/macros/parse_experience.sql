{% macro parse_experience(exp_col, desc_col='NULL') %}
-- ============================================================
-- parse_experience: Chuyển đổi chuỗi kinh nghiệm → (min, max) năm
-- Input: "3 năm", "2 - 4 năm", "Trên 5 năm", "Không yêu cầu", "1 year"
-- Output: experience_min_years (SMALLINT), experience_max_years (SMALLINT)
-- Hỗ trợ extract từ description (desc_col) nếu mô tả chứa regex rõ ràng.
-- ============================================================

-- experience_min_years
COALESCE(
    {% if desc_col != 'NULL' %}
    CASE
        -- Range (e.g. "2 - 4 năm kinh nghiệm", "2-4 years of experience")
        WHEN LOWER({{ desc_col }}) ~ '(\d+)\s*[-–]\s*(\d+)\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)' THEN
            TRY_CAST(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(\d+)\s*[-–]\s*(\d+)\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)', 1) AS SMALLINT)
        -- Minimum Prefix (e.g. "ít nhất 2 năm kinh nghiệm", "minimum 2 years of experience")
        WHEN LOWER({{ desc_col }}) ~ '(?:tối thiểu|ít nhất|yêu cầu|có|với|từ|minimum|min|at least|require|required|having|with)[^\d]{0,30}(\d+)\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)' THEN
            TRY_CAST(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(?:tối thiểu|ít nhất|yêu cầu|có|với|từ|minimum|min|at least|require|required|having|with)[^\d]{0,30}(\d+)\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)', 1) AS SMALLINT)
        -- X+ years of experience ("2+ năm kinh nghiệm", "2+ years of experience")
        WHEN LOWER({{ desc_col }}) ~ '(\d+)\s*\+\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)' THEN
            TRY_CAST(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(\d+)\s*\+\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)', 1) AS SMALLINT)
        -- Reversed Range (e.g. "kinh nghiệm từ 2 - 4 năm", "experience: 2 - 4 years")
        WHEN LOWER({{ desc_col }}) ~ '(?:kinh nghiệm|experience)[^\d]{0,30}(\d+)\s*[-–]\s*(\d+)\s*(?:năm|year|years|yrs?)' THEN
            TRY_CAST(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(?:kinh nghiệm|experience)[^\d]{0,30}(\d+)\s*[-–]\s*(\d+)\s*(?:năm|year|years|yrs?)', 1) AS SMALLINT)
        -- Reversed Minimum (e.g. "kinh nghiệm tối thiểu 2 năm", "experience required: 2 years")
        WHEN LOWER({{ desc_col }}) ~ '(?:kinh nghiệm|experience)[^\d]{0,30}(?:từ|ít nhất|tối thiểu|yêu cầu|minimum|min|at least|require|required|>|>=)[^\d]{0,10}(\d+)\s*(?:năm|year|years|yrs?)' THEN
            TRY_CAST(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(?:kinh nghiệm|experience)[^\d]{0,30}(?:từ|ít nhất|tối thiểu|yêu cầu|minimum|min|at least|require|required|>|>=)[^\d]{0,10}(\d+)\s*(?:năm|year|years|yrs?)', 1) AS SMALLINT)
        -- Simple Exact match (e.g. "Kinh nghiệm: 2 năm", "Experience: 2 years")
        WHEN LOWER({{ desc_col }}) ~ '(?:kinh nghiệm|experience)\s*:\s*(\d+)\s*(?:năm|year|years|yrs?)' THEN
            TRY_CAST(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(?:kinh nghiệm|experience)\s*:\s*(\d+)\s*(?:năm|year|years|yrs?)', 1) AS SMALLINT)
        ELSE NULL
    END,
    {% endif %}
    
    CASE
        WHEN {{ exp_col }} IS NULL THEN NULL
        WHEN LOWER({{ exp_col }}) ~ 'không yêu cầu|fresher|mới ra trường|no experience|entry' THEN 0
        WHEN {{ exp_col }} ~ '(\d+)\s*[-–]\s*(\d+)\s*(năm|year|yrs?)' THEN
            TRY_CAST(REGEXP_EXTRACT({{ exp_col }}, '(\d+)\s*[-–]\s*(\d+)\s*(?:năm|year|yrs?)', 1) AS SMALLINT)
        WHEN LOWER({{ exp_col }}) ~ 'trên|trở lên|above|over|more than|>|at least' THEN
            TRY_CAST(REGEXP_EXTRACT({{ exp_col }}, '(\d+)', 1) AS SMALLINT)
        WHEN LOWER({{ exp_col }}) ~ 'tới|dưới|under|less than|<|up to' THEN 0
        WHEN {{ exp_col }} ~ '(\d+)\s*(năm|year|yrs?)' THEN
            TRY_CAST(REGEXP_EXTRACT({{ exp_col }}, '(\d+)\s*(?:năm|year|yrs?)', 1) AS SMALLINT)
        ELSE NULL
    END
) AS experience_min_years,

-- experience_max_years
COALESCE(
    {% if desc_col != 'NULL' %}
    CASE
        -- Range
        WHEN LOWER({{ desc_col }}) ~ '(\d+)\s*[-–]\s*(\d+)\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)' THEN
            TRY_CAST(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(\d+)\s*[-–]\s*(\d+)\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)', 2) AS SMALLINT)
        -- Minimum Prefix (+3 logic for max)
        WHEN LOWER({{ desc_col }}) ~ '(?:tối thiểu|ít nhất|yêu cầu|có|với|từ|minimum|min|at least|require|required|having|with)[^\d]{0,30}(\d+)\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)' THEN
            TRY_CAST(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(?:tối thiểu|ít nhất|yêu cầu|có|với|từ|minimum|min|at least|require|required|having|with)[^\d]{0,30}(\d+)\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)', 1) AS SMALLINT) + 3
        -- X+ years (+3 logic for max)
        WHEN LOWER({{ desc_col }}) ~ '(\d+)\s*\+\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)' THEN
            TRY_CAST(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(\d+)\s*\+\s*(?:năm|year|years|yrs?)[^\d]{0,20}(?:kinh nghiệm|experience)', 1) AS SMALLINT) + 3
        -- Reversed Range
        WHEN LOWER({{ desc_col }}) ~ '(?:kinh nghiệm|experience)[^\d]{0,30}(\d+)\s*[-–]\s*(\d+)\s*(?:năm|year|years|yrs?)' THEN
            TRY_CAST(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(?:kinh nghiệm|experience)[^\d]{0,30}(\d+)\s*[-–]\s*(\d+)\s*(?:năm|year|years|yrs?)', 2) AS SMALLINT)
        -- Reversed Minimum (+3 logic for max)
        WHEN LOWER({{ desc_col }}) ~ '(?:kinh nghiệm|experience)[^\d]{0,30}(?:từ|ít nhất|tối thiểu|yêu cầu|minimum|min|at least|require|required|>|>=)[^\d]{0,10}(\d+)\s*(?:năm|year|years|yrs?)' THEN
            TRY_CAST(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(?:kinh nghiệm|experience)[^\d]{0,30}(?:từ|ít nhất|tối thiểu|yêu cầu|minimum|min|at least|require|required|>|>=)[^\d]{0,10}(\d+)\s*(?:năm|year|years|yrs?)', 1) AS SMALLINT) + 3
        -- Simple Exact match (max = min)
        WHEN LOWER({{ desc_col }}) ~ '(?:kinh nghiệm|experience)\s*:\s*(\d+)\s*(?:năm|year|years|yrs?)' THEN
            TRY_CAST(REGEXP_EXTRACT(LOWER({{ desc_col }}), '(?:kinh nghiệm|experience)\s*:\s*(\d+)\s*(?:năm|year|years|yrs?)', 1) AS SMALLINT)
        ELSE NULL
    END,
    {% endif %}

    CASE
        WHEN {{ exp_col }} IS NULL THEN NULL
        WHEN LOWER({{ exp_col }}) ~ 'không yêu cầu|fresher|mới ra trường|no experience|entry' THEN 1
        WHEN {{ exp_col }} ~ '(\d+)\s*[-–]\s*(\d+)\s*(năm|year|yrs?)' THEN
            TRY_CAST(REGEXP_EXTRACT({{ exp_col }}, '(\d+)\s*[-–]\s*(\d+)\s*(?:năm|year|yrs?)', 2) AS SMALLINT)
        WHEN LOWER({{ exp_col }}) ~ 'trên|trở lên|above|over|more than|>|at least' THEN
            TRY_CAST(REGEXP_EXTRACT({{ exp_col }}, '(\d+)', 1) AS SMALLINT) + 5
        WHEN LOWER({{ exp_col }}) ~ 'tới|dưới|under|less than|<|up to' THEN
            TRY_CAST(REGEXP_EXTRACT({{ exp_col }}, '(\d+)', 1) AS SMALLINT)
        WHEN {{ exp_col }} ~ '(\d+)\s*(năm|year|yrs?)' THEN
            TRY_CAST(REGEXP_EXTRACT({{ exp_col }}, '(\d+)\s*(?:năm|year|yrs?)', 1) AS SMALLINT)
        ELSE NULL
    END
) AS experience_max_years

{% endmacro %}
