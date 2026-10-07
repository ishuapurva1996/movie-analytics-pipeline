WITH excluded_news_titles AS (
    {{ news_title_ids() }}
), title_relations AS (
    {% for model in ['stg_imdb_title_basics', 'stg_imdb_title_ratings', 'stg_imdb_title_crew', 'stg_imdb_title_principals', 'stg_imdb_title_akas'] %}
    SELECT '{{ model }}' AS model_name, imdb_id, NULL::NUMBER AS tmdb_id
    FROM {{ ref(model) }}
    UNION ALL
    {% endfor %}
    {% for model in ['stg_tmdb_details', 'dim_movies', 'fct_movie_ratings', 'fct_now_playing'] %}
    SELECT '{{ model }}' AS model_name, imdb_id, tmdb_id
    FROM {{ ref(model) }}
    UNION ALL
    {% endfor %}
    SELECT 'stg_tmdb_now_playing' AS model_name, NULL::VARCHAR AS imdb_id, tmdb_id
    FROM {{ ref('stg_tmdb_now_playing') }}
)
SELECT titles.model_name, titles.imdb_id, titles.tmdb_id
FROM title_relations AS titles
INNER JOIN excluded_news_titles AS excluded
    ON titles.imdb_id = excluded.imdb_id OR titles.tmdb_id = excluded.tmdb_id
