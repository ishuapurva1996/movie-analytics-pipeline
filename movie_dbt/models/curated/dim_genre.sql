WITH movie_genre AS (
    SELECT 
        TRIM(gen.value) AS genre_name
    FROM {{ ref('stg_imdb_title_basics')}},
    LATERAL SPLIT_TO_TABLE(GENRES, ',') AS gen
    WHERE GENRES IS NOT NULL
),
DISTINCT_GENRES AS (
    SELECT 
        DISTINCT genre_name
    FROM movie_genre
)
SELECT
    ROW_NUMBER() OVER(ORDER BY genre_name) AS genre_id,
    genre_name
FROM DISTINCT_GENRES