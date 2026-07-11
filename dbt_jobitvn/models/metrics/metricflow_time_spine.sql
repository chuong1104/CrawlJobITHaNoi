{{ config(
    materialized = 'table'
) }}

select 
    cast(generate_series as date) as date_day
from generate_series('2024-01-01'::date, '2030-12-31'::date, INTERVAL 1 DAY)
