WITH TMDB_NOW_PLAYING AS (
    SELECT * FROM {{ ref('stg_tmdb_now_playing') }}
),
DIM_MOVIES AS (
    SELECT * FROM {{ ref('dim_movies') }}
)
SELECT 
    coalesce(m.movie_id, 'tmdb_' || t.tmdb_id::string) as movie_id,
    m.IMDB_ID,
    t.TMDB_ID,
    coalesce(m.movie_name, t.movie_title) as movie_name,
    t.NOW_PLAYING_RELEASE_DATE,
    t.NOW_PLAYING_OVERVIEW,
    t.NOW_PLAYING_POSTER_PATH,
    t.NOW_PLAYING_POPULARITY,
    t.TMDB_REGION,
    t.SNAPSHOT_DATE
FROM TMDB_NOW_PLAYING t
LEFT JOIN DIM_MOVIES m
    ON t.TMDB_ID = m.TMDB_ID