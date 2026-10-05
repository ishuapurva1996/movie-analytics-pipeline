WITH tmdb_genres AS (
    SELECT * FROM {{ source('tmdb','genres')}}
)
SELECT 
    ID AS tmdb_genre_id,
    NAME AS genre_name
FROM tmdb_genres
WHERE COALESCE(LOWER(TRIM(NAME)), '') <> 'news'
