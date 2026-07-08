{{ config(
    materialized='table'
) }}

SELECT
    skill_id,
    skill_code,
    display_name,
    skill_category,
    skill_subcategory,
    is_active
FROM {{ source('silver', 'skills') }}
