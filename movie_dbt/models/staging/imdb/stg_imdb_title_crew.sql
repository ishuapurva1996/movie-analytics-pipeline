WITH excluded_news_titles AS (
    {{ news_title_ids() }}
),
imdb_title_crew AS (
    SELECT * FROM  {{ source('imdb','title_crew') }}
)
SELECT 
    TCONST AS imdb_id,
    DIRECTORS AS all_director_ids,
    WRITERS AS all_writer_ids
FROM imdb_title_crew
WHERE NOT EXISTS (
    SELECT 1 FROM excluded_news_titles AS excluded
    WHERE excluded.imdb_id = imdb_title_crew.TCONST
)
