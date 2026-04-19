-- tests/test_positive_values.sql
SELECT *
FROM {{ ref('stg_sample_data') }}
WHERE value <= 0