WITH imdb_title_basics AS (
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