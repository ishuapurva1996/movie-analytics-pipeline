SELECT 'dim_genre' AS model_name, genre_name
FROM {{ ref('dim_genre') }}
WHERE LOWER(TRIM(genre_name)) = 'news'
UNION ALL
SELECT 'bridge_movie_genres' AS model_name, genre_name
FROM {{ ref('bridge_movie_genres') }}
WHERE LOWER(TRIM(genre_name)) = 'news'
UNION ALL
SELECT 'stg_tmdb_genres' AS model_name, genre_name
FROM {{ ref('stg_tmdb_genres') }}
WHERE LOWER(TRIM(genre_name)) = 'news'
