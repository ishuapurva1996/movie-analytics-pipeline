SELECT 
    COUNT( DISTINCT MOVIE_ID) AS Total_Movies
FROM {{ ref('dim_movies')}}