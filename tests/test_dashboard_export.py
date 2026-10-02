"""Exporter fault injection without a warehouse or publication credentials."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import traceback
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import export_dashboard
from export_dashboard import ExportError, extract_bundle, normalize, validate_bundle, write_bundle


def fixture():
    return json.loads((ROOT / "tests/fixtures/dashboard/synthetic-dashboard.json").read_text())


def warehouse_rows():
    """Hand-built DB-API results, at the SELECT aliases used in the public contract."""
    bundle = fixture()
    overview = bundle["overview"]
    return {
        "total_movies": [{"total_movies": 12}],
        "rated_movies": [{"rated_movies": 10}],
        "avg_movie_rating": [{"avg_rating": Decimal("7.8")}],
        "average_runtime": [{"avg_runtime_minutes": Decimal("112.5")}],
        "highest_rated_movie": [overview["highest_rated_movie"]],
        "most_popular_movie": [overview["most_voted_movie"]],
        "mart_rating_distribution": [dict(row, population_count=Decimal("5")) for row in bundle["ratings"]["bins"]],
        "average_rating_by_genre": bundle["genres"]["ratings"],
        "average_runtime_by_genre": bundle["genres"]["runtimes"],
        "no_of_movies_every_decade": bundle["eras"]["counts"],
        "decade_avg_rating": bundle["eras"]["ratings"],
        "mart_top_years": [{key: value for key, value in row.items() if key != "rank"} for row in bundle["eras"]["top_years"]],
        "mart_top_movies": bundle["top_movies"],
        "mart_top_people": bundle["people"],
        "number_of_movies_now_playing": [{"region": region, "movie_count": data["movie_count"]}
                                         for region, data in sorted(bundle["now_playing"]["regions"].items())],
        "mart_now_playing_recommendations": [dict(row, region=region)
                                            for region, data in sorted(bundle["now_playing"]["regions"].items())
                                            for row in data["recommendations"]],
        "latest_now_playing_snapshot": [{"latest_snapshot_date": date(2026, 10, 1)}],
        "fct_now_playing": [{"region": region, "min_capture_date": date(2026, 10, 1),
                             "max_capture_date": date(2026, 10, 1), "row_count": count,
                             "unique_movie_count": count, "capture_date_count": count}
                            for region, count in (("IN", 1), ("US", 2))],
    }


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, *, timeout):
        self.connection.queries.append(sql)
        self.connection.query_timeouts.append(timeout)
        self.relation = re.search(r'FROM "[^"]+"\."[^"]+"\."([^"]+)"', sql)[1].lower()
        if self.relation == self.connection.fail_relation:
            raise RuntimeError("SECRET_TOKEN private-account private-bucket raw SQL")
        self.names = re.findall(r' AS "([^"]+)"', sql)
        self.description = [(name,) for name in self.names]
        if self.relation == self.connection.missing_column:
            self.description.pop()

    def fetchmany(self, count):
        self.connection.fetch_sizes.append(count)
        return [tuple(row[name] for name in self.names) for row in self.connection.rows[self.relation]][:count]

    def close(self):
        self.connection.closed_cursors += 1


class FakeConnection:
    def __init__(self):
        self.rows = warehouse_rows()
        self.queries = []
        self.query_timeouts = []
        self.fetch_sizes = []
        self.closed_cursors = 0
        self.fail_relation = None
        self.missing_column = None

    def cursor(self):
        return FakeCursor(self)


def extract(connection, **kwargs):
    return extract_bundle(connection, datetime(2026, 10, 1, 18, tzinfo=timezone.utc),
                          exported_at=datetime(2026, 10, 1, 18, 5, tzinfo=timezone.utc), **kwargs)


class DashboardExportTests(unittest.TestCase):
    def test_integral_float_bucket_orders_from_snowflake_are_normalized(self):
        connection = FakeConnection()
        for row in connection.rows['mart_rating_distribution']:
            row['order'] = float(row['order'])
        bundle = extract(connection)
        self.assertEqual([row['bracket'] for row in bundle['ratings']['bins']], ['7-8', '9-10'])
        self.assertTrue(all(type(row['order']) is int for row in bundle['ratings']['bins']))

    def test_synthetic_fixture_requires_explicit_opt_in(self):
        bundle = fixture()
        with self.assertRaises(ExportError):
            validate_bundle(bundle)
        validate_bundle(bundle, allow_synthetic=True)

    def test_complete_extraction_reconciles_and_uses_only_bounded_selects(self):
        connection = FakeConnection()
        bundle = extract(connection)
        expected = fixture()
        for section in expected:
            if section != "metadata":
                self.assertEqual(bundle[section], expected[section])
        self.assertRegex(bundle["metadata"]["bundle_id"], r"^[0-9a-f]{32}$")
        self.assertFalse(bundle["metadata"]["synthetic"])
        self.assertIsNone(bundle["metadata"]["imdb_capture_date"])
        self.assertEqual(len(connection.queries), 18)
        self.assertEqual(connection.closed_cursors, 18)
        self.assertEqual(connection.query_timeouts, [120] * 18)
        self.assertLessEqual(max(connection.fetch_sizes), 1001)
        for query in connection.queries:
            self.assertTrue(query.startswith("SELECT "))
            self.assertNotIn("SELECT *", query)
            self.assertIn(" LIMIT ", query)
            self.assertNotIn("birth_year", query.lower())
        self.assertIn("COUNT(DISTINCT tmdb_id)", connection.queries[-1])
        self.assertIn("COUNT(snapshot_date)", connection.queries[-1])
        self.assertIn("GROUP BY tmdb_region", connection.queries[-1])
        self.assertNotIn("private", json.dumps(bundle))

    def test_decimal_date_datetime_and_null_normalization(self):
        self.assertEqual(normalize({"a": Decimal("2.0"), "b": Decimal("1.25"), "c": None,
                                    "d": date(2026, 10, 1)}),
                         {"a": 2, "b": 1.25, "c": None, "d": "2026-10-01"})
        self.assertEqual(normalize(datetime(2026, 10, 1, 11, tzinfo=timezone(timedelta(hours=-7)))),
                         "2026-10-01T18:00:00Z")
        connection = FakeConnection()
        connection.rows["avg_movie_rating"][0]["avg_rating"] = None
        bundle = extract(connection)
        self.assertIsNone(bundle["overview"]["avg_rating"])
        for value in (float("nan"), float("inf"), Decimal("NaN"), Decimal("Infinity")):
            with self.subTest(value=str(value)), self.assertRaises(ExportError):
                normalize(value)

    def test_missing_kpi_row_column_and_relation_fail_closed(self):
        for fault in ("missing_row", "duplicate_row", "column", "relation"):
            connection = FakeConnection()
            if fault == "missing_row":
                connection.rows["total_movies"] = []
            elif fault == "duplicate_row":
                connection.rows["total_movies"] *= 2
            elif fault == "column":
                connection.missing_column = "total_movies"
            else:
                connection.fail_relation = "total_movies"
            with self.subTest(fault=fault), self.assertRaises(ExportError):
                extract(connection)

    def test_query_failure_suppresses_sensitive_connector_exception(self):
        connection = FakeConnection()
        connection.fail_relation = "fct_now_playing"
        try:
            extract(connection)
        except ExportError:
            rendered = traceback.format_exc()
        else:
            self.fail("The final query failure must fail the complete export")
        self.assertNotIn("SECRET_TOKEN", rendered)
        self.assertNotIn("private-account", rendered)
        self.assertIn("fct_now_playing", rendered)
        self.assertEqual(connection.closed_cursors, 18)

    def test_final_query_failure_preserves_prior_output(self):
        connection = FakeConnection()
        connection.fail_relation = "fct_now_playing"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dashboard.json"
            path.write_bytes(b"prior complete bundle")
            with self.assertRaises(ExportError):
                write_bundle(extract(connection), path)
            self.assertEqual(path.read_bytes(), b"prior complete bundle")
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_region_source_faults_are_rejected(self):
        for field, value in (("min_capture_date", date(2026, 9, 30)),
                             ("unique_movie_count", 0), ("capture_date_count", 0),
                             ("row_count", 9), ("region", "XX"),
                             ("min_capture_date", None)):
            connection = FakeConnection()
            connection.rows["fct_now_playing"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ExportError):
                extract(connection)
        for relation in ("fct_now_playing", "number_of_movies_now_playing"):
            connection = FakeConnection()
            connection.rows[relation].pop()
            with self.subTest(relation=relation), self.assertRaises(ExportError):
                extract(connection)

    def test_empty_eligible_recommendations_are_valid_for_both_markets(self):
        connection = FakeConnection()
        connection.rows["mart_now_playing_recommendations"] = []
        bundle = extract(connection)
        self.assertTrue(all(not data["recommendations"] for data in bundle["now_playing"]["regions"].values()))

    def test_upstream_ranked_mart_overflow_is_detected_without_truncation(self):
        for relation, maximum in (("mart_top_movies", 10), ("mart_top_people", 220),
                                  ("mart_now_playing_recommendations", 10), ("mart_top_years", 10)):
            connection = FakeConnection()
            connection.rows[relation] = [deepcopy(connection.rows[relation][0]) for _ in range(maximum + 1)]
            with self.subTest(relation=relation), self.assertRaisesRegex(ExportError, "Too many rows"):
                extract(connection)

    def test_histogram_faults_are_rejected(self):
        mutations = (
            lambda bins: bins.append(deepcopy(bins[0])),
            lambda bins: bins.reverse(),
            lambda bins: bins[0].update(movie_count=4),
            lambda bins: bins[0].update(percentage=59),
            lambda bins: bins[0].update(bracket="6-7"),
            lambda bins: (bins[0].update(percentage=55), bins[1].update(percentage=45)),
        )
        for mutate in mutations:
            bundle = fixture()
            mutate(bundle["ratings"]["bins"])
            with self.subTest(mutate=mutate), self.assertRaises(ExportError):
                validate_bundle(bundle, allow_synthetic=True)
        connection = FakeConnection()
        connection.rows["mart_rating_distribution"][1]["population_count"] = 6
        with self.assertRaises(ExportError):
            extract(connection)

    def test_empty_histogram_and_accumulated_percentage_rounding_are_valid(self):
        bundle = fixture()
        bundle["ratings"] = {"population_count": 0, "bins": []}
        validate_bundle(bundle, allow_synthetic=True)
        bundle["overview"].update(total_movies=30, rated_movies=30)
        bundle["ratings"] = {"population_count": 30, "bins": [
            {"bracket": f"{index}-{index + 1}", "order": index,
             "movie_count": count, "percentage": round(count / 30 * 100, 2)}
            for index, count in enumerate([1] * 9 + [21])
        ]}
        self.assertAlmostEqual(sum(row["percentage"] for row in bundle["ratings"]["bins"]), 99.97)
        validate_bundle(bundle, allow_synthetic=True)

    def test_ranked_movie_tie_breaks_null_order_and_identity_are_enforced(self):
        bundle = fixture()
        first, second = bundle["top_movies"]
        second.update(rating=first["rating"], votes=first["votes"])
        validate_bundle(bundle, allow_synthetic=True)
        for field, value in (("movie_id", first["movie_id"]), ("rank", 3), ("rating", 10.1)):
            bad = deepcopy(bundle)
            bad["top_movies"][1][field] = value
            with self.subTest(field=field), self.assertRaises(ExportError):
                validate_bundle(bad, allow_synthetic=True)
        first["rating"] = None
        with self.assertRaises(ExportError):
            validate_bundle(bundle, allow_synthetic=True)
        bundle["top_movies"].reverse()
        for rank, row in enumerate(bundle["top_movies"], 1):
            row["rank"] = rank
        validate_bundle(bundle, allow_synthetic=True)

    def test_person_identity_is_unique_within_role_and_minimum_is_role_specific(self):
        bundle = fixture()
        bundle["people"][1]["person_id"] = bundle["people"][0]["person_id"]
        validate_bundle(bundle, allow_synthetic=True)
        bundle["people"].insert(1, dict(bundle["people"][0], rank=2))
        with self.assertRaises(ExportError):
            validate_bundle(bundle, allow_synthetic=True)
        bundle = fixture()
        bundle["people"][0]["movie_count"] = 4
        with self.assertRaises(ExportError):
            validate_bundle(bundle, allow_synthetic=True)

    def test_movie_identity_is_unique_within_recommendation_market(self):
        bundle = fixture()
        row = bundle["now_playing"]["regions"]["US"]["recommendations"][0]
        bundle["now_playing"]["regions"]["IN"]["recommendations"] = [deepcopy(row)]
        validate_bundle(bundle, allow_synthetic=True)
        bundle["now_playing"]["regions"]["US"]["recommendations"].append(dict(row, rank=2))
        with self.assertRaises(ExportError):
            validate_bundle(bundle, allow_synthetic=True)

    def test_recommendation_popularity_breaks_ties_and_region_limit_is_enforced(self):
        bundle = fixture()
        data = bundle["now_playing"]["regions"]["US"]
        data["recommendations"].append(dict(data["recommendations"][0], rank=2,
                                            movie_id="synthetic-z", popularity=10))
        validate_bundle(bundle, allow_synthetic=True)
        data["recommendations"][1]["popularity"] = 20
        with self.assertRaises(ExportError):
            validate_bundle(bundle, allow_synthetic=True)
        data["movie_count"] = 6
        data["recommendations"] = [dict(data["recommendations"][0], rank=i + 1, movie_id=f"synthetic-{i}") for i in range(6)]
        with self.assertRaises(ExportError):
            validate_bundle(bundle, allow_synthetic=True)

    def test_year_and_genre_identity_and_sort_order_are_enforced(self):
        for section, dataset, field in (("genres", "ratings", "genre"),
                                        ("genres", "runtimes", "genre"),
                                        ("eras", "counts", "decade"),
                                        ("eras", "ratings", "decade"),
                                        ("eras", "top_years", "year")):
            bundle = fixture()
            rows = bundle[section][dataset]
            rows.append(deepcopy(rows[0]))
            with self.subTest(field=field, dataset=dataset), self.assertRaises(ExportError):
                validate_bundle(bundle, allow_synthetic=True)
        bundle = fixture()
        bundle["eras"]["top_years"].append({"rank": 2, "year": 1990, "avg_rating": 8, "movie_count": 5})
        with self.assertRaises(ExportError):
            validate_bundle(bundle, allow_synthetic=True)

    def test_schema_rejects_private_fields_bad_dates_unknown_version_and_invalid_counts(self):
        for section, field, value in (("metadata", "s3_bucket", "private-bucket"),
                                      ("metadata", "warehouse_completed_at", "2026-02-30T00:00:00Z"),
                                      ("overview", "total_movies", -1),
                                      ("overview", "rated_movies", 1.5),
                                      ("overview", "avg_rating", float("nan"))):
            bundle = fixture()
            bundle[section][field] = value
            with self.subTest(field=field), self.assertRaises(ExportError):
                validate_bundle(bundle, allow_synthetic=True)
        bundle = fixture()
        bundle["schema_version"] = 2
        with self.assertRaises(ExportError):
            validate_bundle(bundle, allow_synthetic=True)

    def test_source_dates_and_timestamp_sequence_are_enforced(self):
        for path, value in ((["metadata", "tmdb_capture_dates", "IN"], "2026-02-30"),
                            (["now_playing", "latest_snapshot_date"], "2026-09-30"),
                            (["metadata", "exported_at"], "2026-09-30T18:00:00Z")):
            bundle = fixture()
            destination = bundle
            for field in path[:-1]:
                destination = destination[field]
            destination[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(ExportError):
                validate_bundle(bundle, allow_synthetic=True)
        bundle = fixture()
        bundle["now_playing"]["regions"]["US"]["recommendations"][0]["release_date"] = "2026-02-30"
        with self.assertRaises(ExportError):
            validate_bundle(bundle, allow_synthetic=True)

    def test_oversized_data_never_replaces_prior_output(self):
        bundle = fixture()
        bundle["genres"]["ratings"] = [{"genre": "😀" * 490 + str(i), "avg_rating": 8} for i in range(1000)]
        bundle["genres"]["runtimes"] = [{"genre": "😀" * 490 + str(i), "avg_runtime_minutes": 120} for i in range(1000)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dashboard.json"
            path.write_bytes(b"prior")
            with self.assertRaisesRegex(ExportError, "2 MiB"):
                write_bundle(bundle, path, allow_synthetic=True)
            self.assertEqual(path.read_bytes(), b"prior")

    def test_successful_write_returns_exact_checksum_and_small_metadata(self):
        bundle = extract(FakeConnection())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dashboard.json"
            result = write_bundle(bundle, path)
            self.assertEqual(result["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(result["byte_count"], path.stat().st_size)
            self.assertEqual(result["bundle_id"], bundle["metadata"]["bundle_id"])
            self.assertEqual(json.loads(path.read_bytes()), bundle)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_atomic_replace_failure_cleans_temp_and_preserves_prior_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dashboard.json"
            path.write_bytes(b"prior")
            with patch.object(export_dashboard.os, "replace", side_effect=OSError("write failed")):
                with self.assertRaises(ExportError):
                    write_bundle(fixture(), path, allow_synthetic=True)
            self.assertEqual(path.read_bytes(), b"prior")
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_database_identifiers_and_naive_timestamps_fail_before_querying(self):
        for value in ('MOVIE_DB; DROP DATABASE x', 'db.schema', 'x"'):
            connection = FakeConnection()
            with self.subTest(value=value), self.assertRaises(ExportError):
                extract(connection, database=value)
            self.assertFalse(connection.queries)
        connection = FakeConnection()
        with self.assertRaises(ExportError):
            extract_bundle(connection, datetime(2026, 10, 1))
        self.assertFalse(connection.queries)

    def test_explicit_schema_path_supports_airflow_mount(self):
        with patch.object(export_dashboard, "DEFAULT_SCHEMA_PATH", Path("/missing/schema.json")):
            bundle = extract(FakeConnection(), schema_path=ROOT / "web_dashboard/data-contract.schema.json")
            validate_bundle(bundle, schema_path=ROOT / "web_dashboard/data-contract.schema.json")
            with self.assertRaises(ExportError):
                validate_bundle(bundle)


if __name__ == "__main__":
    unittest.main()
