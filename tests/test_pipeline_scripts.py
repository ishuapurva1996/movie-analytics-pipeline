import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

import pandas as pd
import requests


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import config  # noqa: E402
import imdb_download_upload  # noqa: E402
import tmdb_enrichment  # noqa: E402
import tmdb_genre  # noqa: E402
import tmdb_now_playing  # noqa: E402
import tmdb_upload  # noqa: E402


class PipelineFailureTests(unittest.TestCase):
    def test_s3_bucket_requires_explicit_private_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "S3_BUCKET_NAME"):
                config.s3_bucket_name()
        with patch.dict(os.environ, {"S3_BUCKET_NAME": "configured-test-bucket"}):
            self.assertEqual(config.s3_bucket_name(), "configured-test-bucket")

    def test_imdb_download_http_error_is_raised(self):
        response = Mock()
        response.raise_for_status.side_effect = RuntimeError("download failed")

        with tempfile.TemporaryDirectory() as output_dir:
            with patch.object(imdb_download_upload.requests, "get", return_value=response):
                with self.assertRaisesRegex(RuntimeError, "download failed"):
                    imdb_download_upload.download_imdb_data(
                        ["https://example.com/name.basics.tsv.gz"],
                        output_dir,
                    )

    def test_tmdb_genre_http_error_is_raised(self):
        response = Mock()
        response.raise_for_status.side_effect = RuntimeError("genre request failed")

        with patch.object(tmdb_genre, "tmdb_headers", return_value={}):
            with patch.object(tmdb_genre.requests, "get", return_value=response):
                with self.assertRaisesRegex(RuntimeError, "genre request failed"):
                    tmdb_genre.main()

    def test_tmdb_now_playing_http_error_is_raised(self):
        response = Mock()
        response.raise_for_status.side_effect = RuntimeError("now playing failed")

        with patch.object(tmdb_now_playing.requests, "get", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "now playing failed"):
                tmdb_now_playing.extract_movie_now_playing({}, "US")

    def test_tmdb_upload_failure_keeps_local_files_for_retry(self):
        with tempfile.TemporaryDirectory() as output_dir:
            output_path = Path(output_dir)
            local_file = output_path / "tmdb_genres.csv"
            local_file.write_text("id,name\n1,Action\n")

            with patch.object(tmdb_upload, "tmdb_output_dir", return_value=output_path):
                with patch.object(tmdb_upload, "upload_to_s3", side_effect=RuntimeError("upload failed")):
                    with self.assertRaisesRegex(RuntimeError, "upload failed"):
                        tmdb_upload.main()

            self.assertTrue(local_file.exists())


class TmdbEnrichmentTests(unittest.TestCase):
    URL = "https://api.themoviedb.org/3/movie/1?language=en-US"

    def setUp(self):
        sleep_patch = patch.object(tmdb_enrichment.time, "sleep")
        self.sleep = sleep_patch.start()
        self.addCleanup(sleep_patch.stop)

    def response(self, status=200, movie_id=1):
        response = requests.Response()
        response.status_code = status
        response.url = self.URL
        data = {
            "id": movie_id,
            "imdb_id": f"tt{movie_id}",
            "title": f"Movie {movie_id}",
            "budget": 100,
            "revenue": 200,
            "release_date": "2026-10-01",
            "runtime": 100,
            "status": "Released",
            "original_language": "en",
            "vote_average": 7.0,
            "vote_count": 100,
        }
        response._content = json.dumps(data if status == 200 else {"status_message": "Request failed"}).encode()
        return response

    def test_temporary_http_errors_retry_and_return_movie(self):
        for status in (429, 500, 502, 503, 504):
            with self.subTest(status=status):
                error_response = self.response(status)
                # Error bodies need not be JSON; check HTTP status before parsing.
                error_response._content = b"Service temporarily unavailable"
                with patch.object(tmdb_enrichment.requests, "get", side_effect=[error_response, self.response()]) as get:
                    details = tmdb_enrichment.extract_movieDetails_nowPlaying(self.URL, {})

                self.assertEqual(details["id"], 1)
                self.assertEqual(get.call_count, 2)
                for request in get.call_args_list:
                    self.assertEqual(request.kwargs["timeout"], 30)

    def test_temporary_network_errors_retry_and_return_movie(self):
        for error_type in (requests.Timeout, requests.ConnectionError):
            with self.subTest(error=error_type.__name__):
                with patch.object(tmdb_enrichment.requests, "get", side_effect=[error_type("temporary failure"), self.response()]) as get:
                    details = tmdb_enrichment.extract_movieDetails_nowPlaying(self.URL, {})

                self.assertEqual(details["id"], 1)
                self.assertEqual(get.call_count, 2)

    def test_permanent_http_errors_fail_without_retry(self):
        for status in (400, 401, 403, 404):
            with self.subTest(status=status):
                with patch.object(tmdb_enrichment.requests, "get", return_value=self.response(status)) as get:
                    with self.assertRaises(requests.HTTPError):
                        tmdb_enrichment.extract_movieDetails_nowPlaying(self.URL, {})

                self.assertEqual(get.call_count, 1)

    def test_retries_stop_after_three_attempts(self):
        failures = [self.response(429), self.response(503), requests.Timeout("timeout"), requests.ConnectionError("connection failed")]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                self.sleep.reset_mock()
                with patch.object(tmdb_enrichment.requests, "get", side_effect=[failure] * 3) as get:
                    with self.assertRaises(requests.RequestException):
                        tmdb_enrichment.extract_movieDetails_nowPlaying(self.URL, {})

                self.assertEqual(get.call_count, 3)
                self.assertEqual(self.sleep.call_args_list, [call(1), call(2)])

    def test_failed_enrichment_does_not_publish_partial_csv(self):
        for existing_output in (False, True):
            with self.subTest(existing_output=existing_output), tempfile.TemporaryDirectory() as output_dir:
                input_path = Path(output_dir) / "tmdb_now_playing.csv"
                output_path = Path(output_dir) / "tmdb_details.csv"
                input_path.write_text("id\n1\n2\n")
                previous_csv = "id,title\n99,Previous complete dataset\n"
                if existing_output:
                    output_path.write_text(previous_csv)

                with (
                    patch.object(tmdb_enrichment, "tmdb_headers", return_value={}),
                    patch.object(tmdb_enrichment, "tmdb_now_playing_csv", return_value=input_path),
                    patch.object(tmdb_enrichment, "tmdb_details_csv", return_value=output_path),
                    patch.object(tmdb_enrichment.requests, "get", side_effect=[self.response(), *[self.response(429) for _ in range(3)]]),
                ):
                    with self.assertRaises(requests.HTTPError):
                        tmdb_enrichment.main()

                if existing_output:
                    self.assertEqual(output_path.read_text(), previous_csv)
                else:
                    self.assertFalse(output_path.exists())

    def test_successful_enrichment_writes_all_unique_movies(self):
        with tempfile.TemporaryDirectory() as output_dir:
            input_path = Path(output_dir) / "tmdb_now_playing.csv"
            output_path = Path(output_dir) / "tmdb_details.csv"
            input_path.write_text("id\n1\n1\n2\n")
            with (
                patch.object(tmdb_enrichment, "tmdb_headers", return_value={}),
                patch.object(tmdb_enrichment, "tmdb_now_playing_csv", return_value=input_path),
                patch.object(tmdb_enrichment, "tmdb_details_csv", return_value=output_path),
                patch.object(tmdb_enrichment.requests, "get", side_effect=[self.response(movie_id=1), self.response(movie_id=2)]) as get,
            ):
                tmdb_enrichment.main()

            self.assertEqual(pd.read_csv(output_path)["id"].tolist(), [1, 2])
            self.assertEqual(get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
