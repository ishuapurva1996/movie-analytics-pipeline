SELECT 
    TMDB_REGION,
    COUNT(movie_id) AS no_of_movies_Now_Playing
FROM {{ ref('fct_now_playing') }}
GROUP BY TMDB_REGION
