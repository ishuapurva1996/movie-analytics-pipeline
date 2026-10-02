"""Exercise published SQL with tiny synthetic rows, without warehouse access."""

import json
import math
from pathlib import Path
import re
import sqlite3
import unittest

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:
    Draft202012Validator = None


ROOT = Path(__file__).resolve().parents[1]
MARTS = ROOT / "movie_dbt/models/marts"


class DashboardModelContractTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.create_function("FLOOR", 1, math.floor)
        self.db.create_function("LEAST", 2, min)
        self.db.execute("PRAGMA automatic_index = OFF")
        self.db.execute("CREATE TABLE fct_movie_ratings (movie_id TEXT, imdb_avg_rating REAL, imdb_num_of_votes INTEGER, tmdb_avg_rating REAL, tmdb_num_of_votes INTEGER)")
        self.db.execute("CREATE TABLE dim_movies (movie_id TEXT, movie_name TEXT)")

    def tearDown(self):
        self.db.close()

    def model(self, path):
        sql = (MARTS / path).read_text()
        sql = re.sub(r"\{\{\s*ref\('([^']+)'\)\s*\}\}", r"main.\1", sql)
        # Snowflake permits a SELECT alias inside this window expression;
        # SQLite requires the equivalent aggregate expression itself.
        sql = sql.replace("SUM(movie_count) OVER()", "SUM(COUNT(*)) OVER()")
        return [{key.lower(): value for key, value in dict(row).items()} for row in self.db.execute(sql)]

    def add_rating(self, movie_id, rating, votes=100000, tmdb_rating=None):
        self.db.execute("INSERT INTO fct_movie_ratings VALUES (?, ?, ?, ?, NULL)", (movie_id, rating, votes, tmdb_rating))
        self.db.execute("INSERT INTO dim_movies VALUES (?, ?)", (movie_id, "Synthetic " + movie_id))

    def test_exact_ten_and_nine_point_nine_share_final_bucket(self):
        self.add_rating("synthetic-a", 9.9)
        self.add_rating("synthetic-b", 10)
        self.add_rating("synthetic-unknown", None)
        rows = self.model("mart_rating_distribution.sql")
        self.assertEqual(rows, [{"rating_bracket": "9-10", "bucket_order": 9, "movie_count": 2, "percentage_of_movies": 100, "total_no_of_movies": 2}])

    def test_movie_rank_and_highlights_break_ties_by_movie_id(self):
        # Deliberately insert the larger ID first, so physical row order is wrong.
        self.add_rating("synthetic-b", 8.5)
        self.add_rating("synthetic-a", 8.5)
        rows = self.model("mart_top_movies.sql")
        self.assertEqual([row["movie_id"] for row in rows], ["synthetic-a", "synthetic-b"])
        for path in ("kpis/highest_rated_movie.sql", "kpis/most_popular_movie.sql"):
            with self.subTest(model=path):
                self.assertEqual(self.model(path)[0]["movie_id"], "synthetic-a")

    def test_unknown_rating_stays_null(self):
        self.add_rating("synthetic-unknown", None)
        self.assertEqual(self.model("mart_top_movies.sql")[0]["avg_rating"], None)
        self.assertEqual(self.model("mart_rating_distribution.sql"), [])

    def test_recommendation_ties_break_by_movie_id(self):
        self.db.execute("CREATE TABLE fct_now_playing (movie_id TEXT, movie_name TEXT, tmdb_region TEXT, now_playing_release_date TEXT, now_playing_overview TEXT, now_playing_popularity REAL)")
        for movie_id in ("synthetic-b", "synthetic-a"):
            self.add_rating(movie_id, 8.5)
            self.db.execute("INSERT INTO fct_now_playing VALUES (?, ?, 'US', '2026-01-01', NULL, 1)", (movie_id, movie_id))
        rows = self.model("mart_now_playing_recommendations.sql")
        self.assertEqual([row["movie_id"] for row in rows], ["synthetic-a", "synthetic-b"])


@unittest.skipUnless(Draft202012Validator, "Install the pinned dashboard jsonschema dependency")
class DashboardSchemaTests(unittest.TestCase):
    def setUp(self):
        schema = json.loads((ROOT / "web_dashboard/data-contract.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        self.validator = Draft202012Validator(schema, format_checker=FormatChecker())
        self.fixture = json.loads((ROOT / "tests/fixtures/dashboard/synthetic-dashboard.json").read_text())

    def test_fixture_is_complete_and_visibly_synthetic(self):
        self.validator.validate(self.fixture)
        self.assertTrue(self.fixture["metadata"]["synthetic"])
        self.assertIn("synthetic", self.fixture["metadata"]["bundle_id"])
        self.assertTrue(any("SYNTHETIC" in value for value in self.fixture["metadata"]["limitations"]))

    def test_private_metadata_is_rejected(self):
        self.fixture["metadata"]["s3_bucket"] = "must-never-be-public"
        self.assertFalse(self.validator.is_valid(self.fixture))

    def test_null_metrics_are_preserved_and_invalid_dates_rejected(self):
        self.fixture["overview"]["avg_rating"] = None
        self.validator.validate(self.fixture)
        self.fixture["metadata"]["tmdb_capture_dates"]["US"] = "2026-02-30"
        self.assertFalse(self.validator.is_valid(self.fixture))


if __name__ == "__main__":
    unittest.main()
