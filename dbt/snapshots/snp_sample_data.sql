-- snapshots/snp_sample_data.sql
{% snapshot snp_sample_data %}

{{
    config(
      target_schema='snapshots',
      unique_key='id',
      strategy='timestamp',
      updated_at='updated_at',
    )
}}

SELECT
    id,
    name,
    value,
    CURRENT_TIMESTAMP AS updated_at
FROM {{ ref('stg_sample_data') }}

{% endsnapshot %}