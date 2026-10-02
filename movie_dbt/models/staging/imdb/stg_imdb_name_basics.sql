WITH imdb_name_basics AS (
    SELECT *
    FROM {{ source('imdb', 'name_basics') }}
)

SELECT
    NCONST AS person_id,
    COALESCE(
        NULLIF(TRIM(PRIMARYNAME), ''),
        'Unknown'
    ) AS primary_name,
    BIRTHYEAR AS birth_year,
    DEATHYEAR AS death_year,
    PRIMARYPROFESSION AS primary_professions,
    KNOWNFORTITLES AS known_for_titles
FROM imdb_name_basics