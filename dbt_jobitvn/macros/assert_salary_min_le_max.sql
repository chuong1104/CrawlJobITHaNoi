{% test assert_salary_min_le_max(model, column_name) %}

SELECT *
FROM {{ model }}
WHERE {{ column_name }} > salary_max

{% endtest %}
