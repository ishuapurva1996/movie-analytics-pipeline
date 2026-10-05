WITH excluded_news_titles AS (
    {{ news_title_ids() }}
),
IMDB_TITLE_RATINGS AS (
    SELECT * FROM  {{ source('imdb','title_ratings') }}
)
SELECT 
    TCONST AS imdb_id,
    AVERAGERATING AS avg_rating,
    NUMVOTES AS num_of_votes
FROM IMDB_TITLE_RATINGS
WHERE NOT EXISTS (
    SELECT 1 FROM excluded_news_titles AS excluded
    WHERE excluded.imdb_id = IMDB_TITLE_RATINGS.TCONST
)
