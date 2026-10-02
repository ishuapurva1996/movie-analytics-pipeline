WITH dim_movies AS (
    SELECT * FROM {{ ref('dim_movies') }}
),
STG_TMDB_DETAILS AS (
    SELECT * FROM {{ ref('stg_tmdb_details') }}
),
STG_IMDB_TITLE_RATINGS AS (
    SELECT * FROM {{ ref('stg_imdb_title_ratings') }}
)
SELECT
    m.MOVIE_ID,
    m.imdb_id,
    m.tmdb_id,
    i.avg_rating AS imdb_avg_rating,
    i.num_of_votes AS imdb_num_of_votes,
    t.tmdb_avg_rating AS tmdb_avg_rating,
    t.tmdb_num_votes AS tmdb_num_of_votes,
CASE 
    WHEN i.avg_rating IS NOT NULL THEN True
    ELSE false
END AS has_imdb_ratings,
CASE 
    WHEN t.tmdb_avg_rating IS NOT NULL THEN True
    ELSE false
END AS has_tmdb_ratings
FROM dim_movies m
LEFT JOIN STG_IMDB_TITLE_RATINGS i
    ON m.imdb_id = i.imdb_id
LEFT JOIN STG_TMDB_DETAILS t
    ON m.tmdb_id = t.tmdb_id


