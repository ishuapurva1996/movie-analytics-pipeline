WITH excluded_news_titles AS (
    {{ news_title_ids() }}
),
imdb_title_akas AS (
    SELECT * FROM {{ source('imdb','title_akas') }}
)
SELECT
    TITLEID AS imdb_id,
    ORDERING AS alternate_title_order,
    TITLE AS alternate_title,
    REGION,
    LANGUAGE,
    TYPES AS alternate_title_type,
    ATTRIBUTES AS alternate_title_attributes,
    ISORIGINALTITLE AS is_original_title
FROM imdb_title_akas
WHERE NOT EXISTS (
    SELECT 1 FROM excluded_news_titles AS excluded
    WHERE excluded.imdb_id = imdb_title_akas.TITLEID
)
