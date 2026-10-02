WITH rated_movies AS (
    SELECT 
        MOVIE_ID,
        COALESCE(IMDB_AVG_RATING, TMDB_AVG_RATING) AS avg_rating,
        COALESCE(imdb_num_of_votes, tmdb_num_of_votes) AS num_of_votes
    FROM {{ ref('fct_movie_ratings') }}
    WHERE (TMDB_AVG_RATING IS NOT NULL OR IMDB_AVG_RATING IS NOT NULL)
    AND (IMDB_NUM_OF_VOTES >= 100000 OR TMDB_NUM_OF_VOTES >=100000)
    
),
DIM_MOVIES AS (
 SELECT * FROM {{ ref('dim_movies') }}
)
SELECT 
    r.MOVIE_ID,
    m.MOVIE_NAME,
    r.avg_rating,
    r.num_of_votes
FROM rated_movies r
LEFT JOIN DIM_MOVIES m 
ON m.MOVIE_ID = r.MOVIE_ID
ORDER BY r.avg_rating DESC, r.num_of_votes DESC LIMIT 1
