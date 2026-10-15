"""Regression coverage for side-quest drift and bounded mainline recovery."""
import contextlib
import copy
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import configuration
import research
import research_focus
import route_budget
import runner
import runner_core

SOURCE = Path(__file__).resolve().parents[1]
TASK = 'Construct one finite-field authorization step with explicit leakage and a full state transition.'


class ResearchFocusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for directory in ('config', 'method', 'profiles', 'prompts'):
            shutil.copytree(SOURCE / directory, self.root / directory)
        self.project = self.root / 'projects/example'
        self.write('PROJECT.json', {'id': 'example', 'checks': []})
        self.write('GOAL.md', '# Frozen goal\nExact finite-field aggregation with private weights and malicious security.')
        self.write('AGENTS.md', '# Project rules\nPreserve the frozen goal.')
        self.write('RESEARCH_PROFILE.json', {'profiles': [], 'read_order': []})
        self.write('ideas/INDEX.json', {'ideas': [{'id': 'IDEA-0001', 'version': 1,
            'revisions': [{'version': 1, 'file': 'ideas/IDEA-0001/v001.md'}]}]})
        self.write('ideas/IDEA-0001/v001.md', '# User idea\nPrivate authorization for exact aggregation.')
        self.write('literature/queries.json', {'queries': []})
        self.write('research/STATE.json', {'phase': 'FALSIFICATION', 'decision': 'CONTINUE',
            'research_route': 'C/PIWA', 'priority_problem': 'A geometric lemma from a neighboring paper.',
            'next_task': 'Obtain independent review of the unused geometric lemma before any other work.',
            'last_run': None, 'selected_idea': {'id': 'IDEA-0001', 'version': 1},
            'verified_results': ['preexisting result'], 'open_obligations': ['side-lemma-review'],
            'publication_status': 'NOT_ESTABLISHED'})
        self.write('research/REVIEW.md', 'OPEN: external review of side lemma is still pending.')
        self.write('proofs/side.md', 'Existing side lemma; no current use in the core construction.')
        for module, name, value in ((configuration, 'ROOT', self.root), (research, 'ROOT', self.root),
            (runner, 'HERE', self.root), (runner_core, 'ROOT', self.root),
            (runner_core, 'METHOD', self.root / 'method')):
            patcher = mock.patch.object(module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.policy, _, _ = route_budget.policy_for(self.root, self.project)
        self.path, self.ledger, self.epoch = route_budget.load_ledger(self.root, self.project, self.state())

    def write(self, path, value):
        target = self.project / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value, encoding='utf-8')

    def read(self, path):
        return json.loads((self.project / path).read_text(encoding='utf-8'))

    def state(self):
        return self.read('research/STATE.json')

    def impact(self, scope='CORE'):
        return {'anchor_id': self.epoch['focus']['anchor_id'], 'scope': scope,
            'target_obligation': 'Exact authorized finite-field output with bounded leakage',
            'before': 'The proposed authorization interface may reveal a historical weight.',
            'after': 'A reachable witness excludes that interface under the fixed leakage.',
            'next_mainline_task': TASK}

    def record(self, rid, *, status='REFUTED', kind='COUNTEREXAMPLE', scope='CORE', impact=True):
        before = route_budget.evidence_snapshot(self.project)
        state = self.state()
        state['last_run'] = rid
        self.write('research/STATE.json', state)
        self.write('proofs/current.md', 'Explicit assumptions and reachable finite-field witness ' + rid)
        receipt = {'schema_version': 1, 'run_id': rid, 'work_kind': kind, 'result_status': status,
            'core_problem': 'Private aggregation', 'theoretical_obligation': 'Output leakage boundary',
            'nontriviality_argument': 'The prior interface omits malicious scheduling.',
            'contribution_type': 'NONE', 'evidence_paths': ['proofs/current.md']}
        if impact:
            receipt['goal_impact'] = self.impact(scope)
        self.write('research/ROUND_REVIEW.json', receipt)
        self.write('research/ROUTE_SIGNAL.json', {'run_id': rid, 'progress_type': 'COUNTEREXAMPLE',
            'reason': 'An explicit reachable witness has been saved under the original assumptions.',
            'evidence_paths': ['proofs/current.md'], 'route_blocked': False})
        return runner.record_round(self.project, self.ledger, self.epoch, self.policy, state, before)

    def verdict(self, outcome='REFOCUS', *, scope='CORE', decision='CONTINUE'):
        state = self.state()
        state.update(last_run='review-1', decision=decision)
        self.write('research/STATE.json', state)
        self.write('research/ROUTE_VERDICT.json', {'run_id': 'review-1', 'outcome': outcome,
            'reason': 'The side lemma is not currently required; return to the fixed core interface.',
            'evidence_paths': ['proofs/side.md'], 'requires_goal_change': False,
            'next_task': TASK, 'next_goal_impact': self.impact(scope), 'candidates': []})
        return runner.apply_review(self.project, self.ledger, self.epoch, self.policy, state)

    def cli(self, extra=()):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream), \
                mock.patch.object(runner_core, 'codex_run') as model:
            result = research.main(['refocus', 'example', '--task', TASK,
                '--reason', 'Return from the unused geometric side lemma to the fixed core problem.', *extra])
        model.assert_not_called()
        return result, stream.getvalue()

    def test_migration_pins_goal_instead_of_already_drifted_priority(self):
        focus = copy.deepcopy(self.epoch['focus'])
        self.assertIn('Exact finite-field', focus['core_problem'])
        self.assertNotIn('geometric', focus['core_problem'])
        changed = self.state()
        changed['priority_problem'] = 'Another side quest assigned by the model.'
        self.assertEqual(research_focus.ensure_focus(self.project, self.epoch, changed), focus)
        self.assertEqual(research_focus.require_current(self.project, self.epoch, changed), focus)
        self.assertFalse(self.path.exists(), 'read-only migration must not persist a ledger')

    def test_changed_goal_stops_before_model_call(self):
        self.write('GOAL.md', 'A different research goal selected outside the controller.')
        with mock.patch.object(runner, 'run_child') as child:
            with self.assertRaisesRegex(ValueError, 'RESEARCH_FOCUS_STALE'):
                runner.advance_one(self.project, self.policy, self.path, self.ledger, self.epoch, ['core'])
        child.assert_not_called()

    def test_support_only_proof_and_counterexample_trigger_early_review(self):
        for index, kind in enumerate(('COUNTEREXAMPLE', 'PROOF'), 1):
            self.assertFalse(self.record(str(index), status='SUPPORT_ONLY', kind=kind)[0])
            self.assertEqual(self.epoch['effective_rounds'], index)
            self.assertEqual(self.epoch['stagnation'], index)
        self.assertTrue(self.epoch['review_pending'])
        self.assertEqual(self.epoch['review_reason'], 'support_work_without_theoretical_progress')
        self.assertTrue((self.project / 'proofs/current.md').is_file())

    def test_core_refutation_without_novel_contribution_counts(self):
        self.epoch['stagnation'] = 1
        self.assertTrue(self.record('core-refutation')[0])
        self.assertEqual(self.epoch['stagnation'], 0)
        self.assertEqual(self.read('research/ROUND_REVIEW.json')['contribution_type'], 'NONE')
        self.assertEqual(self.state()['verified_results'], ['preexisting result'])

    def test_legacy_receipt_is_preserved_without_mainline_credit(self):
        self.assertFalse(self.record('legacy', impact=False)[0])
        self.assertEqual(self.epoch['effective_rounds'], 1)
        self.assertEqual(self.epoch['support_rounds'], 1)
        self.assertEqual(self.ledger['events'][-1]['goal_alignment']['scope'], 'UNCLASSIFIED')
        self.assertTrue((self.project / 'proofs/current.md').is_file())

    def test_direct_dependency_requires_explicit_consumer(self):
        impact = self.impact('DIRECT_DEPENDENCY')
        with self.assertRaisesRegex(ValueError, 'consumer_claim'):
            research_focus.validate_impact(impact, self.epoch['focus'])
        impact.update(consumer_claim='C-authorization', dependency_argument='Step 2 of the gate uses this bound.')
        self.assertEqual(research_focus.validate_impact(impact, self.epoch['focus']), impact)

    def test_stale_anchor_and_unchanged_obligation_do_not_count(self):
        receipt = {'goal_impact': self.impact(), 'result_status': 'REFUTED', 'evidence_paths': ['proofs/side.md']}
        receipt['goal_impact']['anchor_id'] = 'stale'
        self.assertFalse(research_focus.assess_progress(self.project, self.epoch, receipt, ['proofs/side.md'])['mainline_progress'])
        receipt['goal_impact'] = self.impact()
        receipt['goal_impact']['after'] = receipt['goal_impact']['before']
        self.assertFalse(research_focus.assess_progress(self.project, self.epoch, receipt, ['proofs/side.md'])['mainline_progress'])

    def test_evidence_must_be_fresh_shared_and_not_renamed_duplicate(self):
        self.assertTrue(self.record('first')[0])
        receipt = self.read('research/ROUND_REVIEW.json')
        self.assertFalse(research_focus.assess_progress(self.project, self.epoch, receipt, ['proofs/unrelated.md'])['mainline_progress'])
        self.write('proofs/renamed.md', (self.project / 'proofs/current.md').read_text(encoding='utf-8-sig'))
        receipt['evidence_paths'] = ['proofs/renamed.md']
        result = research_focus.assess_progress(self.project, self.epoch, receipt, ['proofs/renamed.md'])
        self.assertFalse(result['mainline_progress'])
        self.assertIn('Previously counted', result['reason'])

    def test_route_prompt_does_not_inherit_project_proof_audit(self):
        self.write('prompts/independent_review.md', 'ONLY_AUDIT_THIS_SIDE_LEMMA')
        self.write('prompts/stages/REVIEW.md', 'PROJECT_REVIEW_ONLY_MARKER')
        state = self.state()
        state['next_task'] = route_budget.generate_directive('C/PIWA', self.epoch, self.policy, True, 'stagnation', state['next_task'])
        prompt = runner_core.build_prompt(self.project, state, 'test', 'critical', route_review=True)
        self.assertIn('# ROUTE REVIEW MODE', prompt)
        self.assertIn(self.epoch['focus']['anchor_id'], prompt)
        self.assertNotIn('# AUDIT MODE', prompt)
        self.assertNotIn('ONLY_AUDIT_THIS_SIDE_LEMMA', prompt)
        self.assertNotIn('PROJECT_REVIEW_ONLY_MARKER', prompt)
        audit = runner_core.build_prompt(self.project, state, 'test', 'critical', audit=True)
        self.assertIn('# AUDIT MODE', audit)
        self.assertIn('ONLY_AUDIT_THIS_SIDE_LEMMA', audit)
        with self.assertRaises(ValueError):
            runner_core.build_prompt(self.project, state, 'test', 'critical', audit=True, route_review=True)

    def test_route_refocus_uses_remaining_budget_without_approving_evidence(self):
        self.epoch.update(effective_rounds=2, stagnation=2, support_rounds=2, review_pending=True)
        before = (self.project / 'research/REVIEW.md').read_bytes()
        self.assertEqual(self.verdict(), 'REFOCUSED')
        self.assertEqual(self.epoch['effective_rounds'], 2)
        self.assertEqual(self.epoch['extensions_used'], 0)
        self.assertEqual(self.epoch['support_rounds'], 0)
        self.assertEqual(self.state()['next_task'], TASK)
        self.assertEqual(self.state()['open_obligations'], ['side-lemma-review'])
        self.assertEqual((self.project / 'research/REVIEW.md').read_bytes(), before)

    def test_refocus_cannot_add_automatic_budget(self):
        self.epoch['effective_rounds'] = self.policy['initial_round_budget']
        self.assertEqual(self.verdict(), 'PAUSED_REFOCUS_BUDGET_EXHAUSTED')
        self.assertEqual(self.epoch['extensions_used'], 0)
        self.assertEqual(self.state()['decision'], 'NEEDS_REVIEW')

    def test_support_continuation_cannot_refocus_or_extend(self):
        for outcome in ('REFOCUS', 'EXTEND'):
            with self.subTest(outcome=outcome):
                self.assertEqual(self.verdict(outcome, scope='SUPPORT'), 'PAUSED_INVALID_VERDICT')
                self.assertEqual(self.epoch['extensions_used'], 0)

    def test_model_halt_is_still_honored(self):
        self.assertEqual(self.verdict(decision='NEEDS_REVIEW'), 'PAUSED_NATIVE_REVIEW_HALT')
        self.assertEqual(self.state()['decision'], 'NEEDS_REVIEW')

    def test_operator_refocus_preserves_history_budget_and_pending_review(self):
        state = self.state()
        state.update(decision='NEEDS_REVIEW', phase='REVIEW', last_run='last-review')
        self.write('research/STATE.json', state)
        self.epoch.update(effective_rounds=6, last_processed_run='last-review',
            counted_run_ids=['r1', 'r2', 'r3', 'r4', 'r5', 'r6'], support_rounds=2, stagnation=2)
        route_budget.save_ledger(self.path, self.ledger)
        originals = {name: (self.project / name).read_bytes() for name in ('GOAL.md', 'research/REVIEW.md', 'proofs/side.md')}
        code, output = self.cli(['--extra-rounds', '4'])
        self.assertEqual(code, 0, output)
        recovered = self.state()
        for name in ('last_run', 'selected_idea', 'research_route', 'open_obligations', 'verified_results', 'publication_status'):
            self.assertEqual(recovered[name], state[name])
        self.assertEqual(recovered['decision'], 'CONTINUE')
        self.assertEqual(recovered['next_task'], TASK)
        self.assertIn('Exact finite-field', recovered['priority_problem'])
        _, ledger, epoch = route_budget.load_ledger(self.root, self.project, recovered)
        self.assertEqual(epoch['effective_rounds'], 6)
        self.assertEqual(epoch['counted_run_ids'], self.epoch['counted_run_ids'])
        self.assertEqual(route_budget.total_budget(epoch, self.policy), 10)
        self.assertEqual(epoch['extensions_used'], 0)
        self.assertEqual(ledger['events'][-1]['type'], 'OPERATOR_REFOCUS')
        self.assertTrue(all((self.project / name).read_bytes() == data for name, data in originals.items()))

    def test_operator_refocus_requires_explicit_budget_after_exhaustion(self):
        self.epoch['effective_rounds'] = self.policy['initial_round_budget']
        route_budget.save_ledger(self.path, self.ledger)
        before = (self.project / 'research/STATE.json').read_bytes()
        ledger_before = self.path.read_bytes()
        code, output = self.cli()
        self.assertEqual(code, 2)
        self.assertIn('--extra-rounds', output)
        self.assertEqual((self.project / 'research/STATE.json').read_bytes(), before)
        self.assertEqual(self.path.read_bytes(), ledger_before)

    def test_operator_refocus_keeps_explicit_stop_and_respects_run_lock(self):
        self.write('.control/STOP_REQUESTED', 'stop')
        with research.project_lock(self.project):
            self.assertEqual(self.cli()[0], 2)
        code, output = self.cli()
        self.assertEqual(code, 0, output)
        self.assertIn('clear-stop', output)
        self.assertTrue((self.project / '.control/STOP_REQUESTED').is_file())

    def test_operator_refocus_does_not_discard_fixed_attempt(self):
        with mock.patch('engine.discovery_scheduler.active', return_value={'id': 'fixed-attempt'}):
            code, output = self.cli()
        self.assertEqual(code, 2)
        self.assertIn('attempt close', output)
        self.assertFalse(self.path.exists())

    def test_failed_ledger_write_restores_project(self):
        before = (self.project / 'research/STATE.json').read_bytes()
        with mock.patch.object(route_budget, 'save_ledger', side_effect=OSError('disk unavailable')):
            self.assertEqual(self.cli()[0], 2)
        self.assertEqual((self.project / 'research/STATE.json').read_bytes(), before)
        self.assertFalse((self.project / 'research/DECISION_LOG.md').exists())

    def test_failure_after_ledger_write_restores_both_state_and_budget(self):
        route_budget.save_ledger(self.path, self.ledger)
        before = (self.project / 'research/STATE.json').read_bytes()
        ledger_before = self.path.read_bytes()
        original_save = route_budget.save_ledger
        for failure, code in ((OSError('late write failure'), 2), (KeyboardInterrupt(), 130)):
            with self.subTest(failure=type(failure).__name__):
                def interrupted_save(path, ledger):
                    original_save(path, ledger)
                    raise failure
                with mock.patch.object(route_budget, 'save_ledger', side_effect=interrupted_save):
                    self.assertEqual(self.cli(['--extra-rounds', '4'])[0], code)
                self.assertEqual((self.project / 'research/STATE.json').read_bytes(), before)
                self.assertEqual(self.path.read_bytes(), ledger_before)
                self.assertFalse((self.project / 'research/DECISION_LOG.md').exists())

    def test_revisiting_route_preserves_focus_added_budget_and_fingerprints(self):
        self.epoch.update(effective_rounds=4, operator_added_rounds=3, mainline_fingerprints=['fingerprint'])
        route_budget.save_ledger(self.path, self.ledger)
        other = self.state()
        other['research_route'] = 'B/OTHER'
        path, ledger, _ = route_budget.load_ledger(self.root, self.project, other)
        route_budget.save_ledger(path, ledger)
        _, _, revisited = route_budget.load_ledger(self.root, self.project, self.state())
        for key in ('focus', 'effective_rounds', 'operator_added_rounds', 'mainline_fingerprints'):
            self.assertEqual(revisited[key], self.epoch[key])


if __name__ == '__main__':
    unittest.main()
