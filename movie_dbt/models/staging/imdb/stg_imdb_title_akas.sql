WITH imdb_title_akas AS (
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
    