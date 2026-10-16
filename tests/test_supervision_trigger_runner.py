"""R02 real wrapper boundary and frontends, with an offline research child."""
import contextlib
import io
import unittest
from unittest import mock

import configuration
import research
import route_budget
import runner
import supervision
import supervision_scheduler as scheduler
import test_supervision_runner as fixture


class SupervisionTriggerRunnerTests(unittest.TestCase):
    def setUp(self):
        fixture.SupervisionRunnerTests.setUp(self)
        self.patch_research = mock.patch.object(research, 'ROOT', self.root)
        self.patch_research.start(); self.addCleanup(self.patch_research.stop)
        for filename in ('supervision_defaults.json', 'supervision_policy.json'):
            path = self.root / 'config' / filename
            value = configuration.load_json(path); value['enabled'] = True
            configuration.atomic_json(path, value)
        for rid in ('r1', 'r2'): self.complete(rid)
        self.epoch.update(effective_rounds=2, counted_run_ids=['r1', 'r2'], last_processed_run='r2')
        self.ledger['events'] = [{'type': 'RESEARCH_ROUND', 'run_id': rid} for rid in ('r1', 'r2')]
        route_budget.save_ledger(self.path, self.ledger)
        fixture.put(self.project / 'proofs/new.md', 'Previously accepted evidence, before the new round.')
        self.calls = []
        self.no_models = mock.patch.object(supervision, '_execute', side_effect=AssertionError('No model calls'))
        self.no_models.start(); self.addCleanup(self.no_models.stop)

    current = fixture.SupervisionRunnerTests.current
    impact = fixture.SupervisionRunnerTests.impact
    complete = fixture.SupervisionRunnerTests.complete
    advance = fixture.SupervisionRunnerTests.advance

    def child(self, command):
        self.calls.append(command)
        rid = 'review-r3' if '--route-review' in command else 'r3'
        self.complete(rid)
        fixture.put(self.project / 'proofs/new.md', 'New independently checkable evidence for ' + rid)
        if '--route-review' in command:
            task = 'Prove the exact quantified subclaim with an independently testable certificate.'
            fixture.put(self.project / 'research/ROUTE_VERDICT.json', {
                'run_id': rid, 'outcome': 'EXTEND',
                'reason': 'A concrete subclaim preserves the frozen target and has exact supporting evidence.',
                'evidence_paths': ['proofs/new.md'], 'requires_goal_change': False,
                'next_task': task, 'next_goal_impact': self.impact(task)})
        return 0

    def invoke_frontend(self, argv):
        with mock.patch.object(research, 'run_child', side_effect=lambda cmd: runner.main(cmd[2:])), \
             mock.patch.object(runner, 'run_child', side_effect=self.child), \
             contextlib.redirect_stdout(io.StringIO()):
            return research.main(argv)

    def assert_one(self):
        data = scheduler.pending(self.root, self.project)
        self.assertEqual(len(data['events']), 1)
        self.assertEqual(data['events'][0]['trigger_run_id'], 'r3')
        self.assertEqual(data['attempts_used'], 0)
        self.assertEqual(route_budget.read_json(self.path)['epochs'][-1]['effective_rounds'], 3)
        self.assertEqual(len(self.calls), 1)

    def test_run_uses_the_accepted_wrapper_event(self):
        self.assertEqual(self.invoke_frontend(['run', 'subject', '--offline', '--no-fetch']), 0)
        self.assert_one()

    def test_watch_uses_the_same_accepted_wrapper_event(self):
        self.assertEqual(self.invoke_frontend(['watch', 'subject', '--max-rounds', '1', '--pause-seconds', '0',
                                               '--offline', '--no-fetch']), 0)
        self.assert_one()

    def test_temporary_route_policy_is_respected_without_changing_persistent_budget(self):
        path = self.root / 'config/route_policy.json'
        policy = configuration.load_json(path); policy['initial_round_budget'] = 3
        configuration.atomic_json(path, policy)
        self.assertEqual(self.invoke_frontend(['run', 'subject', '--route-budget', '6', '--offline', '--no-fetch']), 0)
        self.assert_one()
        self.assertEqual(scheduler.pending(self.root, self.project)['deferred'], [])
        self.assertEqual(configuration.load_json(path)['initial_round_budget'], 3)

    def test_direct_runner_uses_the_same_accepted_wrapper_event(self):
        with mock.patch.object(runner, 'run_child', side_effect=self.child), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(['--project', str(self.project), '--rounds', '1', '--offline', '--no-fetch']), 0)
        self.assert_one()

    def test_derived_index_failure_cannot_freeze_or_consume_a_queue_event(self):
        def fail_index(project, **kwargs):
            self.assertEqual(self.current()['last_run'], 'r3')
            self.assertEqual(len(scheduler.pending(self.root, self.project)['events']), 0)
            return {'status': 'failed', 'error': 'Offline index failure'}
        with mock.patch.object(runner, 'run_child', side_effect=self.child), \
             mock.patch.object(runner, 'refresh_knowledge', side_effect=fail_index):
            self.assertEqual(self.advance(), (3, 'KNOWLEDGE_INDEX_FAILED'))
        self.assertEqual(scheduler.pending(self.root, self.project)['events'], [])
        self.assertTrue(route_budget.read_json(self.root / 'logs/subject/latest-status.json')['wrapper_accepted'])
        self.assertFalse((self.root / 'state/failed_runs').exists())

    def test_queue_failure_preserves_acceptance_and_recovers_before_next_round(self):
        record = scheduler.record_postaccept
        def fail_after_accept(*args, **kwargs):
            if args[4] == 'r3': raise OSError('Offline queue write interruption')
            return record(*args, **kwargs)
        with mock.patch.object(runner, 'run_child', side_effect=self.child), \
             mock.patch.object(scheduler, 'record_postaccept', side_effect=fail_after_accept):
            self.assertEqual(self.advance(), (3, 'SUPERVISION_QUEUE_FAILED'))
        self.assertEqual(self.current()['last_run'], 'r3')
        self.assertEqual(self.epoch['effective_rounds'], 3)
        self.assertTrue(route_budget.read_json(self.root / 'logs/subject/latest-status.json')['wrapper_accepted'])
        self.assertFalse((self.root / 'state/failed_runs').exists())
        self.assertEqual(scheduler.before_run(self.root, self.project, self.ledger, self.epoch)['status'], 'queue_only')
        self.assert_one()

    def test_budget_boundary_defers_then_valid_review_coalesces_without_science_recount(self):
        self.policy['initial_round_budget'] = 3
        policy_path = self.root / 'config/route_policy.json'
        policy = configuration.load_json(policy_path); policy['initial_round_budget'] = 3
        configuration.atomic_json(policy_path, policy)
        with mock.patch.object(runner, 'run_child', side_effect=self.child):
            self.assertEqual(self.advance(), (0, 'COUNTED_RESEARCH_ROUND'))
            pending = scheduler.pending(self.root, self.project)
            self.assertEqual(pending['events'], [])
            self.assertEqual(len(pending['deferred']), 1)
            self.assertEqual(self.advance(), (0, 'EXTENDED'))
        pending = scheduler.pending(self.root, self.project)
        self.assertEqual(len(pending['events']), 1)
        self.assertEqual(pending['deferred'], [])
        self.assertEqual(pending['events'][0]['trigger_type'], 'POST_ROUTE_REVIEW')
        self.assertEqual(pending['events'][0]['trigger_run_id'], 'r3')
        self.assertEqual(pending['events'][0]['context']['review_run_id'], 'review-r3')
        self.assertEqual(self.epoch['effective_rounds'], 3)
        self.assertEqual(self.epoch['extensions_used'], 1)
        self.assertEqual(pending['attempts_used'], 0)


if __name__ == '__main__': unittest.main()
