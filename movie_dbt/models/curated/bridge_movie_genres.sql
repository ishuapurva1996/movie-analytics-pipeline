WITH IMDB_TITLE_BASICS AS (
    SELECT * 
        FROM {{ ref('stg_imdb_title_basics') }}
    WHERE CONTENT_TYPE IN ('movie', 'tvMovie')
    AND END_YEAR IS NULL 
),
IMDB_GENRE AS (
    SELECT 
        imdb_id AS movie_id, 
        TRIM(gen.value) AS genre_name,
        'imdb' as genre_source
    FROM IMDB_TITLE_BASICS,
    LATERAL SPLIT_TO_TABLE(genres, ',') AS gen
),
TMDB_DETAILS AS (
    SELECT *
        FROM {{ ref('stg_tmdb_details') }}
),
 tmdb_only_genres AS (
    SELECT 
        'tmdb_' || tmdb.tmdb_id::string AS movie_id,
        gen.value:name::VARCHAR AS genre_name,
        'tmdb' as genre_source
    FROM TMDB_DETAILS tmdb
    LEFT JOIN IMDB_TITLE_BASICS imdb
    ON tmdb.imdb_id = imdb.imdb_id,
    LATERAL FLATTEN (input => parse_json(TMDB_GENRES)) AS gen
    WHERE imdb.imdb_id IS NULL
    AND tmdb_genres is not null
)
SELECT * FROM IMDB_GENRE
UNION ALL
SELECT * FROM tmdb_only_genres
