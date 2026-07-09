{{ config(
    materialized = 'table'
) }}

select 
    cast(d as date) as date_day
from generate_series('2024-01-01'::date, '2030-12-31'::date, '1 day'::interval) d
