WITH dim_movies AS (   
    SELECT 
        *,
        CASE 
            WHEN release_year >= 1890  AND release_year < 1900 THEN '1890s'
            WHEN release_year >= 1900  AND release_year < 1910 THEN '1900s'
            WHEN release_year >= 1910  AND release_year < 1920 THEN '1910s'
            WHEN release_year >= 1920  AND release_year < 1930 THEN '1920s'
            WHEN release_year >= 1930  AND release_year < 1940 THEN '1930s'
            WHEN release_year >= 1940  AND release_year < 1950 THEN '1940s'
            WHEN release_year >= 1950  AND release_year < 1960 THEN '1950s'
            WHEN release_year >= 1960  AND release_year < 1970 THEN '1960s'
            WHEN release_year >= 1970  AND release_year < 1980 THEN '1970s'
            WHEN release_year >= 1980  AND release_year < 1990 THEN '1980s'
            WHEN release_year >= 1990  AND release_year < 2000 THEN '1990s'
            WHEN release_year >= 2000  AND release_year < 2010 THEN '2000s'
            WHEN release_year >= 2010  AND release_year < 2020 THEN '2010s'
            WHEN release_year >= 2020  AND release_year < 2030 THEN '2020s'
        END AS decade
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
    m.decade,
    AVG(r.avg_rating) AS decade_avg_rating
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
GROUP BY decade
ORDER BY decade
