"""R05 official acceptance boundary in disposable projects, no model calls."""
import json
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import configuration
import runner
import runner_core
import route_budget
import supervision
import supervision_executor as executor
import supervision_guide as guide
import supervision_scheduler as scheduler
import supervision_runtime as runtime
import test_runner as fixture


class SupervisionE2ETests(unittest.TestCase):
    current = fixture.RunnerTests.current
    impact = fixture.RunnerTests.impact
    complete = fixture.RunnerTests.complete
    state = staticmethod(fixture.RunnerTests.state)
    tearDown = fixture.RunnerTests.tearDown

    def setUp(self):
        original = tempfile.TemporaryDirectory
        with mock.patch.object(tempfile, 'TemporaryDirectory', side_effect=lambda **kw:
                               original(prefix='crc-r04-fixture-')):
            fixture.RunnerTests.setUp(self)
        fixture.put(self.project / 'prompts/continue.md', 'Original next-round instructions.')
        fixture.put(self.project / 'research/PROOF_OBLIGATIONS.json', {'obligations': [
            {'id': 'O-1', 'statement': 'The unchanged quantified condition.'}]})
        route_budget.set_project_override(self.root, self.project,
            {'initial_round_budget': 30, 'stagnation_rounds': 30})
        guide.register_fixture(self.root, self.project)

    def activate(self, backend='fake'):
        import supervision_runtime as runtime
        return runtime.configure(self.root, self.project, enabled=True, backend=backend)

    def run_rounds(self, count, *, fail_at=None):
        prompts = []
        def child(command):
            state = self.current()
            rid = 'round-' + str(len(list((self.project / 'reports').glob('round-*.md'))) + 1) if (self.project / 'reports').exists() else 'round-1'
            prompts.append(runner_core.build_prompt(self.project, state, rid, 'critical',
                                                   route_review='--route-review' in command))
            self.complete(rid)
            fixture.put(self.project / 'proofs/new.md', 'Distinct candidate evidence for ' + rid)
            fixture.put(self.project / 'reports/LATEST.md', (self.project / f'reports/{rid}.md').read_text(encoding='utf8'))
            if '--route-review' in command:
                task = 'Prove the unchanged quantified condition using the recorded candidate.'
                fixture.put(self.project / 'research/ROUTE_VERDICT.json', {'run_id': rid,
                    'outcome': 'EXTEND', 'requires_goal_change': False,
                    'reason': 'A precise bounded unresolved core obligation preserves all original constraints.',
                    'evidence_paths': ['proofs/new.md'], 'next_task': task, 'next_goal_impact': self.impact(task)})
            return 7 if rid == fail_at else 0
        with mock.patch.object(runner, 'run_child', side_effect=child), mock.patch.object(runner_core, 'git_checkpoint', return_value='OFFLINE'):
            code = runner.main(['--project', str(self.project), '--rounds', str(count), '--no-fetch'])
        return code, prompts

    def test_three_accepted_rounds_one_supervisor_and_actual_fourth_prompt(self):
        self.activate()
        code, prompts = self.run_rounds(4)
        self.assertEqual(code, 0)
        self.assertEqual([p.count('# Controller-generated supervision guide') for p in prompts], [0, 0, 0, 1])
        pending = scheduler.pending(self.root, self.project)
        self.assertEqual(len(pending['events']), 1)
        self.assertEqual(pending['events'][0]['state'], 'APPLIED')
        self.assertEqual(pending['attempts_used'], 1)
        self.assertEqual(route_budget.load_ledger(self.root, self.project, self.current())[2]['effective_rounds'], 4)

    def test_enable_at_three_does_not_backfill_history(self):
        self.assertEqual(self.run_rounds(3)[0], 0)
        self.activate()
        self.assertEqual(self.run_rounds(1)[0], 0)
        self.assertEqual(scheduler.pending(self.root, self.project)['events'], [])

    def test_disable_ignores_even_corrupt_guide_and_preserves_history(self):
        import supervision_runtime as runtime
        self.activate(); self.assertEqual(self.run_rounds(3)[0], 0)
        before = supervision._load(self.root, self.project)
        runtime.configure(self.root, self.project, enabled=False)
        (self.project / guide.ACTIVE).write_text('Operator corruption retained.', encoding='utf8')
        self.assertEqual(self.run_rounds(1)[0], 0)
        self.assertEqual(before, supervision._load(self.root, self.project))
        self.assertEqual((self.project / guide.ACTIVE).read_text(), 'Operator corruption retained.')

    def test_fake_rejected_outside_registered_fixture_before_activation(self):
        import supervision_runtime as runtime
        guide._fixture_path(self.root, self.project).unlink()
        with self.assertRaisesRegex(ValueError, 'FAKE'):
            self.activate()
        self.assertFalse(runtime.settings(self.root, self.project).get('enabled', False))

    def test_failure_round_does_not_queue_or_charge(self):
        self.activate()
        self.assertEqual(self.run_rounds(3, fail_at='round-3')[0], 7)
        self.assertEqual(scheduler.pending(self.root, self.project)['events'], [])
        self.assertEqual(route_budget.load_ledger(self.root, self.project, self.current())[2]['effective_rounds'], 2)

    def test_real_backend_stops_without_reserving_and_preserves_accepted_round(self):
        self.activate('codex')
        self.assertEqual(self.run_rounds(3)[0], 3)
        self.assertEqual(self.current()['last_run'], 'round-3')
        self.assertEqual(scheduler.pending(self.root, self.project)['attempts_used'], 0)
        self.assertFalse((self.project / guide.ACTIVE).exists())

    def pending_three(self):
        self.activate()
        with mock.patch.object(runtime, 'safely', return_value={'status': 'deferred', 'proceed': True}):
            self.assertEqual(self.run_rounds(3)[0], 0)
        return scheduler.pending(self.root, self.project)['events'][0]['event_id']

    def test_sixth_round_review_precedes_single_combined_event(self):
        route_budget.set_project_override(self.root, self.project, {'initial_round_budget': 6})
        self.activate(); self.assertEqual(self.run_rounds(7)[0], 0)
        view = scheduler.pending(self.root, self.project)
        self.assertEqual(len(view['events']), 2); self.assertEqual(view['attempts_used'], 2)
        combined = next(e for e in view['events'] if e['trigger_type'] == 'POST_ROUTE_REVIEW')
        self.assertEqual(combined['trigger_run_id'], 'round-6')
        self.assertEqual(combined['context']['review_run_id'], 'round-7')
        self.assertEqual(combined['context']['trigger_reasons'], ['PERIODIC', 'ROUTE_REVIEW'])
        self.assertEqual(route_budget.load_ledger(self.root, self.project, self.current())[2]['effective_rounds'], 6)

    def test_unknown_external_result_never_redispatches_or_refunds(self):
        event = self.pending_three(); fake = executor.FakeSupervisorExecutor(outcome_known=False)
        before = self.current()
        self.assertFalse(runtime.process(self.root, self.project, executor_override=fake)['proceed'])
        cost = supervision._load(self.root, self.project)
        for _ in range(2): self.assertFalse(runtime.process(self.root, self.project, executor_override=fake)['proceed'])
        self.assertEqual(fake.calls, 1); self.assertEqual(cost, supervision._load(self.root, self.project))
        self.assertEqual(before, self.current())

    def test_reserved_not_dispatched_requires_operator_not_automatic_adoption(self):
        event = self.pending_three(); scheduler.claim_event(self.root, self.project, event)
        fake = executor.FakeSupervisorExecutor()
        self.assertFalse(runtime.process(self.root, self.project, executor_override=fake)['proceed'])
        self.assertEqual(fake.calls, 0); self.assertEqual(scheduler.pending(self.root, self.project)['attempts_used'], 1)

    def test_guide_replacement_crash_recovers_without_second_call_or_science_round(self):
        event = self.pending_three(); original = self.current()
        with mock.patch.object(guide, '_commit_receipt', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): runtime.process(self.root, self.project)
        raw = (self.project / guide.ACTIVE).read_bytes(); costs = supervision._load(self.root, self.project)
        for _ in range(2): self.assertTrue(runtime.process(self.root, self.project)['proceed'])
        self.assertEqual(raw, (self.project / guide.ACTIVE).read_bytes())
        self.assertEqual(costs, supervision._load(self.root, self.project)); self.assertEqual(original, self.current())

    def test_missing_frozen_input_blocks_and_cannot_rebuild_from_live(self):
        event = self.pending_three()
        import supervision_ledger as queue
        queue._event_path(self.root, self.project, event).unlink()
        fake = executor.FakeSupervisorExecutor()
        with self.assertRaises(ValueError): runtime.process(self.root, self.project, executor_override=fake)
        self.assertEqual(fake.calls, 0)

    def test_enable_crash_leaves_disabled_fence_and_never_legacy_executor(self):
        configure = supervision.configure
        def crash(*args, **kwargs):
            configure(*args, **kwargs); raise OSError('Activation interrupted')
        with mock.patch.object(supervision, 'configure', side_effect=crash):
            with self.assertRaises(OSError): self.activate()
        self.assertTrue(runtime.disabled(self.root, self.project))
        with mock.patch.object(supervision, '_execute', side_effect=AssertionError('Legacy paid call')):
            self.assertEqual(self.run_rounds(1)[0], 0)

    def test_stop_done_needs_review_and_fixed_attempt_are_preserved(self):
        self.pending_three(); original = self.current()
        for changes in ({'decision': 'STOP'}, {'decision': 'NEEDS_REVIEW'}, {'phase': 'DONE'}):
            fixture.put(self.project / 'research/STATE.json', {**original, **changes})
            self.assertFalse(runtime.process(self.root, self.project)['proceed'])
            self.assertEqual(self.current(), {**original, **changes})
        fixture.put(self.project / 'research/STATE.json', original)
        fixture.put(self.root / 'state/discovery/subject.json', {'active_attempt': 'unchanged-attempt'})
        self.assertEqual(runtime.process(self.root, self.project)['status'], 'deferred_to_fixed_attempt')
        self.assertFalse((self.project / guide.ACTIVE).exists())

    def test_cli_force_dryrun_and_batch_preview_do_not_write(self):
        import research
        self.pending_three()
        def files(): return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        before = files()
        with mock.patch.object(research, 'ROOT', self.root), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(research.main(['supervise', 'run', 'subject', '--force', '--dry-run']), 0)
            self.assertEqual(research.main(['supervise', 'enable', '--all', '--dry-run']), 0)
        self.assertEqual(before, files())

    def test_route_lock_contention_never_starts_science(self):
        self.activate()
        with route_budget.file_lock(self.root / 'locks/route-subject.lock'), mock.patch.object(runner, 'run_child') as child:
            self.assertEqual(runner.main(['--project', str(self.project)]), 3)
            child.assert_not_called()

    def test_disable_preserves_corrupt_costs_and_queue_then_science_runs(self):
        self.pending_three()
        import supervision_ledger as queue
        ledger_path = supervision._home(self.root, self.project) / 'ledger.json'
        ledger_path.write_bytes(b'broken cost ledger retained')
        journal = queue.home(self.root, self.project) / 'events.jsonl'
        journal.write_bytes(b'broken original queue retained')
        runtime.configure(self.root, self.project, enabled=False)
        self.assertEqual(self.run_rounds(1)[0], 0)
        self.assertEqual(ledger_path.read_bytes(), b'broken cost ledger retained')
        self.assertEqual(journal.read_bytes(), b'broken original queue retained')

    def test_enable_does_not_reenroll_missing_reserved_cost_ledger(self):
        event = self.pending_three(); scheduler.claim_event(self.root, self.project, event)
        runtime.configure(self.root, self.project, enabled=False)
        ledger_path = supervision._home(self.root, self.project) / 'ledger.json'
        ledger_path.unlink()
        with self.assertRaises(ValueError): self.activate()
        self.assertFalse(ledger_path.exists())

    def test_reenable_at_six_does_not_backfill(self):
        self.activate(); self.assertEqual(self.run_rounds(3)[0], 0)
        runtime.configure(self.root, self.project, enabled=False)
        self.assertEqual(self.run_rounds(3)[0], 0)
        self.activate(); self.assertEqual(self.run_rounds(1)[0], 0)
        self.assertEqual(len(scheduler.pending(self.root, self.project)['events']), 1)

    def test_completion_receipt_crash_settles_once_then_applies_without_recall(self):
        self.pending_three(); fake = executor.FakeSupervisorExecutor()
        with mock.patch.object(scheduler, 'finish_claim', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                runtime.process(self.root, self.project, executor_override=fake)
        self.assertTrue(runtime.process(self.root, self.project, executor_override=fake)['proceed'])
        cost = supervision._load(self.root, self.project)
        self.assertTrue(runtime.process(self.root, self.project, executor_override=fake)['proceed'])
        self.assertEqual(fake.calls, 1); self.assertEqual(cost, supervision._load(self.root, self.project))

    def test_lost_activation_metadata_blocks_legacy_fallback_until_explicit_disable(self):
        self.activate()
        (supervision._home(self.root, self.project) / 'automation.json').unlink()
        with mock.patch.object(supervision, '_execute', side_effect=AssertionError('Legacy paid call')):
            self.assertEqual(self.run_rounds(1)[0], 3)
        runtime.configure(self.root, self.project, enabled=False)
        self.assertEqual(self.run_rounds(1)[0], 0)


if __name__ == '__main__': unittest.main()
