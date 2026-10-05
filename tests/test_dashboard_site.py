import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_dashboard_site import SiteError, decode_bundle, build_site, read_latest
import build_dashboard_site as site


class SiteTests(unittest.TestCase):
    def setUp(self):
        self.bundle = json.loads((ROOT / 'tests/fixtures/dashboard/synthetic-dashboard.json').read_text())
        self.body = json.dumps(self.bundle).encode()
        self.digest = hashlib.sha256(self.body).hexdigest()

    def test_checksum_is_verified_before_json(self):
        with self.assertRaisesRegex(SiteError, 'checksum'):
            decode_bundle(b'not json', '0' * 64)

    def test_unknown_schema_and_synthetic_production_data_fail(self):
        with self.assertRaises(SiteError):
            decode_bundle(self.body, self.digest)
        self.bundle['schema_version'] = 2
        body = json.dumps(self.bundle).encode()
        with self.assertRaises(SiteError):
            decode_bundle(body, hashlib.sha256(body).hexdigest(), allow_synthetic=True)

    def test_missing_first_pointer_is_actionable(self):
        from botocore.exceptions import ClientError
        class S3:
            def get_object(self, **kwargs):
                raise ClientError({'Error': {'Code': 'NoSuchKey'}}, 'GetObject')
        with self.assertRaisesRegex(SiteError, 'complete Airflow'):
            read_latest(S3(), 'private', 'dashboard/v1')

    def test_artifact_allowlist_and_failure_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / 'source', root / '_site'
            for name in site.ASSETS:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('public asset')
            (source / 'index.html').write_text('original comparison dashboard')
            (source / 'redesign.html').write_text('approved movie dashboard')
            (source / '.env').write_text('secret')
            build_site(source, output, self.body, self.digest, allow_synthetic=True)
            self.assertFalse((output / '.env').exists())
            self.assertEqual((output / 'index.html').read_text(), 'approved movie dashboard')
            self.assertEqual((output / 'redesign.html').read_text(), 'approved movie dashboard')
            self.assertFalse((output / 'js/dashboard.js').exists())
            for name in ('css/dashboard-redesign.css', 'js/dashboard-redesign.js', 'js/dashboard-theme.js'):
                self.assertTrue((output / name).is_file())
            self.assertEqual((output / 'data/dashboard.json').read_bytes(), self.body)
            before = (output / 'data/dashboard.json').read_bytes()
            with self.assertRaises(SiteError):
                build_site(source, output, b'bad', self.digest, allow_synthetic=True)
            self.assertEqual((output / 'data/dashboard.json').read_bytes(), before)

    def test_symlink_asset_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            source.mkdir()
            private = root / 'private'
            private.write_text('secret')
            (source / 'redesign.html').symlink_to(private)
            with self.assertRaises(SiteError):
                build_site(source, root / '_site', self.body, self.digest, allow_synthetic=True)


class MemoryS3:
    """Private-object test double that can advance the latest pointer between reads."""

    prefix = 'dashboard/test'

    def __init__(self, bundles):
        self.objects = {}
        self.pointers = []
        self.reads = []
        for bundle in bundles:
            body = json.dumps(bundle).encode()
            digest = hashlib.sha256(body).hexdigest()
            key = f'{self.prefix}/bundles/{digest}.json'
            self.objects[key] = body
            pointer = {name: bundle['metadata'][name] for name in (
                'bundle_id', 'warehouse_completed_at', 'exported_at')}
            pointer.update(schema_version=1, bundle_key=key, sha256=digest,
                           run_id='synthetic-test-run')
            self.pointers.append(json.dumps(pointer).encode())
        self.pointer_sequence = [self.pointers[0]]

    def get_object(self, *, Bucket, Key):
        self.reads.append(Key)
        if Key == self.prefix + '/latest-success.json':
            body = self.pointer_sequence[0]
            if len(self.pointer_sequence) > 1:
                self.pointer_sequence.pop(0)
        else:
            body = self.objects[Key]
        return {'Body': io.BytesIO(body)}


class AssemblyTests(unittest.TestCase):
    commit = 'a' * 40
    next_commit = 'b' * 40

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / '_site'
        self.state = self.root / 'selection.json'
        self.github_output = self.root / 'github-output'
        for name in site.ASSETS:
            asset = self.root / 'web_dashboard' / name
            asset.parent.mkdir(parents=True, exist_ok=True)
            asset.write_text('synthetic frontend test asset')
        fixture = json.loads((ROOT / 'tests/fixtures/dashboard/synthetic-dashboard.json').read_text())
        next_fixture = copy.deepcopy(fixture)
        next_fixture['metadata']['bundle_id'] = 'synthetic-next-fixture-not-production'
        next_fixture['metadata']['exported_at'] = '2026-10-01T18:06:00Z'
        self.s3 = MemoryS3([fixture, next_fixture])
        self.enterContext(patch.object(site, 'ROOT', self.root))
        self.enterContext(patch.object(site, '_cloud_context', return_value=(
            self.s3, 'synthetic-private-bucket', self.s3.prefix)))
        self.checkout = self.enterContext(patch.object(site, '_checkout_current_main', return_value=self.commit))
        self.main_commit = self.enterContext(patch.object(site, '_main_commit', return_value=self.commit))
        self.enterContext(patch.dict(os.environ, {
            'GITHUB_OUTPUT': str(self.github_output),
            'GITHUB_STEP_SUMMARY': '',
            'GITHUB_SHA': 'c' * 40,  # The old event SHA must not select the source.
        }))
        # Keep fixtures explicitly synthetic. Only this test seam permits them;
        # checksum, schema, pointer matching, and actual asset assembly still run.
        self.enterContext(patch.object(site, 'decode_bundle', side_effect=lambda body, checksum, **kwargs:
            decode_bundle(body, checksum, allow_synthetic=True)))

    def test_assembly_selects_current_main_and_latest_bundle_not_event_sha(self):
        self.s3.pointer_sequence = [self.s3.pointers[1]]
        site.assemble(self.output, self.state)
        selection = json.loads(self.state.read_text())
        pointer = json.loads(self.s3.pointers[1])
        self.assertEqual(selection, {
            'commit': self.commit,
            'pointer_sha256': hashlib.sha256(self.s3.pointers[1]).hexdigest(),
            'bundle_id': pointer['bundle_id'],
            'sha256': pointer['sha256'],
        })
        self.assertNotEqual(selection['commit'], os.environ['GITHUB_SHA'])
        self.assertEqual((self.output / 'data/dashboard.json').read_bytes(),
                         self.s3.objects[pointer['bundle_key']])

    def test_pointer_advance_during_assembly_rebuilds_the_complete_artifact(self):
        self.s3.pointer_sequence = [self.s3.pointers[0], self.s3.pointers[1]]
        with patch.object(site, 'build_site', wraps=site.build_site) as build:
            site.assemble(self.output, self.state)
        self.assertEqual(build.call_count, 2)
        selected = json.loads(self.state.read_text())
        latest = json.loads(self.s3.pointers[1])
        self.assertEqual(selected['sha256'], latest['sha256'])
        self.assertEqual((self.output / 'data/dashboard.json').read_bytes(),
                         self.s3.objects[latest['bundle_key']])
        self.assertTrue((self.output / '.nojekyll').is_file())
        self.assertTrue(all((self.output / name).is_file() for name in site.ASSETS))

    def test_main_advance_during_assembly_reloads_before_recording_a_selection(self):
        class ReloadCurrentMain(Exception):
            pass
        self.main_commit.return_value = self.next_commit
        self.checkout.side_effect = [self.commit, ReloadCurrentMain()]
        with self.assertRaises(ReloadCurrentMain):
            site.assemble(self.output, self.state)
        self.assertEqual(self.checkout.call_count, 2)
        self.assertFalse(self.state.exists())

    def test_recheck_after_upload_rejects_either_changed_input(self):
        site.assemble(self.output, self.state)
        original_selection = self.state.read_bytes()
        original_artifact = (self.output / 'data/dashboard.json').read_bytes()
        for changed in ('main', 'pointer', 'neither'):
            with self.subTest(changed=changed):
                self.main_commit.return_value = self.next_commit if changed == 'main' else self.commit
                self.s3.pointer_sequence = [self.s3.pointers[1 if changed == 'pointer' else 0]]
                self.github_output.write_text('')
                self.assertEqual(site.recheck(self.state), changed == 'neither')
                self.assertEqual(self.github_output.read_text(),
                                 f'current={str(changed == "neither").lower()}\n')
                self.assertEqual(self.state.read_bytes(), original_selection)
                self.assertEqual((self.output / 'data/dashboard.json').read_bytes(), original_artifact)

    def test_perpetually_changing_pointer_fails_without_a_deployable_selection(self):
        self.s3.pointer_sequence = self.s3.pointers * 5
        with patch.object(site, 'build_site', wraps=site.build_site) as build:
            with self.assertRaisesRegex(SiteError, 'inputs keep changing'):
                site.assemble(self.output, self.state)
        self.assertEqual(build.call_count, 5)
        self.assertFalse(self.state.exists())

    def test_pointer_metadata_must_match_the_checksummed_bundle(self):
        mismatches = {
            'bundle_id': 'synthetic-other-bundle',
            'warehouse_completed_at': '2026-10-01T17:00:00Z',
            'exported_at': '2026-10-01T18:06:00Z',
        }
        for key, value in mismatches.items():
            with self.subTest(key=key):
                pointer = json.loads(self.s3.pointers[0])
                pointer[key] = value
                self.s3.pointer_sequence = [json.dumps(pointer).encode()]
                with patch.object(site, 'build_site', wraps=site.build_site) as build:
                    with self.assertRaisesRegex(SiteError, 'pointer and validated bundle disagree'):
                        site.assemble(self.output, self.state)
                build.assert_not_called()
                self.assertFalse(self.state.exists())
                self.assertFalse(self.output.exists())


class TrustedMainCheckoutTests(unittest.TestCase):
    def test_old_checkout_fetches_current_main_and_reexecutes_current_builder(self):
        old_commit, current_commit = 'c' * 40, 'a' * 40
        class ProcessReplaced(Exception):
            pass
        with patch.dict(os.environ, {'DASHBOARD_ASSEMBLY_RESTARTS': '0', 'GITHUB_SHA': old_commit}), \
                patch.object(site.subprocess, 'check_output', side_effect=[
                    f'{current_commit}\trefs/heads/main\n', old_commit + '\n']) as read_git, \
                patch.object(site.subprocess, 'run') as run_git, \
                patch.object(site.os, 'execv', side_effect=ProcessReplaced) as restart, \
                patch.object(site.sys, 'argv', ['old-builder.py', '--assemble', '--state', 'selection.json']):
            with self.assertRaises(ProcessReplaced):
                site._checkout_current_main()
            self.assertEqual([args.args[0] for args in read_git.call_args_list], [
                ['git', 'ls-remote', 'origin', 'refs/heads/main'],
                ['git', 'rev-parse', 'HEAD'],
            ])
            self.assertEqual([args.args[0] for args in run_git.call_args_list], [
                ['git', 'fetch', '--no-tags', 'origin', current_commit],
                ['git', 'checkout', '--detach', current_commit],
            ])
            restart.assert_called_once_with(sys.executable, [sys.executable,
                str(ROOT / 'scripts/build_dashboard_site.py'), '--assemble', '--state', 'selection.json'])
            self.assertEqual(os.environ['DASHBOARD_ASSEMBLY_RESTARTS'], '1')

    def test_repeated_main_changes_stop_instead_of_restarting_forever(self):
        with patch.dict(os.environ, {'DASHBOARD_ASSEMBLY_RESTARTS': '5'}), \
                patch.object(site, '_main_commit', return_value='a' * 40), \
                patch.object(site.subprocess, 'check_output', return_value='b' * 40), \
                patch.object(site.subprocess, 'run'), \
                patch.object(site.os, 'execv') as restart:
            with self.assertRaisesRegex(SiteError, 'Main keeps changing'):
                site._checkout_current_main()
            restart.assert_not_called()


if __name__ == '__main__':
    unittest.main()
