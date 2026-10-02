import os
import subprocess
import sys
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone

import pendulum
from airflow.providers.snowflake.hooks.snowflake import SnowflakeHook
from airflow.sdk import dag, task, get_current_context


PROJECT_SCRIPTS = "/opt/airflow/project/scripts"
DBT_PROJECT_DIR = "/opt/airflow/project/movie_dbt"
DBT_PROFILES_DIR = "/opt/airflow/dbt_profiles"
IMDB_SNOWFLAKE_STAGE = os.environ.get(
    "IMDB_SNOWFLAKE_STAGE",
    "MOVIE_DB.RAW.IMDB_STAGE",
).lstrip("@")
TMDB_SNOWFLAKE_STAGE = os.environ.get(
    "TMDB_SNOWFLAKE_STAGE",
    "MOVIE_DB.RAW.TMDB_STAGE",
).lstrip("@")

DBT_ENV = {
    "DBT_USER": "{{ conn.snowflake_conn.login }}",
    "DBT_PASSWORD": "{{ conn.snowflake_conn.password }}",
    "DBT_ACCOUNT": "{{ conn.snowflake_conn.extra_dejson.account }}",
    "DBT_SCHEMA": "{{ conn.snowflake_conn.schema }}",
    "DBT_ROLE": "{{ conn.snowflake_conn.extra_dejson.get('role') or 'ACCOUNTADMIN' }}",
    "DBT_DATABASE": "{{ conn.snowflake_conn.extra_dejson.database }}",
    "DBT_WAREHOUSE": "{{ conn.snowflake_conn.extra_dejson.warehouse }}",
}


def run_project_script(script_name: str) -> None:
    script_path = os.path.join(PROJECT_SCRIPTS, script_name)
    subprocess.run([sys.executable, script_path], check=True, cwd=PROJECT_SCRIPTS)


def dbt_success_receipt(_output: str) -> dict:
    """BashOperator calls this only after the full dbt command exits with zero."""
    ti = get_current_context()['ti']
    return {
        'schema_version': 1,
        'dag_id': ti.dag_id,
        'run_id': ti.run_id,
        'task_id': ti.task_id,
        'task_instance_id': str(ti.id),
        'try_number': ti.try_number,
        'started_at': ti.start_date.isoformat(),
        'completed_at': datetime.now(timezone.utc).isoformat(),
        'dag_version_id': str(ti.dag_version_id),
    }


def dashboard_snowflake_connection():
    from snowflake.connector import connect

    hook = SnowflakeHook(snowflake_conn_id='snowflake_conn')
    # This provider's get_conn() does not forward transport timeout kwargs.
    # Reuse its auth configuration while bounding this export connection only.
    options = hook._get_conn_params()
    options.update(login_timeout=30, network_timeout=60, socket_timeout=30)
    return connect(**options)


def refresh_raw_tables(
    copy_specs: Iterable[tuple[str, str, str]],
    stage: str,
) -> None:
    """Replace every target's rows after validating its staged load."""
    hook = SnowflakeHook(snowflake_conn_id="snowflake_conn")
    connection = hook.get_conn()
    cursor = connection.cursor()

    try:
        for target_table, object_path, file_format in copy_specs:
            temp_table = f"{target_table}_AIRFLOW_LOAD"

            cursor.execute(
                f"CREATE OR REPLACE TEMPORARY TABLE {temp_table} LIKE {target_table}"
            )
            cursor.execute(
                f"""
                COPY INTO {temp_table}
                FROM @{stage}/{object_path}
                FILE_FORMAT = (FORMAT_NAME = '{file_format}')
                FORCE = TRUE
                """
            )

            cursor.execute(f"SELECT EXISTS(SELECT 1 FROM {temp_table} LIMIT 1)")
            if not cursor.fetchone()[0]:
                raise RuntimeError(
                    f"Snowflake loaded zero rows from @{stage}/{object_path}; "
                    f"{target_table} was left unchanged."
                )

            cursor.execute("BEGIN")
            cursor.execute(f"DELETE FROM {target_table}")
            cursor.execute(f"INSERT INTO {target_table} SELECT * FROM {temp_table}")
            cursor.execute("COMMIT")
    except Exception:
        cursor.execute("ROLLBACK")
        raise
    finally:
        cursor.close()
        connection.close()


@dag(
    dag_id="movie_analytics_pipeline",
    description="Load IMDb and TMDB data, refresh Snowflake RAW, and build dbt models",
    schedule="0 6 * * 1",
    start_date=pendulum.datetime(2026, 1, 1, tz="America/Los_Angeles"),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "airflow",
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["movies", "etl", "dbt"],
)
def movie_analytics_pipeline():
    @task
    def extract_and_upload_imdb() -> None:
        run_project_script("imdb_download_upload.py")

    @task
    def extract_tmdb_genres() -> None:
        run_project_script("tmdb_genre.py")

    @task
    def extract_tmdb_now_playing() -> None:
        run_project_script("tmdb_now_playing.py")

    @task
    def enrich_tmdb_movies() -> None:
        run_project_script("tmdb_enrichment.py")

    @task
    def upload_tmdb_files() -> None:
        run_project_script("tmdb_upload.py")

    @task
    def load_imdb_raw() -> None:
        imdb_file_format = os.environ.get(
            "IMDB_SNOWFLAKE_FILE_FORMAT",
            "MOVIE_DB.RAW.IMDB_TSV_FORMAT",
        )
        refresh_raw_tables(
            [
                ("MOVIE_DB.RAW.IMDB_NAME_BASICS", "name.basics.tsv.gz", imdb_file_format),
                ("MOVIE_DB.RAW.IMDB_TITLE_AKAS", "title.akas.tsv.gz", imdb_file_format),
                ("MOVIE_DB.RAW.IMDB_TITLE_BASICS", "title.basics.tsv.gz", imdb_file_format),
                ("MOVIE_DB.RAW.IMDB_TITLE_CREW", "title.crew.tsv.gz", imdb_file_format),
                ("MOVIE_DB.RAW.IMDB_TITLE_PRINCIPALS", "title.principals.tsv.gz", imdb_file_format),
                ("MOVIE_DB.RAW.IMDB_TITLE_RATINGS", "title.ratings.tsv.gz", imdb_file_format),
            ],
            stage=IMDB_SNOWFLAKE_STAGE,
        )

    @task
    def load_tmdb_raw() -> None:
        tmdb_file_format = os.environ.get(
            "TMDB_SNOWFLAKE_FILE_FORMAT",
            "MOVIE_DB.RAW.TMDB_CSV_FORMAT",
        )
        refresh_raw_tables(
            [
                ("MOVIE_DB.RAW.TMDB_DETAILS", "tmdb_details.csv", tmdb_file_format),
                ("MOVIE_DB.RAW.TMDB_GENRES", "tmdb_genres.csv", tmdb_file_format),
                ("MOVIE_DB.RAW.TMDB_NOW_PLAYING", "tmdb_now_playing.csv", tmdb_file_format),
            ],
            stage=TMDB_SNOWFLAKE_STAGE,
        )

    @task.bash(env=DBT_ENV, append_env=True, output_processor=dbt_success_receipt)
    def dbt_build() -> str:
        return (
            f"/opt/dbt_venv/bin/dbt build --full-refresh "
            f"--project-dir {DBT_PROJECT_DIR} "
            f"--profiles-dir {DBT_PROFILES_DIR} "
            "--target dev"
        )

    @task(execution_timeout=timedelta(minutes=10))
    def export_dashboard_bundle(dbt_receipt: dict) -> dict:
        from publish_dashboard import export_and_publish

        context = get_current_context()
        connection = dashboard_snowflake_connection()
        try:
            return export_and_publish(connection, context['dag'].dag_id, context['run_id'], dbt_receipt)
        finally:
            connection.close()

    @task
    def dispatch_dashboard_pages(publication: dict) -> dict:
        from publish_dashboard import dispatch_from_environment

        return dispatch_from_environment(publication)

    imdb_upload = extract_and_upload_imdb()
    imdb_raw = load_imdb_raw()

    tmdb_genres = extract_tmdb_genres()
    tmdb_now_playing = extract_tmdb_now_playing()
    tmdb_details = enrich_tmdb_movies()
    tmdb_upload = upload_tmdb_files()
    tmdb_raw = load_tmdb_raw()

    imdb_upload >> imdb_raw
    tmdb_now_playing >> tmdb_details
    [tmdb_genres, tmdb_details] >> tmdb_upload >> tmdb_raw
    build = dbt_build()
    publication = export_dashboard_bundle(build)
    [imdb_raw, tmdb_raw] >> build >> publication
    dispatch_dashboard_pages(publication)


movie_analytics_pipeline()
