-- Every published bracket is unique, correctly ordered, and reconciled to
-- its declared population. Includes the inclusive upper edge at rating 10.
WITH bins AS (
    SELECT * FROM {{ ref('mart_rating_distribution') }}
), violations AS (
    SELECT 'invalid_bin' AS issue
    FROM bins
    WHERE bucket_order NOT BETWEEN 0 AND 9
       OR rating_bracket IS NULL
       OR rating_bracket <> bucket_order::VARCHAR || '-' || (bucket_order + 1)::VARCHAR
       OR movie_count < 0
       OR total_no_of_movies < movie_count
    UNION ALL
    SELECT 'duplicate_bin' AS issue
    FROM bins
    GROUP BY rating_bracket
    HAVING COUNT(*) <> 1
    UNION ALL
    SELECT 'incorrect_population' AS issue
    FROM bins
    HAVING SUM(movie_count) <> MAX(total_no_of_movies)
        OR MIN(total_no_of_movies) <> MAX(total_no_of_movies)
        OR ABS(SUM(percentage_of_movies) - 100) > 0.051
)
SELECT * FROM violations
