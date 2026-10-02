WITH imdb_name_basics AS (
    SELECT *
    FROM {{ ref('stg_imdb_name_basics') }}
)

SELECT
    person_id,
    primary_name AS person_name,
    birth_year,
    death_year
FROM imdb_name_basics