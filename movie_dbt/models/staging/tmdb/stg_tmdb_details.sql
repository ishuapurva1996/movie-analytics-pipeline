WITH tmdb_details AS (
    SELECT * FROM {{ source('tmdb','details')}}
)
SELECT 
    ID AS tmdb_id,
    IMDB_ID AS imdb_id,
    TITLE AS movie_title,
    BUDGET AS budget,
    REVENUE AS revenue,
    RELEASE_DATE AS tmdb_release_date,
    RUNTIME AS tmdb_runtime_min,
    STATUS AS tmdb_status,
    ORIGINAL_LANGUAGE AS original_language,
    ORIGIN_COUNTRY AS origin_country,
    PRODUCTION_COUNTRIES AS production_countries,
    PRODUCTION_COMPANIES AS production_companies,
    GENRES AS tmdb_genres,
    VOTE_AVERAGE AS tmdb_avg_rating,
    VOTE_COUNT AS tmdb_num_votes,
    POSTER_PATH AS tmdb_poster_path
FROM tmdb_details