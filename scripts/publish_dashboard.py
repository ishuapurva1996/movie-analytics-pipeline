"""Private publication handoff. No credentials, raw rows, or API bodies in logs."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import quote, urlsplit

import requests

PREDECESSORS = (
    'extract_and_upload_imdb', 'extract_tmdb_genres', 'extract_tmdb_now_playing',
    'enrich_tmdb_movies', 'upload_tmdb_files', 'load_imdb_raw', 'load_tmdb_raw', 'dbt_build',
)
MUTATORS = ('load_imdb_raw', 'load_tmdb_raw', 'dbt_build')
ACTIVE_STATES = {'running', 'restarting', 'queued', 'scheduled', 'up_for_retry', 'deferred'}
EDGES = (('extract_and_upload_imdb', 'load_imdb_raw'),
         ('extract_tmdb_now_playing', 'enrich_tmdb_movies'),
         ('extract_tmdb_genres', 'upload_tmdb_files'),
         ('enrich_tmdb_movies', 'upload_tmdb_files'), ('upload_tmdb_files', 'load_tmdb_raw'),
         ('load_imdb_raw', 'dbt_build'), ('load_tmdb_raw', 'dbt_build'))


class PublicationError(RuntimeError):
    """Safe owner-facing failure, without service response payloads."""


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        raise PublicationError('Missing or invalid warehouse eligibility timestamp; run the complete DAG.') from None


def required(name):
    value = os.environ.get(name)
    if not value:
        raise PublicationError(f'Missing required dashboard setting: {name}. See DASHBOARD_OPERATIONS.md.')
    return value


class AirflowMetadataAPI:
    """Airflow 3 public REST API; task code never imports the metadata ORM."""
    def __init__(self, base_url, username, password, dag_id, session=None):
        url = urlsplit(base_url)
        if url.username or url.password or url.query or url.fragment:
            raise PublicationError('Airflow API URL must not contain credentials or query parameters.')
        if url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in {'airflow-apiserver', 'localhost', '127.0.0.1'}):
            raise PublicationError('Use HTTPS for a remote Airflow metadata API.')
        self.base_url = base_url.rstrip('/')
        self.dag_id = dag_id
        self.session = session or requests.Session()
        try:
            response = self.session.post(self.base_url + '/auth/token',
                                         json={'username': username, 'password': password}, timeout=(10, 30))
            response.raise_for_status()
            token = response.json()['access_token']
            if not isinstance(token, str) or not token:
                raise ValueError()
            self.session.headers.update({'Authorization': 'Bearer ' + token})
        except Exception:
            raise PublicationError('Airflow metadata authentication failed; check the private API reader credential.') from None

    def task_instances(self, run_id, **filters):
        path = f'/api/v2/dags/{quote(self.dag_id, safe="")}/dagRuns/{quote(run_id, safe="")}/taskInstances'
        rows, total = [], None
        try:
            for offset in range(0, 10000, 100):
                response = self.session.get(self.base_url + path,
                                            params={**filters, 'limit': 100, 'offset': offset}, timeout=(10, 30))
                response.raise_for_status()
                data = response.json()
                batch, count = data['task_instances'], data['total_entries']
                if not isinstance(batch, list) or not isinstance(count, int) or count < 0:
                    raise ValueError()
                if total is not None and count != total:
                    raise ValueError()
                total = count
                rows.extend(batch)
                if len(rows) == total:
                    ids = [row['id'] for row in rows]
                    if len(ids) != len(set(ids)):
                        raise ValueError()
                    return rows
                if not batch or len(rows) > total:
                    raise ValueError()
        except Exception:
            raise PublicationError('Cannot prove export eligibility from Airflow metadata; run the complete DAG.') from None
        raise PublicationError('Airflow metadata scan exceeded its bound; review metadata retention before publishing.')

    def task_tries(self, run_id):
        # This supported endpoint is unpaginated; history rows have no id field.
        path = f'/api/v2/dags/{quote(self.dag_id, safe="")}/dagRuns/{quote(run_id, safe="")}/taskInstances/dbt_build/tries'
        try:
            response = self.session.get(self.base_url + path, params={'map_index': -1}, timeout=(10, 30))
            response.raise_for_status()
            data = response.json()
            rows = data['task_instances']
            if not isinstance(rows, list) or len(rows) != data['total_entries'] or len(rows) > 10000:
                raise ValueError()
            return rows
        except Exception:
            raise PublicationError('Cannot verify completed dbt attempt history; run the complete DAG.') from None


def check_dbt_receipt(receipt, dag_id, run_id, dbt):
    """Mutable Airflow success state alone cannot prove a successful dbt command."""
    keys = {'schema_version', 'dag_id', 'run_id', 'task_id', 'task_instance_id',
            'try_number', 'started_at', 'completed_at', 'dag_version_id'}
    if (not isinstance(receipt, dict) or set(receipt) != keys
            or type(receipt['schema_version']) is not int or receipt['schema_version'] != 1
            or receipt['dag_id'] != dag_id or receipt['run_id'] != run_id
            or receipt['task_id'] != 'dbt_build' or receipt['task_instance_id'] != dbt['id']
            or type(receipt['try_number']) is not int or receipt['try_number'] != dbt['try_number']
            or receipt['dag_version_id'] != dbt['dag_version']['id']
            or timestamp(receipt['started_at']) != timestamp(dbt['start_date'])
            or not timestamp(dbt['start_date']) <= timestamp(receipt['completed_at']) <= timestamp(dbt['end_date'])):
        raise PublicationError('Missing or stale successful dbt completion receipt; run the complete DAG.')


def check_eligibility(api, run_id, dbt_receipt, expected=None):
    """Reject replayed exports and mutations after the selected completed build."""
    try:
        all_rows = api.task_instances(run_id)
        selected = [row for row in all_rows if row['task_id'] in PREDECESSORS]
        rows = {row['task_id']: row for row in selected}
        if len(selected) != len(PREDECESSORS) or set(rows) != set(PREDECESSORS):
            raise ValueError()
        for row in selected:
            if (row['dag_id'] != api.dag_id or row['dag_run_id'] != run_id
                    or row['map_index'] != -1 or row['state'] != 'success'
                    or not row['id'] or row['try_number'] < 1 or not row['dag_version']
                    or timestamp(row['start_date']) > timestamp(row['end_date'])):
                raise ValueError()
        dbt = rows['dbt_build']
        check_dbt_receipt(dbt_receipt, api.dag_id, run_id, dbt)
        if any(timestamp(row['end_date']) > timestamp(dbt['start_date'])
               for name, row in rows.items() if name != 'dbt_build'):
            raise ValueError()
        if any(timestamp(rows[parent]['end_date']) > timestamp(rows[child]['start_date']) for parent, child in EDGES):
            raise ValueError()
        attempts = api.task_tries(run_id)
        numbers = [row['try_number'] for row in attempts]
        if len(numbers) != len(set(numbers)) or not numbers or max(numbers) != dbt['try_number']:
            raise ValueError()
        current = [row for row in attempts if row['try_number'] == dbt['try_number']]
        if len(current) != 1 or any(current[0][key] != dbt[key] for key in ('state', 'start_date', 'end_date', 'dag_version')):
            raise ValueError()
        if any(timestamp(row['end_date']) > timestamp(dbt['start_date']) for row in attempts if row['try_number'] != dbt['try_number']):
            raise ValueError()
        changed = api.task_instances(run_id, updated_at_gt=dbt['start_date'])
        if any(row['task_id'] in PREDECESSORS[:-1] for row in changed):
            raise ValueError()
        boundary = min(timestamp(rows[name]['start_date']) for name in MUTATORS)
        for name in MUTATORS:
            for row in api.task_instances('~', task_id=name):
                if row['dag_run_id'] == run_id:
                    continue
                start, end = row.get('start_date'), row.get('end_date')
                if (row['state'] in ACTIVE_STATES or (start and not end)
                        or (start and timestamp(start) >= boundary)
                        or (end and timestamp(end) > boundary)):
                    raise ValueError()
        fingerprint = hashlib.sha256(json.dumps([
            {key: rows[name][key] for key in ('id', 'state', 'try_number', 'start_date', 'end_date', 'dag_version')}
            for name in PREDECESSORS
        ], sort_keys=True).encode()).hexdigest()
        result = {'fingerprint': fingerprint, 'warehouse_completed_at': timestamp(dbt['end_date']).isoformat().replace('+00:00', 'Z')}
        if expected is not None and expected != result:
            raise ValueError()
        return result
    except PublicationError:
        raise
    except Exception:
        raise PublicationError('Export is not eligible: upstream tasks changed or another run touched the warehouse. Run the complete DAG.') from None


def dashboard_prefix(value):
    if not re.fullmatch(r'dashboard/[A-Za-z0-9/_-]+', value) or '..' in value or value.endswith('/'):
        raise PublicationError('DASHBOARD_S3_PREFIX must be a dedicated dashboard/<name> prefix without a trailing slash.')
    return value


def read_object(s3, bucket, key, limit):
    """Bound reads before parsing; never put the key in a public error."""
    response = s3.get_object(Bucket=bucket, Key=key)
    stream = response['Body']
    try:
        body = stream.read(limit + 1)
    finally:
        stream.close()
    if len(body) > limit:
        raise PublicationError('Private dashboard object exceeds the size limit.')
    return body, response.get('ETag')


def publish_bundle(s3, bucket, prefix, body, info, run_id, guard):
    """Upload immutable bytes first, then conditionally replace one private pointer."""
    prefix = dashboard_prefix(prefix)
    digest = hashlib.sha256(body).hexdigest()
    key = f'{prefix}/bundles/{digest}.json'
    pointer = {name: info[name] for name in ('schema_version', 'bundle_id', 'warehouse_completed_at', 'exported_at')}
    pointer.update(bundle_key=key, sha256=digest, run_id=run_id)
    pointer_key = prefix + '/latest-success.json'
    try:
        try:
            s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType='application/json', IfNoneMatch='*')
        except Exception as exc:
            if getattr(exc, 'response', {}).get('Error', {}).get('Code') not in {'PreconditionFailed', '412'}:
                raise
        uploaded, _ = read_object(s3, bucket, key, 2 * 1024 * 1024)
        if uploaded != body:
            raise PublicationError('Immutable dashboard object does not match validated bytes.')
        try:
            old_body, etag = read_object(s3, bucket, pointer_key, 8192)
            old = json.loads(old_body)
            if timestamp(old['warehouse_completed_at']) > timestamp(pointer['warehouse_completed_at']):
                raise PublicationError('A newer successful warehouse build is already published.')
            condition = {'IfMatch': etag}
            if not etag:
                raise PublicationError('Cannot conditionally update the dashboard pointer.')
        except Exception as exc:
            if getattr(exc, 'response', {}).get('Error', {}).get('Code') not in {'NoSuchKey', '404'}:
                raise
            condition = {'IfNoneMatch': '*'}
        guard()
        pointer_bytes = json.dumps(pointer, sort_keys=True).encode()
        try:
            s3.put_object(Bucket=bucket, Key=pointer_key, Body=pointer_bytes,
                          ContentType='application/json', **condition)
        except Exception:
            # A lost response does not prove that S3 rejected the atomic write.
            try:
                observed, _ = read_object(s3, bucket, pointer_key, 8192)
                if observed != pointer_bytes:
                    raise ValueError()
            except Exception:
                raise PublicationError('Dashboard pointer update outcome is unconfirmed. Inspect the latest-success pointer and retry safely.') from None
        return pointer
    except PublicationError:
        raise
    except Exception:
        raise PublicationError('Private dashboard upload failed before pointer publication. Retry the export task.') from None


def dispatch_dashboard(repository, workflow, token, session=None):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository) or not re.fullmatch(r'[A-Za-z0-9_.-]+\.ya?ml', workflow):
        raise PublicationError('Invalid dashboard GitHub repository or workflow setting.')
    if not token:
        raise PublicationError('Missing repository-scoped dashboard dispatch credential.')
    try:
        response = (session or requests).post(
            f'https://api.github.com/repos/{repository}/actions/workflows/{workflow}/dispatches',
            headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28'}, json={'ref': 'main'}, timeout=(10, 30))
        status = response.status_code
    except Exception:
        raise PublicationError('Dashboard dispatch timed out or failed to connect; Airflow may retry safely.') from None
    if status != 204:
        raise PublicationError(f'Dashboard dispatch was rejected (HTTP {status}); check token expiry, Actions permission, and main workflow.')


def export_and_publish(connection, dag_id, run_id, dbt_receipt):
    import boto3
    from export_dashboard import extract_bundle, write_bundle
    api = AirflowMetadataAPI(required('DASHBOARD_AIRFLOW_API_URL'), required('DASHBOARD_AIRFLOW_USERNAME'),
                             required('DASHBOARD_AIRFLOW_PASSWORD'), dag_id)
    bucket = required('S3_BUCKET_NAME')
    prefix = dashboard_prefix(required('DASHBOARD_S3_PREFIX'))
    # Fail configuration before querying the warehouse, including dispatch setup.
    required('DASHBOARD_GITHUB_TOKEN')
    required('DASHBOARD_GITHUB_REPOSITORY')
    evidence = check_eligibility(api, run_id, dbt_receipt)
    guard = lambda: check_eligibility(api, run_id, dbt_receipt, expected=evidence)
    schema_path = os.environ.get('DASHBOARD_SCHEMA_PATH', '/opt/airflow/project/web_dashboard/data-contract.schema.json')
    bundle = extract_bundle(connection, evidence['warehouse_completed_at'], schema_path=schema_path)
    guard()
    with tempfile.TemporaryDirectory(prefix='movie-dashboard-') as directory:
        target = Path(directory) / 'dashboard.json'
        info = write_bundle(bundle, target, schema_path=schema_path)
        pointer = publish_bundle(boto3.client('s3'), bucket, prefix, target.read_bytes(), info, run_id, guard)
    # Small private XCom only: the bundle never passes through the metadata DB.
    return {'bundle_id': pointer['bundle_id'], 'sha256': pointer['sha256']}


def dispatch_from_environment(publication):
    if not publication or not publication.get('bundle_id') or not publication.get('sha256'):
        raise PublicationError('A completed private export is required before dispatch.')
    dispatch_dashboard(required('DASHBOARD_GITHUB_REPOSITORY'),
                       os.environ.get('DASHBOARD_GITHUB_WORKFLOW', 'deploy-dashboard.yml'),
                       required('DASHBOARD_GITHUB_TOKEN'))
    return {'bundle_id': publication['bundle_id'], 'submitted': True}
