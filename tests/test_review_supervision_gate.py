"""F01/F05: every legacy live entry fails closed without touching old costs.

The provider and process spies never execute a model. Existing legacy fixtures
are reused only as synthetic input; this suite does not mock the isolation gate.
"""
import contextlib
import io
import unittest
from unittest import mock

import configuration
import research
import route_budget
import runner
import runner_core
import supervision
import supervision_executor as executor
import test_supervision as fixtures


class ReviewSupervisionGateTests(unittest.TestCase):
    setUp = fixtures.SupervisionTests.setUp
    put = fixtures.SupervisionTests.put
    read = fixtures.SupervisionTests.read
    enable = fixtures.SupervisionTests.enable
    rounds = fixtures.SupervisionTests.rounds

    def files(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file() and 'locks' not in p.parts}

    def ready(self):
        self.enable()
        self.rounds(3)

    def assert_blocked(self, result):
        self.assertFalse(result['proceed'], result)
        self.assertEqual(result['reason'], 'BLOCKED_UNVERIFIED_OS_SANDBOX')
        self.assertFalse(result['automatic_retry_allowed'])

    def test_legacy_manual_cadence_and_budget_block_before_any_reservation(self):
        self.ready()
        before = self.files()
        with mock.patch.object(supervision, '_execute') as provider, \
             mock.patch.object(supervision.subprocess, 'Popen') as process:
            for options in ({'force': True}, {}, {'budget_reason': 'budget_exhausted'}):
                with self.subTest(options=options):
                    self.assert_blocked(supervision.maybe_supervise(
                        self.root, self.project, self.ledger, **options))
                    self.assertEqual(before, self.files())
        provider.assert_not_called()
        process.assert_not_called()

    def test_direct_legacy_transport_blocks_before_lookup_or_process(self):
        before = self.files()
        with mock.patch.object(supervision.shutil, 'which') as lookup, \
             mock.patch.object(supervision.subprocess, 'Popen') as process, \
             self.assertRaisesRegex(ValueError, 'BLOCKED_UNVERIFIED_OS_SANDBOX'):
            supervision._execute(self.root, self.project, self.root / 'not-created', 'untrusted', {})
        lookup.assert_not_called()
        process.assert_not_called()
        self.assertEqual(before, self.files())

    def test_direct_legacy_apply_is_retired_before_project_writes(self):
        before = self.files()
        with mock.patch.object(supervision, '_write') as write, \
             self.assertRaisesRegex(ValueError, 'BLOCKED_UNVERIFIED_OS_SANDBOX'):
            supervision._apply(self.root, self.project, {}, {}, {}, None, [])
        write.assert_not_called()
        self.assertEqual(before, self.files())

    def test_missing_old_cost_authority_is_never_automatically_zero_enrolled(self):
        self.enable()
        (supervision._home(self.root, self.project) / 'ledger.json').unlink()
        before = self.files()
        with mock.patch.object(supervision, '_enroll') as enroll, \
             mock.patch.object(supervision, '_execute') as provider:
            result = supervision.maybe_supervise(self.root, self.project, self.ledger, force=True)
        self.assertEqual(result['reason'], 'LEGACY_SUPERVISION_HISTORY_UNAVAILABLE')
        self.assertFalse(result['automatic_retry_allowed'])
        enroll.assert_not_called()
        provider.assert_not_called()
        self.assertEqual(before, self.files())

    def test_certifying_new_backend_cannot_silently_reactivate_old_apply(self):
        with mock.patch.object(executor.CodexSupervisorExecutor, '_require_isolation'), \
             self.assertRaisesRegex(ValueError, 'BLOCKED_LEGACY_SUPERVISION_MIGRATION_REQUIRED'):
            supervision._apply(self.root, self.project, {}, {}, {}, None, [])

    def test_unknown_old_running_outcome_never_retries_or_releases_reservation(self):
        self.ready()
        data = supervision._load(self.root, self.project)
        triggers = supervision._triggers(data, self.ledger, supervision.policy_for(
            self.root, self.project), None, True, self.project)
        rid = 'review-' + supervision._hash(supervision._json_bytes([data['goal_sha256'], triggers]))[:24]
        data['records'][rid] = {'status': 'running', 'attempts': 1, 'triggers': triggers,
                                'started_at': '2026-10-15T00:00:00Z'}
        data.update(attempts_used=4, seconds_used=723.5)
        supervision._save(self.root, self.project, data)
        before = self.files()
        with mock.patch.object(supervision, '_execute') as provider, \
             mock.patch.object(supervision.subprocess, 'Popen') as process:
            for _ in range(2):
                result = supervision.maybe_supervise(self.root, self.project, self.ledger, force=True)
                self.assertEqual(result['reason'], 'UNKNOWN_EXTERNAL_OUTCOME')
                self.assertEqual(result['unknown_review_ids'], [rid])
                self.assertFalse(result['automatic_retry_allowed'])
                self.assertEqual(self.files(), before)
        provider.assert_not_called()
        process.assert_not_called()
        history = supervision.history(self.root, self.project)
        self.assertEqual((history['attempts_used'], history['seconds_used']), (4, 723.5))
        self.assertEqual(history['records'][0]['status'], 'running')
        self.assertEqual(history['unknown_review_ids'], [rid])

    def test_cli_configure_then_legacy_force_run_has_no_paid_fallback(self):
        with mock.patch.object(research, 'ROOT', self.root), \
             mock.patch.object(supervision, '_execute') as provider, \
             mock.patch.object(supervision.subprocess, 'Popen') as process, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(research.main(['supervision', 'configure', 'example', '--enabled', 'on']), 0)
            before = self.files()
            with mock.patch.object(runner_core, 'validate_project', return_value=self.read('research/STATE.json')):
                self.assertEqual(research.main(['supervision', 'run', 'example', '--force']), 2)
            self.assertEqual(before, self.files())
        self.assertIn('BLOCKED_UNVERIFIED_OS_SANDBOX', output.getvalue())
        provider.assert_not_called()
        process.assert_not_called()

    def test_run_and_watch_stop_at_due_legacy_gate_before_core_or_provider(self):
        self.ready()
        for action in ('run', 'watch'):
            with self.subTest(action=action):
                before = self.files()
                def wrapper(command, **kwargs):
                    return runner.main(command[2:])
                with mock.patch.object(research, 'ROOT', self.root), \
                     mock.patch.object(runner, 'HERE', self.root), \
                     mock.patch.object(research, 'run_child', side_effect=wrapper), \
                     mock.patch.object(runner, 'run_child') as core, \
                     mock.patch.object(supervision, '_execute') as provider, \
                     mock.patch.object(supervision.subprocess, 'Popen') as process, \
                     contextlib.redirect_stdout(io.StringIO()) as output:
                    args = [action, 'example', '--offline', '--no-fetch']
                    if action == 'watch': args += ['--max-rounds', '1', '--pause-seconds', '0']
                    self.assertEqual(research.main(args), 3)
                self.assertIn('SUPERVISION_BLOCKED', output.getvalue())
                self.assertEqual(before, self.files())
                core.assert_not_called()
                provider.assert_not_called()
                process.assert_not_called()

    def test_r03_spoofed_preflight_cannot_reserve_before_shared_gate(self):
        import test_supervision_executor as r03_fixture
        case = r03_fixture.SupervisorExecutorTests(methodName='runTest')
        case.setUp()
        self.addCleanup(case.doCleanups)
        event = case.event()
        before = supervision._load(case.root, case.project)
        with mock.patch.object(executor.CodexSupervisorExecutor, 'preflight', return_value={
                'compatible': True, 'isolation_verified': True}), \
             mock.patch.object(executor.scheduler, 'claim_event') as reserve, \
             mock.patch.object(executor, '_run_process') as process:
            result = executor.execute(case.root, case.project, event,
                                      executor=executor.CodexSupervisorExecutor())
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['reason'], 'BLOCKED_UNVERIFIED_OS_SANDBOX')
        self.assertEqual(before, supervision._load(case.root, case.project))
        reserve.assert_not_called()
        process.assert_not_called()


if __name__ == '__main__':
    unittest.main()
