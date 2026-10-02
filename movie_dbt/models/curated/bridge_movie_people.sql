WITH dim_movies AS (
    SELECT * FROM {{ ref('dim_movies') }}
),
IMDB_TITLE_PRINCIPALS AS (
    SELECT * FROM {{ ref('stg_imdb_title_principals') }}
)
SELECT 
    m.MOVIE_ID,
    m.IMDB_ID,
    p.PRINCIPAL_ORDER,
    p.PERSON_ID,
    p.JOB_ROLE,
    p.SPECIFIC_JOB
FROM dim_movies m
LEFT JOIN IMDB_TITLE_PRINCIPALS p
    ON m.IMDB_ID = p.IMDB_ID
WHERE p.PERSON_ID IS NOT NULL