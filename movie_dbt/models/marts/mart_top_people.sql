WITH rated_movies AS (
    SELECT *,
    COALESCE(IMDB_AVG_RATING, TMDB_AVG_RATING) AS avg_rating,
    COALESCE(IMDB_NUM_OF_VOTES, TMDB_NUM_OF_VOTES) AS num_of_votes
    FROM {{ ref('fct_movie_ratings')}}
    WHERE (IMDB_NUM_OF_VOTES IS NOT NULL OR TMDB_NUM_OF_VOTES IS NOT NULL)
    AND (IMDB_NUM_OF_VOTES >= 100000 OR TMDB_NUM_OF_VOTES >=100000)
),
movie_people AS (
    SELECT * FROM {{ ref('bridge_movie_people') }}
),
movie_people_rated AS (
    SELECT 
        p.MOVIE_ID,
        p.PERSON_ID,
        p.JOB_ROLE,
        r.avg_rating,
        r.num_of_votes
    FROM movie_people p
    INNER JOIN rated_movies r
    ON p.MOVIE_ID = r.MOVIE_ID
),
avg_rating_by_job AS (
    SELECT 
        PERSON_ID,
        JOB_ROLE,
        AVG(avg_rating) AS person_rating,
        SUM(num_of_votes) AS total_votes,
        COUNT(DISTINCT movie_id) AS movie_count
    FROM movie_people_rated
    GROUP BY (PERSON_ID, JOB_ROLE)
    HAVING 
        CASE 
            WHEN JOB_ROLE IN ('actor', 'actress', 'editor') THEN COUNT(DISTINCT movie_id) >= 5
            WHEN JOB_ROLE IN ('archive_footage', 'casting_director') THEN COUNT(DISTINCT movie_id) >= 5
            WHEN JOB_ROLE IN ('production_designer', 'producer') THEN COUNT(DISTINCT movie_id) >= 4
            WHEN JOB_ROLE IN ('cinematographer', 'composer', 'writer' ) THEN COUNT(DISTINCT movie_id) >= 4
            WHEN job_role = 'director' THEN COUNT(DISTINCT movie_id) >= 3
        END
),
rank_by_job AS (
    SELECT 
        PERSON_ID,
        JOB_ROLE,
        person_rating,
        movie_count,
        ROW_NUMBER() OVER (PARTITION BY JOB_ROLE ORDER BY person_rating DESC NULLS LAST, PERSON_ID ASC) AS rn
    FROM avg_rating_by_job
),
dim_person AS (
    SELECT * FROM {{ ref('dim_person')}}
)
SELECT 
    r.PERSON_ID,
    r.JOB_ROLE,
    r.person_rating,
    r.rn AS job_rank,
    r.movie_count,
    p.PERSON_NAME,
    p.BIRTH_YEAR,
    p.DEATH_YEAR
FROM rank_by_job r
INNER JOIN DIM_PERSON p
ON p.PERSON_ID = r.PERSON_ID
WHERE rn <= 20
ORDER BY job_role ASC, rn ASC
