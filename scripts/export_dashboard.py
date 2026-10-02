"""Extract one bounded, validated public dashboard bundle.

The caller owns the connection, run-eligibility guards and publication. No
credentials, raw source rows or operational run identifiers belong in this file's
public output. Importing this module performs no network or filesystem writes.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import uuid

from jsonschema import Draft202012Validator, FormatChecker


MAX_BUNDLE_BYTES = 2 * 1024 * 1024
QUERY_TIMEOUT_SECONDS = 120
PERCENTAGE_TOLERANCE = 0.051
DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "web_dashboard/data-contract.schema.json"
REGIONS = ("IN", "US")
PEOPLE_MINIMUMS = {
    "actor": 5, "actress": 5, "archive_footage": 5, "casting_director": 5,
    "cinematographer": 4, "composer": 4, "director": 3, "editor": 5,
    "producer": 4, "production_designer": 4, "writer": 4,
}
SOURCES = [
    {"name": "IMDb", "url": "https://developer.imdb.com/non-commercial-datasets/"},
    {"name": "TMDB", "url": "https://www.themoviedb.org"},
]
METRIC_DEFINITIONS = {
    "overview": "Catalog includes movie and TV-movie titles plus TMDB-only titles; adult content is not excluded. Average title rating is unweighted; eligible runtime is 40–300 minutes. Most voted movie uses the preferred vote count, not TMDB popularity.",
    "ratings": "IMDb 1,000+ votes or TMDB 500+ votes; IMDb rating preferred. Brackets include their lower edge; 9–10 includes exactly 10. Percentages use this qualifying population.",
    "genres": "Rating: 1,000+ votes on either source; IMDb rating preferred. Runtime: 40–300 minutes. Each multi-genre title contributes to each genre; source genre vocabularies are not harmonized.",
    "eras": "Counts: runtime 40–300 minutes, years 1890–2029. Rating vote floors: 20 before 1900, 50 before 1930, 100 before 1950, 500 before 1970, 1,000 before 1990, 10,000 thereafter, using IMDb votes when available. Top years require at least five qualifying titles.",
    "top_movies": "100,000+ votes on either source; IMDb rating preferred. Displayed vote count independently prefers IMDb; it can be below the eligibility threshold.",
    "people": "IMDb principal credits for films with 100,000+ votes on either source; IMDb rating preferred. Minimum films: actor/actress/editor/archive_footage/casting_director 5; producer/production_designer/cinematographer/composer/writer 4; director 3. Not a full filmography or individual performance score.",
    "now_playing": "IMDb 10,000+ votes or TMDB 1,000+ votes; IMDb rating preferred. US/IN are exhibition markets, not nationality. A film can be in both. Capture dates are extractor-local dates, not complete-build timestamps.",
}
LIMITATIONS = [
    "IMDb capture date is unavailable. Current TMDB enrichment covers the US/IN now-playing extract only; snapshots are replaced rather than retained.",
    "Genre and era cohorts differ from the full catalog. Ranked lists are truncated. Source ratings and votes are independently preferred, so they can come from different providers.",
    "Repeated IMDb principal credits can weight a film more than once in a person's rating. These ratings do not measure individual performance.",
    "TMDB capture dates are extractor-local calendar dates. A weekly refresh is stale after eight days since the warehouse build or either market's capture date.",
]


class ExportError(ValueError):
    """A safe, non-sensitive export or validation failure."""


def normalize(value):
    """Convert warehouse scalar types without turning unknown values into zero."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ExportError("Non-finite number in dashboard data")
        return normalize(int(value) if value == value.to_integral_value() else float(value))
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ExportError("Non-finite number in dashboard data")
        return int(value) if value.is_integer() else value
    if isinstance(value, datetime):
        return _utc_timestamp(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ExportError("Dashboard object keys must be strings")
        return {key: normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value]
    raise ExportError("Unsupported value type in dashboard data")


def _utc_timestamp(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ExportError("Invalid warehouse or export timestamp") from None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ExportError("Warehouse and export timestamps require an explicit timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,254}", value):
        raise ExportError("Invalid warehouse database or schema identifier")
    return '"' + value.upper() + '"'


def _read(connection, database, schema, relation, columns, *, order="", where="", group="", maximum=1):
    """Bound query results and require the complete, exact SELECT allowlist."""
    selected = ", ".join(f'{expression} AS "{alias}"' for alias, expression in columns)
    sql = f"SELECT {selected} FROM {database}.{schema}.\"{relation.upper()}\""
    if where:
        sql += " WHERE " + where
    if group:
        sql += " GROUP BY " + group
    if order:
        sql += " ORDER BY " + order
    # One extra row detects an invalid upstream mart instead of silently truncating.
    sql += f" LIMIT {maximum + 1}"
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(sql, timeout=QUERY_TIMEOUT_SECONDS)
        names = [column[0].lower() for column in cursor.description]
        if names != [alias for alias, _ in columns]:
            raise ExportError(f"Unexpected columns in dashboard dataset {relation}")
        rows = cursor.fetchmany(maximum + 1)
        if len(rows) > maximum:
            raise ExportError(f"Too many rows in dashboard dataset {relation}")
        if any(len(row) != len(names) for row in rows):
            raise ExportError(f"Incomplete row in dashboard dataset {relation}")
        return [normalize(dict(zip(names, row))) for row in rows]
    except ExportError:
        raise
    except Exception:
        # Connector exceptions may include SQL, account details or credentials.
        raise ExportError(f"Warehouse query failed for dashboard dataset {relation}") from None
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass


def _one(rows, name, *, optional=False):
    if not rows and optional:
        return None
    if len(rows) != 1:
        raise ExportError(f"Expected one row in dashboard dataset {name}")
    return rows[0]


def _unique(rows, field, name):
    if len({row[field] for row in rows}) != len(rows):
        raise ExportError(f"Duplicate identity in {name}")


def _descending(value):
    return (value is None, -value if value is not None else 0)


def _ordered(rows, key, name, *, ranked=False):
    if sorted(rows, key=key) != rows:
        raise ExportError(f"Non-deterministic ordering in {name}")
    if ranked and [row["rank"] for row in rows] != list(range(1, len(rows) + 1)):
        raise ExportError(f"Non-contiguous ranks in {name}")


def _movie_order(row):
    return (_descending(row["rating"]), _descending(row["votes"]), row["movie_id"])


def _recommendation_order(row):
    return (_descending(row["rating"]), _descending(row["votes"]),
            _descending(row["popularity"]), row["movie_id"])


def _serialize(bundle):
    try:
        data = (json.dumps(bundle, ensure_ascii=False, allow_nan=False, sort_keys=True,
                           separators=(",", ":")) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeError, OverflowError):
        raise ExportError("Dashboard bundle cannot be serialized as finite UTF-8 JSON") from None
    if len(data) > MAX_BUNDLE_BYTES:
        raise ExportError("Dashboard bundle exceeds the 2 MiB public size limit")
    return data


def validate_bundle(bundle, allow_synthetic=False, *, schema_path=None):
    """Validate the public contract and cross-field semantics; raise ExportError."""
    _serialize(bundle)
    try:
        schema = json.loads(Path(schema_path or DEFAULT_SCHEMA_PATH).read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        error = next(validator.iter_errors(bundle), None)
    except (OSError, ValueError, TypeError):
        raise ExportError("Dashboard schema is unavailable or invalid") from None
    if error is not None:
        # Do not stringify jsonschema errors: they contain the offending data.
        raise ExportError("Dashboard bundle does not match the public schema")
    metadata = bundle["metadata"]
    if metadata["synthetic"] and not allow_synthetic:
        raise ExportError("Synthetic dashboard data cannot be published")
    if not metadata["synthetic"] and not re.fullmatch(r"[0-9a-f]{32}", metadata["bundle_id"]):
        raise ExportError("Production bundle ID must be an opaque random identifier")
    if metadata["sources"] != SOURCES:
        raise ExportError("Dashboard source attribution must use the approved public links")
    # jsonschema's date-time checker depends on optional packages. Parse all
    # contract dates ourselves as well, so the minimal pinned runtime is strict.
    completed = datetime.fromisoformat(_utc_timestamp(metadata["warehouse_completed_at"]).replace("Z", "+00:00"))
    exported = datetime.fromisoformat(_utc_timestamp(metadata["exported_at"]).replace("Z", "+00:00"))
    if completed > exported:
        raise ExportError("Export timestamp precedes warehouse completion")
    date_values = [*metadata["tmdb_capture_dates"].values(), bundle["now_playing"]["latest_snapshot_date"]]
    date_values.extend(row["release_date"] for data in bundle["now_playing"]["regions"].values()
                       for row in data["recommendations"] if row["release_date"] is not None)
    try:
        for value in date_values:
            date.fromisoformat(value)
    except ValueError:
        raise ExportError("Invalid calendar date in dashboard data") from None

    overview = bundle["overview"]
    ratings = bundle["ratings"]
    if not ratings["population_count"] <= overview["rated_movies"] <= overview["total_movies"]:
        raise ExportError("Rating populations do not reconcile with the catalog")
    bins = ratings["bins"]
    _unique(bins, "order", "rating bins")
    _unique(bins, "bracket", "rating bins")
    _ordered(bins, lambda row: row["order"], "rating bins")
    if any(row["bracket"] != f'{row["order"]}-{row["order"] + 1}' for row in bins):
        raise ExportError("Rating bin labels do not match their order")
    population = ratings["population_count"]
    if sum(row["movie_count"] for row in bins) != population:
        raise ExportError("Rating bin counts do not reconcile")
    if population == 0:
        if bins:
            raise ExportError("An empty rating population must have no bins")
    else:
        if abs(sum(row["percentage"] for row in bins) - 100) > PERCENTAGE_TOLERANCE:
            raise ExportError("Rating bin percentages do not sum to 100")
        if any(abs(row["percentage"] - row["movie_count"] * 100 / population) > 0.0051 for row in bins):
            raise ExportError("Rating bin percentages do not match their counts")

    for name, field in (("ratings", "avg_rating"), ("runtimes", "avg_runtime_minutes")):
        rows = bundle["genres"][name]
        _unique(rows, "genre", "genre " + name)
        _ordered(rows, lambda row: (_descending(row[field]), row["genre"]), "genre " + name)
    for name in ("counts", "ratings"):
        rows = bundle["eras"][name]
        _unique(rows, "decade", "era " + name)
        _ordered(rows, lambda row: row["decade"], "era " + name)
    years = bundle["eras"]["top_years"]
    _unique(years, "year", "top years")
    _ordered(years, lambda row: (_descending(row["avg_rating"]), row["year"]), "top years", ranked=True)
    movies = bundle["top_movies"]
    _unique(movies, "movie_id", "top movies")
    _ordered(movies, _movie_order, "top movies", ranked=True)
    people = bundle["people"]
    _ordered(people, lambda row: (row["role"], row["rank"]), "people roles")
    for role, minimum in PEOPLE_MINIMUMS.items():
        rows = [row for row in people if row["role"] == role]
        _unique(rows, "person_id", "people role " + role)
        _ordered(rows, lambda row: (_descending(row["avg_rating"]), row["person_id"]), "people role " + role, ranked=True)
        if len(rows) > 20 or any(row["movie_count"] < minimum for row in rows):
            raise ExportError("People rows violate the role's eligibility or size limit")

    now_playing = bundle["now_playing"]
    if now_playing["latest_snapshot_date"] != max(metadata["tmdb_capture_dates"].values()):
        raise ExportError("Latest snapshot does not reconcile with regional capture dates")
    for region in REGIONS:
        data = now_playing["regions"][region]
        rows = data["recommendations"]
        if data["movie_count"] < 1 or len(rows) > data["movie_count"]:
            raise ExportError("Now-playing market coverage or counts are invalid")
        _unique(rows, "movie_id", "recommendations " + region)
        _ordered(rows, _recommendation_order, "recommendations " + region, ranked=True)


def extract_bundle(connection, warehouse_completed_at, *, database="MOVIE_DB",
                   analytics_schema="ANALYTICS", curated_schema="CURATED",
                   exported_at=None, schema_path=None):
    """Read all required marts through an existing DB-API connection, then validate.

    Callers must prove the owning Airflow run is eligible immediately before and
    after this function. It deliberately cannot establish ownership from SQL.
    """
    completed = _utc_timestamp(warehouse_completed_at)
    database = _identifier(database)
    analytics_schema = _identifier(analytics_schema)
    curated_schema = _identifier(curated_schema)

    def read(relation, columns, **kwargs):
        return _read(connection, database, analytics_schema, relation, columns, **kwargs)

    overview = {}
    for public, relation, source in (
        ("total_movies", "total_movies", "total_movies"),
        ("rated_movies", "rated_movies", "total_rated_movies"),
        ("avg_rating", "avg_movie_rating", "avg_movie_rating"),
        ("avg_runtime_minutes", "average_runtime", "average_runtime"),
    ):
        overview[public] = _one(read(relation, [(public, source)]), relation)[public]
    movie_columns = [("movie_id", "movie_id"), ("title", "movie_name"),
                     ("rating", "avg_rating"), ("votes", "num_of_votes")]
    movie_order = "avg_rating DESC NULLS LAST, num_of_votes DESC NULLS LAST, movie_id ASC"
    for public, relation, order in (
        ("highest_rated_movie", "highest_rated_movie", movie_order),
        ("most_voted_movie", "most_popular_movie", "num_of_votes DESC NULLS LAST, movie_id ASC"),
    ):
        overview[public] = _one(read(relation, movie_columns, order=order), relation, optional=True)

    bins = read("mart_rating_distribution", [
        ("bracket", "rating_bracket"), ("order", "bucket_order"),
        ("movie_count", "movie_count"), ("percentage", "percentage_of_movies"),
        ("population_count", "total_no_of_movies"),
    ], order="bucket_order ASC", maximum=10)
    population = bins[0]["population_count"] if bins else 0
    if any(row.pop("population_count") != population for row in bins):
        raise ExportError("Rating bins disagree on their population")
    genres = {
        "ratings": read("average_rating_by_genre", [("genre", "genre_name"), ("avg_rating", "genre_avg_rating")],
                        order="genre_avg_rating DESC NULLS LAST, genre_name ASC", maximum=1000),
        "runtimes": read("average_runtime_by_genre", [("genre", "genre_name"), ("avg_runtime_minutes", "genre_avg_runtime")],
                         order="genre_avg_runtime DESC NULLS LAST, genre_name ASC", maximum=1000),
    }
    eras = {
        "counts": read("no_of_movies_every_decade", [("decade", "decade"), ("movie_count", "movies_made_in_decade")], order="decade ASC", maximum=14),
        "ratings": read("decade_avg_rating", [("decade", "decade"), ("avg_rating", "decade_avg_rating")],
                        where="decade IS NOT NULL", order="decade ASC", maximum=14),
        "top_years": read("mart_top_years", [("year", "release_year"), ("avg_rating", "release_yr_avg_rating"), ("movie_count", "movie_count")],
                          order="release_yr_avg_rating DESC NULLS LAST, release_year ASC", maximum=10),
    }
    eras["top_years"] = [dict(row, rank=index) for index, row in enumerate(eras["top_years"], 1)]
    movies = read("mart_top_movies", [("rank", "movie_rank")] + movie_columns, order="movie_rank ASC", maximum=10)
    people = read("mart_top_people", [
        ("role", "job_role"), ("rank", "job_rank"), ("person_id", "person_id"),
        ("name", "person_name"), ("movie_count", "movie_count"), ("avg_rating", "person_rating"),
    ], order="job_role ASC, job_rank ASC", maximum=220)
    region_counts = read("number_of_movies_now_playing", [("region", "tmdb_region"), ("movie_count", "no_of_movies_now_playing")],
                         order="tmdb_region ASC", maximum=2)
    if [row["region"] for row in region_counts] != list(REGIONS):
        raise ExportError("Both US and IN now-playing markets are required")
    regions = {row["region"]: {"movie_count": row["movie_count"], "recommendations": []} for row in region_counts}
    recommendations = read("mart_now_playing_recommendations", [
        ("region", "tmdb_region"), ("rank", "recommendation_rank"), *movie_columns,
        ("release_date", "now_playing_release_date"), ("overview", "now_playing_overview"),
        ("popularity", "now_playing_popularity"),
    ], order="tmdb_region ASC, recommendation_rank ASC", maximum=10)
    for row in recommendations:
        region = row.pop("region")
        if region not in regions:
            raise ExportError("Unsupported recommendation market")
        regions[region]["recommendations"].append(row)
    latest = _one(read("latest_now_playing_snapshot", [("latest_snapshot_date", "latest_now_playing_snapshot")]), "latest_now_playing_snapshot")
    capture_rows = _read(connection, database, curated_schema, "fct_now_playing", [
        ("region", "tmdb_region"), ("min_capture_date", "MIN(snapshot_date)"),
        ("max_capture_date", "MAX(snapshot_date)"), ("row_count", "COUNT(*)"),
        ("unique_movie_count", "COUNT(DISTINCT tmdb_id)"), ("capture_date_count", "COUNT(snapshot_date)"),
    ], group="tmdb_region", order="tmdb_region ASC", maximum=2)
    capture_dates = _capture_dates(capture_rows, regions)
    bundle = {
        "schema_version": 1,
        "metadata": {
            "bundle_id": uuid.uuid4().hex, "warehouse_completed_at": completed,
            "exported_at": _utc_timestamp(exported_at if exported_at is not None else datetime.now(timezone.utc)),
            "tmdb_capture_dates": capture_dates, "imdb_capture_date": None,
            "synthetic": False, "sources": [dict(source) for source in SOURCES],
            "metric_definitions": dict(METRIC_DEFINITIONS), "limitations": list(LIMITATIONS),
        },
        "overview": overview, "ratings": {"population_count": population, "bins": bins},
        "genres": genres, "eras": eras, "top_movies": movies, "people": people,
        "now_playing": {**latest, "regions": regions},
    }
    validate_bundle(bundle, schema_path=schema_path)
    return bundle


def _capture_dates(rows, regions):
    if [row["region"] for row in rows] != list(REGIONS):
        raise ExportError("Capture metadata requires both US and IN markets")
    result = {}
    for row in rows:
        region = row["region"]
        if not (isinstance(row["row_count"], int) and row["row_count"] > 0
                and row["row_count"] == row["unique_movie_count"] == row["capture_date_count"] == regions[region]["movie_count"]):
            raise ExportError("Now-playing source identities, dates or counts do not reconcile")
        if row["min_capture_date"] is None or row["min_capture_date"] != row["max_capture_date"]:
            raise ExportError("Inconsistent now-playing capture dates within a market")
        result[region] = row["min_capture_date"]
    return result


def write_bundle(bundle, output_path, *, allow_synthetic=False, schema_path=None):
    """Validate before atomically replacing output; return small private metadata."""
    validate_bundle(bundle, allow_synthetic=allow_synthetic, schema_path=schema_path)
    data = _serialize(bundle)
    destination = Path(output_path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix=".dashboard-", suffix=".tmp",
                                         dir=destination.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except OSError:
        raise ExportError("Could not atomically write dashboard bundle") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {
        "path": str(destination.resolve()), "sha256": hashlib.sha256(data).hexdigest(),
        "byte_count": len(data), "schema_version": bundle["schema_version"],
        **{field: bundle["metadata"][field] for field in ("bundle_id", "warehouse_completed_at", "exported_at")},
    }
