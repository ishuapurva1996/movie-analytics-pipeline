WITH imdb_title_crew AS (
    SELECT * FROM  {{ source('imdb','title_crew') }}
)
SELECT 
    TCONST AS imdb_id,
    DIRECTORS AS all_director_ids,
    WRITERS AS all_writer_ids
FROM imdb_title_crew