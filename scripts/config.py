import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def required_env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Add it to {PROJECT_ROOT / '.env'} or export it before running the script."
        )
    return value


def path_from_env(name, default_relative_path):
    default_path = PROJECT_ROOT / default_relative_path
    return Path(os.getenv(name, str(default_path))).expanduser()


def tmdb_headers():
    token = required_env("TMDB_BEARER_TOKEN")
    if token == "your_tmdb_api_read_access_token_here":
        raise RuntimeError(
            f"TMDB_BEARER_TOKEN is still the placeholder value. "
            f"Add your real TMDB API Read Access Token to {PROJECT_ROOT / '.env'} "
            "or export it before running the script."
        )
    authorization = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    return {
        "accept": "application/json",
        "Authorization": authorization,
    }


def s3_bucket_name():
    return os.getenv("S3_BUCKET_NAME", "movie-pipeline-landing")


def tmdb_output_dir():
    return path_from_env("TMDB_OUTPUT_DIR", "scripts/output_tmdb")


def imdb_output_dir():
    return path_from_env("IMDB_OUTPUT_DIR", "scripts/output_imbd")


def tmdb_now_playing_csv():
    return tmdb_output_dir() / "tmdb_now_playing.csv"


def tmdb_genres_csv():
    return tmdb_output_dir() / "tmdb_genres.csv"


def tmdb_details_csv():
    return tmdb_output_dir() / "tmdb_details.csv"
