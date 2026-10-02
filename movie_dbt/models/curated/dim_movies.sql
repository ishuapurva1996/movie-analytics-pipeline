WITH TMDB_DETAILS AS (
    SELECT * FROM {{ ref('stg_tmdb_details') }}
),
IMDB_TITLE_BASICS AS (
    SELECT * FROM {{ ref('stg_imdb_title_basics') }}
    WHERE CONTENT_TYPE IN ('movie', 'tvMovie')
    AND END_YEAR IS NULL 
)
SELECT 
    coalesce(imdb.imdb_id, 'tmdb_' || tmdb.tmdb_id::string) as movie_id,
    coalesce(imdb.imdb_id, tmdb.imdb_id) as imdb_id,
    tmdb.tmdb_id,
    coalesce(imdb.primary_title, tmdb.movie_title) as movie_name,
    imdb.original_title as imdb_original_title,
    tmdb.movie_title as tmdb_movie_title,
    imdb.is_adult,
    coalesce(imdb.start_year, extract(year from tmdb.tmdb_release_date)) as release_year,
    coalesce(imdb.runtime_min, tmdb.tmdb_runtime_min) as runtime_min,
    coalesce(imdb.content_type, 'tmdb_movie') as content_type
FROM TMDB_DETAILS tmdb
FULL OUTER JOIN IMDB_TITLE_BASICS imdb
    ON tmdb.IMDB_ID = imdb.IMDB_ID