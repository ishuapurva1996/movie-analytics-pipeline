-- Rank checks run on the actual marts so a physical table order cannot define
-- ties. The exporter separately checks grain uniqueness and list limits.
WITH movie_ranks AS (
    SELECT movie_rank AS actual_rank,
           ROW_NUMBER() OVER (ORDER BY avg_rating DESC NULLS LAST,
               num_of_votes DESC NULLS LAST, movie_id ASC) AS expected_rank
    FROM {{ ref('mart_top_movies') }}
), people_ranks AS (
    SELECT job_rank AS actual_rank,
           ROW_NUMBER() OVER (PARTITION BY job_role
               ORDER BY person_rating DESC NULLS LAST, person_id ASC) AS expected_rank
    FROM {{ ref('mart_top_people') }}
), recommendation_ranks AS (
    SELECT recommendation_rank AS actual_rank,
           ROW_NUMBER() OVER (PARTITION BY tmdb_region
               ORDER BY avg_rating DESC NULLS LAST, num_of_votes DESC NULLS LAST,
               now_playing_popularity DESC NULLS LAST, movie_id ASC) AS expected_rank
    FROM {{ ref('mart_now_playing_recommendations') }}
)
SELECT 'movie' AS list_name, actual_rank, expected_rank FROM movie_ranks
WHERE actual_rank <> expected_rank
UNION ALL
SELECT 'people' AS list_name, actual_rank, expected_rank FROM people_ranks
WHERE actual_rank <> expected_rank
UNION ALL
SELECT 'recommendation' AS list_name, actual_rank, expected_rank FROM recommendation_ranks
WHERE actual_rank <> expected_rank
