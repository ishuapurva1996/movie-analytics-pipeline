"""Publication must preserve the last complete bundle across failures."""
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from publish_dashboard import PublicationError, check_eligibility, publish_bundle, dispatch_dashboard


class MemoryS3:
    def __init__(self):
        self.objects = {}
        self.fail_upload = False

    def etag(self, key):
        return '"' + hashlib.sha256(self.objects[key]).hexdigest() + '"'

    def get_object(self, Bucket, Key):
        from botocore.exceptions import ClientError
        if Key not in self.objects:
            raise ClientError({'Error': {'Code': 'NoSuchKey'}}, 'GetObject')
        return {'Body': io.BytesIO(self.objects[Key]), 'ETag': self.etag(Key)}

    def put_object(self, Bucket, Key, Body, **kwargs):
        from botocore.exceptions import ClientError
        if self.fail_upload:
            raise RuntimeError('private service failure')
        if kwargs.get('IfNoneMatch') == '*' and Key in self.objects:
            raise ClientError({'Error': {'Code': 'PreconditionFailed'}}, 'PutObject')
        if 'IfMatch' in kwargs and (Key not in self.objects or kwargs['IfMatch'] != self.etag(Key)):
            raise ClientError({'Error': {'Code': 'PreconditionFailed'}}, 'PutObject')
        self.objects[Key] = Body
        return {'ETag': self.etag(Key)}


def metadata():
    names = ['extract_and_upload_imdb', 'extract_tmdb_genres', 'extract_tmdb_now_playing',
             'enrich_tmdb_movies', 'upload_tmdb_files', 'load_imdb_raw', 'load_tmdb_raw', 'dbt_build']
    return [dict(dag_id='movie_analytics_pipeline', task_id=name, dag_run_id='current', id=name, map_index=-1, state='success',
                 try_number=1, start_date=f'2026-10-02T{hour:02}:00:00Z',
                 end_date=f'2026-10-02T{hour:02}:10:00Z', dag_version={'id': 'v1'})
            for name, hour in zip(names, [1, 1, 1, 2, 3, 4, 4, 5])]


class MetadataAPI:
    def __init__(self):
        self.dag_id = 'movie_analytics_pipeline'
        self.rows = metadata()
        self.others = []
        self.changed = []
        self.history = []

    def task_instances(self, run_id, **filters):
        if run_id == '~':
            return [r for r in self.rows + self.others if r['task_id'] == filters['task_id']]
        return self.changed if 'updated_at_gt' in filters else self.rows

    def task_tries(self, run_id):
        return self.history + [self.rows[-1]]


def dbt_receipt():
    return dict(schema_version=1, dag_id='movie_analytics_pipeline', run_id='current',
                task_id='dbt_build', task_instance_id='dbt_build', try_number=1,
                started_at='2026-10-02T05:00:00Z', completed_at='2026-10-02T05:09:59Z',
                dag_version_id='v1')


class EligibilityTests(unittest.TestCase):
    def test_complete_current_run_is_eligible(self):
        evidence = check_eligibility(MetadataAPI(), 'current', dbt_receipt())
        self.assertEqual(evidence['warehouse_completed_at'], '2026-10-02T05:10:00Z')

    def test_worker_start_after_supervisor_start_is_eligible_for_same_attempt(self):
        # Airflow's worker and metadata API record separate start timestamps.
        receipt = dbt_receipt()
        receipt['started_at'] = '2026-10-02T05:00:00.012123Z'
        evidence = check_eligibility(MetadataAPI(), 'current', receipt)
        self.assertEqual(evidence['warehouse_completed_at'], '2026-10-02T05:10:00Z')

    def test_receipt_start_outside_successful_attempt_is_denied(self):
        for start in ('2026-10-02T04:59:59.999999Z', '2026-10-02T05:10:00Z'):
            receipt = dbt_receipt()
            receipt['started_at'] = start
            with self.subTest(start=start), self.assertRaisesRegex(PublicationError, 'receipt'):
                check_eligibility(MetadataAPI(), 'current', receipt)

    def test_failed_cleared_or_restarted_predecessor_is_denied(self):
        for state in [None, 'failed', 'running', 'up_for_retry']:
            api = MetadataAPI()
            api.rows[0]['state'] = state
            with self.subTest(state=state), self.assertRaises(PublicationError):
                check_eligibility(api, 'current', dbt_receipt())

    def test_old_run_cannot_export_a_later_warehouse(self):
        api = MetadataAPI()
        later = copy.deepcopy(api.rows[-1])
        later.update(dag_run_id='later', start_date='2026-10-02T06:00:00Z', end_date='2026-10-02T06:10:00Z')
        api.others = [later]
        with self.assertRaises(PublicationError):
            check_eligibility(api, 'current', dbt_receipt())

    def test_marked_or_cleared_upstream_is_denied_even_with_old_dates(self):
        api = MetadataAPI()
        api.changed = [api.rows[0]]
        with self.assertRaises(PublicationError):
            check_eligibility(api, 'current', dbt_receipt())

    def test_new_attempt_invalidates_saved_evidence(self):
        api = MetadataAPI()
        evidence = check_eligibility(api, 'current', dbt_receipt())
        api.rows[-1]['id'] = 'new-attempt'
        with self.assertRaises(PublicationError):
            check_eligibility(api, 'current', dbt_receipt(), expected=evidence)

    def test_cleared_then_marked_success_dbt_is_not_a_completed_build(self):
        api = MetadataAPI()
        api.history = [copy.deepcopy(api.rows[-1])]
        api.rows[-1]['id'] = 'cleared-id'
        with self.assertRaises(PublicationError):
            check_eligibility(api, 'current', dbt_receipt())
        api.rows[-1]['try_number'] = 2
        with self.assertRaises(PublicationError):
            check_eligibility(api, 'current', dbt_receipt())

    def test_reextract_without_reloading_raw_is_denied(self):
        api = MetadataAPI()
        api.rows[0]['start_date'] = '2026-10-02T04:30:00Z'
        api.rows[0]['end_date'] = '2026-10-02T04:40:00Z'
        with self.assertRaises(PublicationError):
            check_eligibility(api, 'current', dbt_receipt())

    def test_failed_or_running_dbt_marked_success_without_receipt_is_denied(self):
        for original_state in ['failed', 'running']:
            api = MetadataAPI()
            dbt = api.rows[-1]
            dbt['state'] = original_state
            # Marking success changes REST state, but never runs the output processor.
            dbt['state'] = 'success'
            api.changed = [dbt]
            with self.subTest(original_state=original_state), self.assertRaisesRegex(PublicationError, 'receipt'):
                check_eligibility(api, 'current', None)

    def test_receipt_must_match_this_run_and_concrete_successful_attempt(self):
        changes = {
            'dag_id': 'another_dag', 'run_id': 'older', 'task_id': 'another_task',
            'task_instance_id': 'cleared-instance', 'try_number': 2,
            'dag_version_id': 'old-version', 'started_at': '2026-10-02T04:00:00Z',
            'completed_at': '2026-10-02T05:11:00Z',
        }
        for key, value in changes.items():
            receipt = dbt_receipt()
            receipt[key] = value
            with self.subTest(field=key), self.assertRaisesRegex(PublicationError, 'receipt'):
                check_eligibility(MetadataAPI(), 'current', receipt)

    def test_old_attempt_receipt_cannot_authorize_later_failed_attempt_marked_success(self):
        api = MetadataAPI()
        receipt = dbt_receipt()
        api.history = [copy.deepcopy(api.rows[-1])]
        api.rows[-1].update(try_number=2, start_date='2026-10-02T05:20:00Z',
                            end_date='2026-10-02T05:30:00Z', state='success')
        with self.assertRaisesRegex(PublicationError, 'receipt'):
            check_eligibility(api, 'current', receipt)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.s3 = MemoryS3()
        self.body = b'{"schema_version":1}'
        self.info = dict(bundle_id='opaque', schema_version=1,
                         warehouse_completed_at='2026-10-02T05:10:00Z', exported_at='2026-10-02T05:12:00Z')

    def publish(self, guard=lambda: None):
        return publish_bundle(self.s3, 'private-bucket', 'dashboard/v1', self.body, self.info, 'current', guard)

    def test_identical_retry_is_safe(self):
        first = self.publish()
        self.assertEqual(self.publish(), first)
        self.assertEqual(len(self.s3.objects), 2)

    def test_upload_failure_does_not_advance_pointer(self):
        self.s3.objects['dashboard/v1/latest-success.json'] = b'previous'
        self.s3.fail_upload = True
        with self.assertRaises(PublicationError):
            self.publish()
        self.assertEqual(self.s3.objects['dashboard/v1/latest-success.json'], b'previous')

    def test_guard_failure_after_upload_does_not_advance_pointer(self):
        before = self.publish()
        self.body = b'{"schema_version":1,"new":true}'
        guard = Mock(side_effect=PublicationError('new mutation'))
        with self.assertRaises(PublicationError):
            self.publish(guard)
        self.assertEqual(json.loads(self.s3.objects['dashboard/v1/latest-success.json']), before)

    def test_conflicting_immutable_object_is_rejected(self):
        pointer = self.publish()
        self.s3.objects[pointer['bundle_key']] = b'conflict'
        with self.assertRaises(PublicationError):
            self.publish()

    def test_older_build_cannot_replace_latest_pointer(self):
        self.publish()
        self.info['warehouse_completed_at'] = '2026-10-01T05:10:00Z'
        with self.assertRaises(PublicationError):
            self.publish()

    def test_competing_publisher_cannot_be_overwritten_after_pointer_read(self):
        original = self.publish()
        newer = {**original, 'bundle_id': 'newer', 'warehouse_completed_at': '2026-10-02T06:10:00Z'}
        key = 'dashboard/v1/latest-success.json'
        newer_bytes = json.dumps(newer, sort_keys=True).encode()

        def advance_pointer():
            # Another publisher wins after this publisher read its old ETag.
            self.s3.put_object(Bucket='private-bucket', Key=key, Body=newer_bytes)

        with self.assertRaises(PublicationError):
            self.publish(guard=advance_pointer)
        self.assertEqual(self.s3.objects[key], newer_bytes)

    def test_competing_first_publisher_keeps_its_pointer(self):
        key = 'dashboard/v1/latest-success.json'
        newer_bytes = json.dumps({**self.info, 'bundle_id': 'newer',
                                  'warehouse_completed_at': '2026-10-02T06:10:00Z'}).encode()
        with self.assertRaises(PublicationError):
            self.publish(guard=lambda: self.s3.put_object(Bucket='private-bucket', Key=key, Body=newer_bytes))
        self.assertEqual(self.s3.objects[key], newer_bytes)

    def test_pointer_timeout_after_server_commit_is_reconciled(self):
        original = self.s3.put_object
        def timeout_after_commit(**kwargs):
            result = original(**kwargs)
            if kwargs['Key'].endswith('latest-success.json'):
                raise TimeoutError('response lost after write')
            return result
        self.s3.put_object = timeout_after_commit
        pointer = self.publish()
        self.assertEqual(json.loads(self.s3.objects['dashboard/v1/latest-success.json']), pointer)

    def test_dispatch_submission_and_failures(self):
        session = Mock()
        session.post.return_value.status_code = 204
        dispatch_dashboard('owner/repo', 'deploy-dashboard.yml', 'private-token', session=session)
        self.assertEqual(session.post.call_args.kwargs['json'], {'ref': 'main'})
        session.post.return_value.status_code = 403
        with self.assertRaises(PublicationError) as error:
            dispatch_dashboard('owner/repo', 'deploy-dashboard.yml', 'private-token', session=session)
        self.assertNotIn('private-token', str(error.exception))


if __name__ == '__main__':
    unittest.main()
