WITH rated_movies AS (
    SELECT *,
    COALESCE(IMDB_AVG_RATING, TMDB_AVG_RATING) AS avg_rating,
    COALESCE(IMDB_NUM_OF_VOTES, TMDB_NUM_OF_VOTES) AS num_of_votes
    FROM {{ ref('fct_movie_ratings')}}
    WHERE (IMDB_NUM_OF_VOTES IS NOT NULL OR TMDB_NUM_OF_VOTES IS NOT NULL)
    AND (IMDB_NUM_OF_VOTES >= 1000 OR TMDB_NUM_OF_VOTES >=1000)
),

BRIDGE_MOVIE_GENRES AS (
    SELECT * FROM {{ ref('bridge_movie_genres')}}
)
SELECT 
    g.GENRE_NAME,
    AVG(r.avg_rating) AS genre_avg_rating
FROM BRIDGE_MOVIE_GENRES g
INNER JOIN rated_movies r 
ON g.movie_id = r.movie_id
GROUP BY g.GENRE_NAME
ORDER BY genre_avg_rating DESC