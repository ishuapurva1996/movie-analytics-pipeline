# Local Airflow setup

This project runs Airflow 3.3.2 with PostgreSQL and the local executor in Docker. Dashboard publication configuration is described in [dashboard operations](docs/DASHBOARD_OPERATIONS.md).

## What runs

The `movie_analytics_pipeline` DAG has ten tasks and runs every Monday at **6:00 AM America/Los_Angeles**, following daylight-saving changes. It allows one active run and does not catch up missed schedules:

1. Download IMDb files and upload them to `s3://<bucket>/imdb/`.
2. Fetch TMDB genres and now-playing data.
3. Enrich the now-playing movies with TMDB details.
4. Upload the TMDB CSV files to `s3://<bucket>/tmdb/`.
5. Copy the S3 objects into the existing Snowflake RAW tables.
6. Run `dbt build --full-refresh` to rebuild and test the staging, curated, and analytics models.
7. Verify the completed run's eligibility, validate the dashboard JSON, and publish an immutable private S3 bundle plus its latest-success pointer (`export_dashboard_bundle`).
8. Submit a deployment request to GitHub Actions (`dispatch_dashboard_pages`). This confirms request submission; deployment is verified separately in Actions.

The IMDb, TMDB genre, and TMDB now-playing extraction tasks can run in parallel. dbt starts only after both Snowflake RAW load branches succeed.

The ten task IDs are `extract_and_upload_imdb`, `extract_tmdb_genres`, `extract_tmdb_now_playing`, `enrich_tmdb_movies`, `upload_tmdb_files`, `load_imdb_raw`, `load_tmdb_raw`, `dbt_build`, `export_dashboard_bundle`, and `dispatch_dashboard_pages`.

## 1. Prepare `.env`

Keep the existing `.env` file and add the Airflow and Snowflake settings shown in `.env.example`.

Docker mounts the existing `~/.aws` directory into the Airflow containers as read-only, so boto3 can normally reuse credentials created with `aws configure`. If you do not use that credentials file, set the optional `AWS_*` variables shown in `.env.example`.

The important Snowflake setting is `AIRFLOW_CONN_SNOWFLAKE_CONN`. It defines the Airflow connection named `snowflake_conn`, which is used by both the RAW load tasks and dbt.

Confirm that these four object names match the stages and file formats already created in Snowflake:

```text
IMDB_SNOWFLAKE_STAGE=MOVIE_DB.RAW.IMDB_STAGE
TMDB_SNOWFLAKE_STAGE=MOVIE_DB.RAW.TMDB_STAGE
IMDB_SNOWFLAKE_FILE_FORMAT=MOVIE_DB.RAW.IMDB_TSV_FORMAT
TMDB_SNOWFLAKE_FILE_FORMAT=MOVIE_DB.RAW.TMDB_CSV_FORMAT
```

If your Snowflake objects have different names, update only the values in `.env`.

Fill in the dashboard settings from `.env.example` before a full run. `DASHBOARD_AIRFLOW_USERNAME` and `DASHBOARD_AIRFLOW_PASSWORD` belong to a dedicated metadata reader; `DASHBOARD_GITHUB_TOKEN` is an expiring token scoped to this repository with Actions read/write access. The export fails visibly if its required configuration is missing. See [private Airflow configuration](docs/DASHBOARD_OPERATIONS.md#private-airflow-configuration) for the exact settings and reader permissions.

The supplied Snowflake connection is a placeholder. Use a role with the RAW loading and dbt build privileges needed by this project; do not use `ACCOUNTADMIN` as a routine service role. The export uses the same connection and reads allowlisted analytics columns plus bounded now-playing aggregates.

## 2. Build and initialize Airflow

From the project root, run:

```bash
docker compose build
docker compose up airflow-init
```

The initialization command should finish successfully and exit.

## 3. Start Airflow

```bash
docker compose up -d
```

Open <http://localhost:8080> and sign in. The local defaults are:

```text
username: airflow
password: airflow
```

The Dag is paused when first created. Find `movie_analytics_pipeline`, unpause it, and use the play button for the first manual test.

These login defaults and the Compose JWT fallback are local development settings. Before exposing Airflow remotely, change the login, set private `AIRFLOW_FERNET_KEY` and `AIRFLOW_API_JWT_SECRET` values, and provide HTTPS. The dashboard API reader must not share the administrator login.

For the first complete validation, confirm all ten task instances are successful, then inspect **Deploy dashboard** in GitHub Actions for a successful deployment and public bundle identity check. A successful `dbt_build` alone does not establish that dashboard export or deployment succeeded. The final complete run and public site are still awaiting verification.

## 4. Useful checks

Check that Airflow can see the Snowflake connection in a private terminal; connection output can contain configuration details:

```bash
docker compose run --rm airflow-cli connections get snowflake_conn
```

Check whether Airflow loaded the Dag without import errors:

```bash
docker compose run --rm airflow-cli dags list-import-errors
docker compose run --rm airflow-cli dags list
```

View running containers:

```bash
docker compose ps
```

Follow task and scheduler logs:

```bash
docker compose logs -f airflow-scheduler
```

Stop Airflow without deleting its metadata database:

```bash
docker compose down
```

After changing `.env`, recreate the services so they receive the new values:

```bash
docker compose up -d --force-recreate airflow-apiserver airflow-scheduler airflow-dag-processor
```

Airflow's task history is part of the dashboard eligibility check. Preserve metadata for the current candidate run, its dbt attempts, and any overlapping warehouse writes. [Dashboard operations](docs/DASHBOARD_OPERATIONS.md#metadata-and-bundle-retention) describes retention and safe recovery from a rejected export.

## RAW refresh behavior

All nine RAW tables are fully refreshed, including `TMDB_NOW_PLAYING`. Airflow first loads each file into a temporary Snowflake table. After confirming that the temporary table contains data, it deletes all rows from the target and inserts the new rows in one transaction. An empty load leaves the target unchanged, and an insert failure rolls back that table's replacement.

`TMDB_NOW_PLAYING` contains only the incoming dataset after a successful refresh. `SNAPSHOT_DATE` records when that dataset was captured; earlier snapshots are not retained. Existing historical rows will be removed on the next successful load, so this pipeline does not support comparisons with previous snapshots.

After both RAW load tasks succeed, `dbt build --full-refresh` rebuilds the curated and analytics tables and recreates the staging views from the refreshed sources.

## TMDB enrichment failures

Each movie-details request uses a 30-second timeout. Timeouts, connection failures, and HTTP 429, 500, 502, 503, or 504 responses are retried up to three attempts total, waiting one second and then two seconds between attempts. Other HTTP errors fail immediately.

The details CSV is written only after every distinct movie ID has been fetched successfully. If a request still fails, enrichment raises an error and leaves any existing details CSV unchanged. Airflow retries the failed task once after five minutes; TMDB upload, TMDB RAW loading, and dbt cannot proceed until enrichment succeeds. The independent IMDb branch may still run.
