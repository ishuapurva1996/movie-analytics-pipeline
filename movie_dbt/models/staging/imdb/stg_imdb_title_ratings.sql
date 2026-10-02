WITH IMDB_TITLE_RATINGS AS (
    SELECT * FROM  {{ source('imdb','title_ratings') }}
)
SELECT 
    TCONST AS imdb_id,
    AVERAGERATING AS avg_rating,
    NUMVOTES AS num_of_votes
FROM IMDB_TITLE_RATINGS