{% macro has_news_genre(genres_expression) -%}
    REGEXP_LIKE(
        COALESCE({{ genres_expression }}, ''),
        '(^|.*,)[[:space:]]*News[[:space:]]*(,.*|$)',
        'i'
    )
{%- endmacro %}

{% macro news_title_ids() -%}
-- Use raw classifications: staging has already removed these identities.
-- Exclude the whole title, including titles tagged News alongside other genres.
WITH imdb_news AS (
    SELECT DISTINCT TCONST AS imdb_id
    FROM {{ source('imdb', 'title_basics') }}
    WHERE {{ has_news_genre('GENRES') }}
), tmdb_news_genres AS (
    SELECT ID AS genre_id
    FROM {{ source('tmdb', 'genres') }}
    WHERE LOWER(TRIM(NAME)) = 'news'
), directly_tagged_tmdb_news AS (
    SELECT details.ID AS tmdb_id
    FROM {{ source('tmdb', 'details') }} AS details,
         LATERAL FLATTEN(INPUT => TRY_PARSE_JSON(details.GENRES)) AS genre
    WHERE LOWER(TRIM(genre.value:name::VARCHAR)) = 'news'
    UNION
    SELECT playing.ID AS tmdb_id
    FROM {{ source('tmdb', 'now_playing') }} AS playing,
         LATERAL FLATTEN(INPUT => TRY_PARSE_JSON(playing.GENRE_IDS)) AS genre
    WHERE genre.value::NUMBER IN (SELECT genre_id FROM tmdb_news_genres)
), excluded_imdb AS (
    SELECT imdb_id FROM imdb_news
    UNION
    SELECT details.IMDB_ID AS imdb_id
    FROM {{ source('tmdb', 'details') }} AS details
    INNER JOIN directly_tagged_tmdb_news ON details.ID = directly_tagged_tmdb_news.tmdb_id
    WHERE details.IMDB_ID IS NOT NULL
), excluded_tmdb AS (
    SELECT tmdb_id FROM directly_tagged_tmdb_news
    UNION
    SELECT details.ID AS tmdb_id
    FROM {{ source('tmdb', 'details') }} AS details
    INNER JOIN excluded_imdb ON details.IMDB_ID = excluded_imdb.imdb_id
)
SELECT imdb_id, NULL::NUMBER AS tmdb_id FROM excluded_imdb
UNION ALL
SELECT NULL::VARCHAR AS imdb_id, tmdb_id FROM excluded_tmdb
{%- endmacro %}
