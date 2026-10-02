WITH dim_movies AS (   
    SELECT 
        *
    FROM {{ ref('dim_movies')}}
    WHERE RELEASE_YEAR IS NOT NULL
),
rated_movies AS (
    SELECT *,
    COALESCE(IMDB_AVG_RATING, TMDB_AVG_RATING) AS avg_rating,
    COALESCE(IMDB_NUM_OF_VOTES, TMDB_NUM_OF_VOTES) AS num_of_votes
    FROM {{ ref('fct_movie_ratings')}}
    WHERE (IMDB_NUM_OF_VOTES IS NOT NULL OR TMDB_NUM_OF_VOTES IS NOT NULL)
)
SELECT 
    m.RELEASE_YEAR,
    ROUND(AVG(r.avg_rating), 2) AS release_yr_avg_rating,
    COUNT(DISTINCT m.movie_id) AS movie_count
FROM dim_movies m
INNER JOIN rated_movies r 
    ON m.movie_id = r.movie_id
WHERE r.avg_rating IS NOT NULL
AND
    CASE 
        WHEN m.release_year < 1900 THEN r.num_of_votes >= 20
        WHEN m.release_year < 1930 THEN r.num_of_votes >= 50
        WHEN m.release_year < 1950 THEN r.num_of_votes >= 100
        WHEN m.release_year < 1970 THEN r.num_of_votes >= 500
        WHEN m.release_year < 1990 THEN r.num_of_votes >= 1000
        ELSE r.num_of_votes >= 10000
    END
GROUP BY m.RELEASE_YEAR
HAVING COUNT(DISTINCT m.movie_id) >= 5
ORDER BY release_yr_avg_rating DESC
LIMIT 10 

