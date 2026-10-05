WITH excluded_news_titles AS (
    {{ news_title_ids() }}
),
imdb_title_basics AS (
    SELECT * FROM  {{ source('imdb','title_basics') }}
)
SELECT 
    TCONST AS imdb_id,
    TITLETYPE AS content_type,
    PRIMARYTITLE AS primary_title,
    ORIGINALTITLE AS original_title,
    ISADULT AS is_Adult,
    STARTYEAR AS start_year,
    ENDYEAR AS end_year,
    RUNTIMEMINUTES AS runtime_min,
    GENRES
FROM imdb_title_basics
WHERE NOT EXISTS (
    SELECT 1 FROM excluded_news_titles AS excluded
    WHERE excluded.imdb_id = imdb_title_basics.TCONST
)
