
WITH rated_movies AS (
    SELECT *,
    COALESCE(IMDB_AVG_RATING, TMDB_AVG_RATING) AS avg_rating,
    COALESCE(IMDB_NUM_OF_VOTES, TMDB_NUM_OF_VOTES) AS num_of_votes
    FROM {{ ref('fct_movie_ratings')}}
    WHERE (IMDB_NUM_OF_VOTES IS NOT NULL OR TMDB_NUM_OF_VOTES IS NOT NULL)
    AND (IMDB_NUM_OF_VOTES >= 100000 OR TMDB_NUM_OF_VOTES >=100000)
),
rank_movie AS (
    SELECT 
        movie_id,
        IMDB_AVG_RATING,
        IMDB_NUM_OF_VOTES,
        TMDB_AVG_RATING,
        TMDB_NUM_OF_VOTES,
        avg_rating,
        num_of_votes,
        ROW_NUMBER() OVER (ORDER BY avg_rating DESC NULLS LAST, num_of_votes DESC NULLS LAST, movie_id ASC) AS rn
    FROM rated_movies
),
DIM_MOVIES AS (
 SELECT * FROM {{ ref('dim_movies')}}
)
SELECT 
    r.movie_id,
    m.movie_name,
    r.avg_rating,
    r.num_of_votes,
    r.rn AS movie_rank
FROM rank_movie r
LEFT JOIN DIM_MOVIES m
ON m.movie_id = r.movie_id
WHERE r.rn <=10
ORDER BY r.rn ASC
