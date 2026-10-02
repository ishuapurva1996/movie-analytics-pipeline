import unittest
from unittest.mock import Mock, call, patch

import pendulum

import movie_pipeline


class AirflowDagConfigurationTests(unittest.TestCase):
    def test_start_date_is_not_in_the_future(self):
        dag = movie_pipeline.movie_analytics_pipeline()

        self.assertLessEqual(
            dag.start_date,
            pendulum.now("America/Los_Angeles"),
        )

    def test_imdb_and_tmdb_use_their_existing_stage_roots(self):
        self.assertEqual(
            movie_pipeline.IMDB_SNOWFLAKE_STAGE,
            "MOVIE_DB.RAW.IMDB_STAGE",
        )
        self.assertEqual(
            movie_pipeline.TMDB_SNOWFLAKE_STAGE,
            "MOVIE_DB.RAW.TMDB_STAGE",
        )

    def test_dbt_role_falls_back_when_connection_role_is_missing(self):
        self.assertEqual(
            movie_pipeline.DBT_ENV["DBT_ROLE"],
            "{{ conn.snowflake_conn.extra_dejson.get('role') or 'ACCOUNTADMIN' }}",
        )

    def test_refresh_uses_a_path_relative_to_the_selected_stage(self):
        cursor = Mock()
        cursor.fetchone.return_value = (True,)
        connection = Mock()
        connection.cursor.return_value = cursor
        hook = Mock()
        hook.get_conn.return_value = connection

        with patch.object(movie_pipeline, "SnowflakeHook", return_value=hook):
            movie_pipeline.refresh_raw_tables(
                [
                    (
                        "MOVIE_DB.RAW.IMDB_NAME_BASICS",
                        "name.basics.tsv.gz",
                        "MOVIE_DB.RAW.IMDB_TSV_FORMAT",
                    )
                ],
                stage="MOVIE_DB.RAW.IMDB_STAGE",
            )

        executed_sql = "\n".join(
            call.args[0]
            for call in cursor.execute.call_args_list
            if call.args
        )
        self.assertIn(
            "FROM @MOVIE_DB.RAW.IMDB_STAGE/name.basics.tsv.gz",
            executed_sql,
        )

    def test_raw_loads_replace_entire_tables(self):
        dag = movie_pipeline.movie_analytics_pipeline()
        task_tables = {
            "load_imdb_raw": [
                "IMDB_NAME_BASICS", "IMDB_TITLE_AKAS", "IMDB_TITLE_BASICS",
                "IMDB_TITLE_CREW", "IMDB_TITLE_PRINCIPALS", "IMDB_TITLE_RATINGS",
            ],
            "load_tmdb_raw": ["TMDB_DETAILS", "TMDB_GENRES", "TMDB_NOW_PLAYING"],
        }

        for task_id, tables in task_tables.items():
            with self.subTest(task_id=task_id):
                hook = Mock()
                cursor = hook.get_conn.return_value.cursor.return_value
                cursor.fetchone.return_value = (True,)

                with patch.object(movie_pipeline, "SnowflakeHook", return_value=hook):
                    dag.get_task(task_id).python_callable()

                # An unconditional DELETE also removes snapshots from earlier dates.
                for table in tables:
                    target = f"MOVIE_DB.RAW.{table}"
                    cursor.execute.assert_has_calls([
                        call("BEGIN"),
                        call(f"DELETE FROM {target}"),
                        call(f"INSERT INTO {target} SELECT * FROM {target}_AIRFLOW_LOAD"),
                        call("COMMIT"),
                    ])

    def test_empty_load_does_not_replace_existing_data(self):
        hook = Mock()
        cursor = hook.get_conn.return_value.cursor.return_value
        cursor.fetchone.return_value = (False,)

        with patch.object(movie_pipeline, "SnowflakeHook", return_value=hook):
            with self.assertRaisesRegex(RuntimeError, "loaded zero rows"):
                movie_pipeline.refresh_raw_tables(
                    [("MOVIE_DB.RAW.TMDB_NOW_PLAYING", "tmdb_now_playing.csv", "TMDB_CSV")],
                    stage="MOVIE_DB.RAW.TMDB_STAGE",
                )

        statements = [item.args[0].strip().upper() for item in cursor.execute.call_args_list]
        self.assertFalse(any(sql.startswith(("DELETE", "TRUNCATE", "INSERT")) for sql in statements))

    def test_failed_insert_rolls_back_refresh(self):
        hook = Mock()
        connection = hook.get_conn.return_value
        cursor = connection.cursor.return_value
        cursor.fetchone.return_value = (True,)

        def fail_insert(sql):
            if sql.startswith("INSERT INTO"):
                raise RuntimeError("insert failed")

        cursor.execute.side_effect = fail_insert
        with patch.object(movie_pipeline, "SnowflakeHook", return_value=hook):
            with self.assertRaisesRegex(RuntimeError, "insert failed"):
                movie_pipeline.refresh_raw_tables(
                    [("MOVIE_DB.RAW.TMDB_NOW_PLAYING", "tmdb_now_playing.csv", "TMDB_CSV")],
                    stage="MOVIE_DB.RAW.TMDB_STAGE",
                )

        cursor.execute.assert_any_call("ROLLBACK")
        self.assertNotIn(call("COMMIT"), cursor.execute.call_args_list)
        cursor.close.assert_called_once()
        connection.close.assert_called_once()

    def test_dbt_build_requests_full_refresh(self):
        dag = movie_pipeline.movie_analytics_pipeline()
        command = dag.get_task("dbt_build").python_callable()

        self.assertIn("--full-refresh", command.split())


if __name__ == "__main__":
    unittest.main()
