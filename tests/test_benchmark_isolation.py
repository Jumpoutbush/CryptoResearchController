"""R16 probes a temporary token boundary, never certifies a research agent."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from evaluation import isolation


class BenchmarkIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='crc-r16-isolation-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'public').mkdir()
        (self.root / 'private').mkdir()
        self.task = self.root / 'public/task.json'
        self.sentinel = self.root / 'private/oracle.json'
        self.task.write_text('{"task":"Synthetic public task; no hidden answer."}', encoding='utf8')
        self.sentinel.write_text('{"answer":"private-sentinel-not-in-probe-output"}', encoding='utf8')

    def assert_no_agent_authority(self, report):
        self.assertEqual(report['benchmark_agent_isolation'], 'NOT_ISOLATED')
        self.assertIs(report['formal_count'], False)
        self.assertIs(report['agent_execution_allowed'], False)
        self.assertIs(report['real_supervision_allowed'], False)
        self.assertIs(report['lean_execution_allowed'], False)

    def test_unsupported_platform_never_uses_paths_as_isolation(self):
        with mock.patch.object(isolation.os, 'name', 'posix'):
            report = isolation.probe_isolation(self.task, self.sentinel)
        self.assertEqual(report['os_probe_status'], 'NOT_ISOLATED')
        self.assertEqual(report['reason'], 'WINDOWS_APPCONTAINER_REQUIRED')
        self.assert_no_agent_authority(report)

    def test_same_input_cannot_be_claimed_public_and_private(self):
        report = isolation.probe_isolation(self.task, self.task)
        self.assertEqual(report['os_probe_status'], 'NOT_ISOLATED')
        self.assert_no_agent_authority(report)

    def test_api_has_no_arbitrary_command_or_caller_certification(self):
        for key, value in [('argv', ['cmd', '/c', 'echo unsafe']), ('verified', True), ('formal_count', True)]:
            with self.subTest(key=key), self.assertRaises(TypeError):
                isolation.probe_isolation(self.task, self.sentinel, **{key: value})

    def test_failed_platform_api_stays_unverified(self):
        with mock.patch.object(isolation.os, 'name', 'nt'), \
             mock.patch.object(isolation, '_input', side_effect=lambda path: (path, path.read_bytes())), \
             mock.patch.object(isolation, '_Windows', side_effect=OSError('Unavailable local API')):
            report = isolation.probe_isolation(self.task, self.sentinel)
        self.assertEqual(report['os_probe_status'], 'NOT_ISOLATED')
        self.assert_no_agent_authority(report)

    def test_missing_private_input_is_not_an_access_denial_proof(self):
        self.sentinel.unlink()
        report = isolation.probe_isolation(self.task, self.sentinel)
        self.assertEqual(report['os_probe_status'], 'NOT_ISOLATED')
        self.assert_no_agent_authority(report)

    @unittest.skipUnless(os.name == 'nt', 'Real Windows AppContainer error-code negative control')
    def test_missing_file_error_cannot_substitute_for_kernel_access_denial(self):
        original = isolation._Windows.read
        def missing_instead_of_denied(api, path):
            observed = original(api, path)
            if not observed['opened'] and observed['winerror'] == 5:
                return {**observed, 'winerror': 2}
            return observed
        with mock.patch.object(isolation._Windows, 'read', missing_instead_of_denied):
            report = isolation.probe_isolation(self.task, self.sentinel)
        self.assertEqual(report['os_probe_status'], 'NOT_ISOLATED')
        self.assert_no_agent_authority(report)
        if report['access_checks']:
            self.assertEqual(report['access_checks']['private_winerror'], 2)
            self.assertTrue(report['cleanup']['reverted_to_self'])
            self.assertTrue(report['cleanup']['profile_deleted'])
            self.assertTrue(report['cleanup']['temporary_lane_removed'])

    @unittest.skipUnless(os.name == 'nt', 'Real Windows token-observation negative controls')
    def test_wrong_token_sid_or_capability_observation_never_certifies(self):
        for changes in ({'is_appcontainer': False}, {'capability_count': 1},
                        {'appcontainer_sid_matches_profile': False}):
            observed = {'is_appcontainer': True, 'capability_count': 0,
                        'appcontainer_sid_matches_profile': True, 'appcontainer_sid': 'not-an-asserted-identity'}
            observed.update(changes)
            with self.subTest(changes=changes), \
                 mock.patch.object(isolation._Windows, 'token_observation', return_value=observed):
                report = isolation.probe_isolation(self.task, self.sentinel)
            self.assertEqual(report['os_probe_status'], 'NOT_ISOLATED')
            self.assert_no_agent_authority(report)
            self.assertTrue(report['cleanup']['process_handles_closed'])
            self.assertTrue(report['cleanup']['profile_deleted'])
            self.assertTrue(report['cleanup']['temporary_lane_removed'])

    @unittest.skipUnless(os.name == 'nt', 'Real Windows AppContainer token probe')
    def test_live_child_token_read_denial_is_exactly_scoped_and_sources_unchanged(self):
        before = {self.task: self.task.read_bytes(), self.sentinel: self.sentinel.read_bytes()}
        report = isolation.probe_isolation(self.task, self.sentinel)
        self.assert_no_agent_authority(report)
        self.assertEqual(report['actor'], 'CONTROLLER_THREAD_IMPERSONATING_LIVE_CHILD_TOKEN')
        self.assertFalse(report['child_performed_file_reads'])
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertNotIn('private-sentinel-not-in-probe-output', json.dumps(report))
        self.assertNotIn(str(self.sentinel), json.dumps(report))
        if report['os_probe_status'] == 'VERIFIED_READ_DENIAL':
            self.assertTrue(report['token']['is_appcontainer'])
            self.assertEqual(report['token']['capability_count'], 0)
            self.assertTrue(report['token']['appcontainer_sid_matches_profile'])
            self.assertTrue(report['access_checks']['public_read_matches'])
            self.assertEqual(report['access_checks']['private_winerror'], 5)
            self.assertFalse(report['access_checks']['private_open_succeeded'])
            self.assertTrue(report['host_control']['private_readable_before'])
            self.assertTrue(report['host_control']['private_readable_after'])
            self.assertTrue(report['cleanup']['reverted_to_self'])
            self.assertTrue(report['cleanup']['process_handles_closed'])
            self.assertTrue(report['cleanup']['profile_deleted'])
            self.assertFalse(report['process']['inherit_handles'])
            self.assertFalse(report['process']['private_path_in_argv_or_environment'])
        else:
            self.assertEqual(report['os_probe_status'], 'NOT_ISOLATED')
            self.assertTrue(report['reason'])
