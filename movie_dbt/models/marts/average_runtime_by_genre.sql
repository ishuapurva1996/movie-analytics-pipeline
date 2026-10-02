WITH DIM_MOVIES AS (
    SELECT * FROM {{ ref('dim_movies') }}
),
BRIDGE_MOVIE_GENRES AS (
    SELECT * FROM {{ ref('bridge_movie_genres') }}
)
SELECT  
    g.GENRE_NAME,
    AVG(m.RUNTIME_MIN) AS genre_avg_runtime
FROM BRIDGE_MOVIE_GENRES g
INNER JOIN DIM_MOVIES m
ON m.MOVIE_ID = g.MOVIE_ID
WHERE m.runtime_min IS NOT NULL
  AND m.runtime_min BETWEEN 40 AND 300
GROUP BY g.GENRE_NAME
ORDER BY genre_avg_runtime DESC
