WITH imdb_title_principals AS (
    SELECT * FROM  {{ source('imdb','title_principals') }}
)
SELECT 
    TCONST AS imdb_id,
    ORDERING AS principal_order,
    NCONST AS person_id,
    CATEGORY AS job_role,
    JOB AS specific_job,
    CHARACTERS AS characters_played
FROM imdb_title_principals