import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from airflow.exceptions import AirflowException
from airflow.sdk.exceptions import AirflowTaskTimeout
import pendulum

import movie_pipeline


class AirflowDagConfigurationTests(unittest.TestCase):
    def test_publication_waits_for_successful_dbt_and_dispatch_reuses_export(self):
        dag = movie_pipeline.movie_analytics_pipeline()
        self.assertEqual(dag.max_active_runs, 1)
        self.assertEqual(len(dag.tasks), 10)
        export = dag.get_task('export_dashboard_bundle')
        dispatch = dag.get_task('dispatch_dashboard_pages')
        self.assertEqual(export.upstream_task_ids, {'dbt_build'})
        self.assertEqual(dispatch.upstream_task_ids, {'export_dashboard_bundle'})
        self.assertEqual(export.trigger_rule.value, 'all_success')
        self.assertEqual(dispatch.trigger_rule.value, 'all_success')
        self.assertEqual(export.execution_timeout, timedelta(minutes=10))
        self.assertEqual(export.op_args[0].operator.task_id, 'dbt_build')

    def test_dbt_receipt_is_returned_only_after_command_success(self):
        ti = SimpleNamespace(dag_id='movie_analytics_pipeline', run_id='current', task_id='dbt_build',
                             id='task-instance-id', try_number=2, dag_version_id='version-id',
                             start_date=pendulum.now('UTC').subtract(minutes=1))
        context = {'ti': ti}
        for exit_code in (0, 1, 99):
            build = movie_pipeline.movie_analytics_pipeline().get_task('dbt_build')
            result = SimpleNamespace(exit_code=exit_code, output='private dbt stdout must not enter receipt')
            with (patch.object(build, 'render_template_fields'), patch.object(build, 'get_env', return_value={}),
                  patch.object(build, '_run_inline_command', return_value=result),
                  patch.object(movie_pipeline, 'get_current_context', return_value=context),
                  patch.object(build, 'output_processor', wraps=build.output_processor) as processor):
                if exit_code:
                    with self.assertRaises(AirflowException):
                        build.execute(context)
                    processor.assert_not_called()
                else:
                    receipt = build.execute(context)
                    processor.assert_called_once()
                    self.assertEqual(receipt['task_instance_id'], 'task-instance-id')
                    self.assertEqual(receipt['run_id'], 'current')
                    self.assertEqual(receipt['dag_id'], 'movie_analytics_pipeline')
                    self.assertEqual(receipt['task_id'], 'dbt_build')
                    self.assertEqual(receipt['try_number'], 2)
                    self.assertEqual(receipt['dag_version_id'], 'version-id')
                    self.assertEqual(pendulum.parse(receipt['started_at']), ti.start_date)
                    self.assertGreaterEqual(pendulum.parse(receipt['completed_at']), ti.start_date)
                    self.assertNotIn('stdout', str(receipt))
                    self.assertLess(len(str(receipt)), 1024)

    def test_export_connection_bounds_transport_without_changing_raw_hook(self):
        hook = Mock()
        hook._get_conn_params.return_value = {'account': 'example', 'user': 'example', 'password': 'example'}
        with (patch.object(movie_pipeline, 'SnowflakeHook', return_value=hook),
              patch('snowflake.connector.connect') as connect):
            self.assertIs(movie_pipeline.dashboard_snowflake_connection(), connect.return_value)
        connect.assert_called_once_with(account='example', user='example', password='example',
                                        login_timeout=30, network_timeout=60, socket_timeout=30)

    def test_export_passes_receipt_and_closes_connection_on_task_timeout(self):
        export = movie_pipeline.movie_analytics_pipeline().get_task('export_dashboard_bundle')
        connection = Mock()
        receipt = {'receipt': 'success'}
        context = {'dag': SimpleNamespace(dag_id='movie_analytics_pipeline'), 'run_id': 'current'}
        with (patch.object(movie_pipeline, 'dashboard_snowflake_connection', return_value=connection),
              patch.object(movie_pipeline, 'get_current_context', return_value=context),
              patch('publish_dashboard.export_and_publish', side_effect=AirflowTaskTimeout('bounded task')) as publish):
            with self.assertRaises(AirflowTaskTimeout):
                export.python_callable(receipt)
        publish.assert_called_once_with(connection, 'movie_analytics_pipeline', 'current', receipt)
        connection.close.assert_called_once()

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

        self.assertEqual(command, '/opt/dbt_venv/bin/dbt build --full-refresh '
                         '--project-dir /opt/airflow/project/movie_dbt '
                         '--profiles-dir /opt/airflow/dbt_profiles --target dev')


if __name__ == "__main__":
    unittest.main()
