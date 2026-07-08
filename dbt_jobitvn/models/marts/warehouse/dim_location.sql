{{ config(
    materialized='table'
) }}

SELECT
    location_id,
    location_code,
    display_name,
    region,
    is_remote
FROM {{ source('silver', 'locations') }}
