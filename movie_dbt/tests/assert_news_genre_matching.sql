-- Exact genre matching must not remove titles just because their names contain
-- "news". Unknown genres remain eligible under the existing population rules.
WITH cases AS (
    SELECT column1 AS genres, column2 AS expected_news
    FROM VALUES
        ('News', TRUE),
        ('Documentary,News', TRUE),
        ('News,Drama', TRUE),
        ('Drama,News,History', TRUE),
        ('Drama, news ,History', TRUE),
        ('Drama,Documentary', FALSE),
        ('Newsreel', FALSE),
        ('NotNews', FALSE),
        ('', FALSE),
        (NULL, FALSE)
)
SELECT genres, expected_news
FROM cases
WHERE {{ has_news_genre('genres') }} <> expected_news
