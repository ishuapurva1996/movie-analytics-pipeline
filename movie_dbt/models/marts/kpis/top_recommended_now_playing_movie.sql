WITH FCT_NOW_PLAYING AS (
    SELECT * FROM {{ ref('fct_now_playing') }}
),
rated_movies AS (
    SELECT *,
    COALESCE(IMDB_AVG_RATING, TMDB_AVG_RATING) AS avg_rating,
    COALESCE(IMDB_NUM_OF_VOTES, TMDB_NUM_OF_VOTES) AS num_of_votes
    FROM {{ ref('fct_movie_ratings') }}
    WHERE (IMDB_NUM_OF_VOTES IS NOT NULL OR TMDB_NUM_OF_VOTES IS NOT NULL)
    AND (IMDB_NUM_OF_VOTES >= 10000 OR TMDB_NUM_OF_VOTES >=1000)
),
ranked AS (
SELECT
    n.movie_id,
    n.MOVIE_NAME,
    n.tmdb_region,
    n.now_playing_release_date,
    n.now_playing_overview,
    n.now_playing_popularity,
    r.avg_rating,
    r.num_of_votes,
    ROW_NUMBER() OVER(PARTITION BY n.tmdb_region ORDER BY r.avg_rating DESC, r.num_of_votes DESC, n.now_playing_popularity DESC) AS recommendation_rank
FROM FCT_NOW_PLAYING n 
INNER JOIN rated_movies r
    ON n.movie_id = r.movie_id
)
SELECT *
FROM ranked
WHERE recommendation_rank <= 1
ORDER BY tmdb_region, recommendation_rank
