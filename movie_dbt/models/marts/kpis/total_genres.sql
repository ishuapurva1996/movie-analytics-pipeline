SELECT
    COUNT(DISTINCT GENRE_ID) AS Total_Genres
FROM {{ ref('dim_genre') }}
