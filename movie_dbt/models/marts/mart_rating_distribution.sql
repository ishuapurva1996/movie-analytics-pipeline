WITH FCT_MOVIE_RATINGS AS (
     
    SELECT
        movie_id,
        CASE 
            WHEN COALESCE(imdb_avg_rating, tmdb_avg_rating) >= 0 AND COALESCE(imdb_avg_rating, tmdb_avg_rating) < 1  THEN '0-1'
            WHEN COALESCE(imdb_avg_rating, tmdb_avg_rating) >= 1 AND COALESCE(imdb_avg_rating, tmdb_avg_rating) < 2  THEN '1-2'
            WHEN COALESCE(imdb_avg_rating, tmdb_avg_rating) >= 2 AND COALESCE(imdb_avg_rating, tmdb_avg_rating) < 3  THEN '2-3'
            WHEN COALESCE(imdb_avg_rating, tmdb_avg_rating) >= 3 AND COALESCE(imdb_avg_rating, tmdb_avg_rating) < 4  THEN '3-4'
            WHEN COALESCE(imdb_avg_rating, tmdb_avg_rating) >= 4 AND COALESCE(imdb_avg_rating, tmdb_avg_rating) < 5  THEN '4-5'
            WHEN COALESCE(imdb_avg_rating, tmdb_avg_rating) >= 5 AND COALESCE(imdb_avg_rating, tmdb_avg_rating) < 6  THEN '5-6'
            WHEN COALESCE(imdb_avg_rating, tmdb_avg_rating) >= 6 AND COALESCE(imdb_avg_rating, tmdb_avg_rating) < 7  THEN '6-7'
            WHEN COALESCE(imdb_avg_rating, tmdb_avg_rating) >= 7 AND COALESCE(imdb_avg_rating, tmdb_avg_rating) < 8  THEN '7-8'
            WHEN COALESCE(imdb_avg_rating, tmdb_avg_rating) >= 8 AND COALESCE(imdb_avg_rating, tmdb_avg_rating) < 9  THEN '8-9'
            WHEN COALESCE(imdb_avg_rating, tmdb_avg_rating) >= 9 AND COALESCE(imdb_avg_rating, tmdb_avg_rating) <= 10  THEN '9-10'
        END AS rating_bracket,
        FLOOR(COALESCE(imdb_avg_rating, tmdb_avg_rating)) AS bucket_order
    FROM {{ ref('fct_movie_ratings') }}
    WHERE (IMDB_AVG_RATING IS NOT NULL OR TMDB_AVG_RATING IS NOT NULL)
    AND (IMDB_NUM_OF_VOTES >= 1000 OR TMDB_NUM_OF_VOTES >= 500)
),
BUCKET_COUNTS AS (
    SELECT 
        rating_bracket,
        bucket_order,
        COUNT(*) AS movie_count,
        SUM(movie_count) OVER() AS total_no_of_movies
    FROM FCT_MOVIE_RATINGS
    GROUP BY rating_bracket, bucket_order
    ORDER BY bucket_order ASC
)

SELECT 
    rating_bracket,
    bucket_order,
    movie_count,
    ROUND(((movie_count / total_no_of_movies) * 100),2)  AS percentage_of_movies,
    total_no_of_movies
FROM BUCKET_COUNTS