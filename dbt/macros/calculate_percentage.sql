-- macros/calculate_percentage.sql
{% macro calculate_percentage(numerator, denominator) %}
    CASE
        WHEN {{ denominator }} = 0 THEN 0
        ELSE ({{ numerator }} * 100.0) / {{ denominator }}
    END
{% endmacro %}
