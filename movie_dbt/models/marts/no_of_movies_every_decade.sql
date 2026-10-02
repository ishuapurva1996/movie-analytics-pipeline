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
)
SELECT 
    decade,
    COUNT(*) AS movies_made_in_decade
FROM dim_movies m
WHERE m.runtime_min IS NOT NULL
  AND m.runtime_min BETWEEN 40 AND 300
  AND decade is NOT NULL
GROUP BY decade
ORDER BY decade
