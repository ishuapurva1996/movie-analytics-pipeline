WITH excluded_news_titles AS (
    {{ news_title_ids() }}
),
tmdb_now_playing AS (
    SELECT *
    FROM {{ source('tmdb', 'now_playing') }} AS playing
    WHERE NOT EXISTS (
        SELECT 1 FROM excluded_news_titles AS excluded
        WHERE excluded.tmdb_id = playing.ID
    )
),

deduplicated AS (
    SELECT *
    FROM tmdb_now_playing
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY ID, REGION, SNAPSHOT_DATE
        ORDER BY POPULARITY DESC, VOTE_COUNT DESC
    ) = 1
)

SELECT
    ID AS tmdb_id,
    TITLE AS movie_title,
    RELEASE_DATE AS now_playing_release_date,
    VOTE_AVERAGE AS now_playing_avg_rating,
    VOTE_COUNT AS now_playing_num_votes,
    GENRE_IDS AS tmdb_genre_ids,
    OVERVIEW AS now_playing_overview,
    POSTER_PATH AS now_playing_poster_path,
    POPULARITY AS now_playing_popularity,
    REGION AS tmdb_region,
    SNAPSHOT_DATE AS snapshot_date
FROM deduplicated
