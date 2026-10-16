"""Offline supervision hooks preserve accepted research and live instructions."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import configuration
import research_focus
import route_budget
import runner
import runner_core
import supervision


SOURCE = Path(__file__).resolve().parents[1]


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)
                    if isinstance(value, (dict, list)) else value, encoding='utf-8')


class SupervisionRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for folder in ('config', 'method', 'profiles'):
            shutil.copytree(SOURCE / folder, self.root / folder)
        put(self.root / 'runner_core.py', '# offline fixture')
        self.project = self.root / 'projects/subject'
        put(self.project / 'PROJECT.json', {'id': 'subject'})
        put(self.project / 'GOAL.md', '# Frozen goal\nProve one explicit cryptographic property.')
        put(self.project / 'AGENTS.md', '# Local instructions\nPreserve the complete security model.')
        put(self.project / 'prompts/continue.md', 'Find the smallest decisive counterexample.')
        put(self.project / 'RESEARCH_PROFILE.json', {'profiles': [], 'read_order': []})
        put(self.project / 'literature/queries.json', {'queries': []})
        put(self.project / 'proofs/original.md', 'Accepted mathematical evidence.')
        put(self.project / 'research/STATE.json', {
            'phase': 'FALSIFICATION', 'decision': 'CONTINUE', 'research_route': 'C/TEST',
            'priority_problem': 'A precise fixed-target obstruction with independently testable evidence.',
            'next_task': 'Run a decisive counterexample search and preserve its explicit certificate.',
            'last_run': None, 'open_obligations': [], 'verified_results': [],
            'publication_status': 'NOT_ESTABLISHED'})
        for patch in (
            mock.patch.object(runner, 'HERE', self.root),
            mock.patch.object(runner, 'CORE', self.root / 'runner_core.py'),
            mock.patch.object(runner_core, 'ROOT', self.root),
            mock.patch.object(runner_core, 'METHOD', self.root / 'method'),
            mock.patch.object(configuration, 'ROOT', self.root),
            mock.patch.object(runner_core, 'git_checkpoint', return_value='OFFLINE'),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        self.policy, _, _ = route_budget.policy_for(self.root, self.project)
        self.path, self.ledger, self.epoch = route_budget.load_ledger(
            self.root, self.project, self.current())

    def current(self):
        return route_budget.state_read(self.project)

    def impact(self, task):
        return {'anchor_id': research_focus.make_focus(self.project, self.current())['anchor_id'],
                'scope': 'CORE', 'target_obligation': 'The core quantified security condition',
                'before': 'Missing exact invariant', 'after': 'An exact counterexample eliminates a candidate',
                'next_mainline_task': task}

    def complete(self, rid='accepted-1'):
        state = self.current()
        state.update(last_run=rid,
                     next_task='Prove the remaining quantified condition using the recorded evidence.')
        put(self.project / 'research/STATE.json', state)
        put(self.project / f'reports/{rid}.md', f'RUN_ID: {rid}\n' +
            'The bounded investigation recorded exact assumptions and independently testable evidence. ' * 8)
        put(self.project / 'proofs/new.md', 'A precise new mathematical obligation and exact assumptions.')
        put(self.project / 'research/ROUTE_SIGNAL.json', {
            'run_id': rid, 'progress_type': 'PROOF_STEP',
            'reason': 'A precise new proof obligation has been isolated with independently recorded evidence.',
            'evidence_paths': ['proofs/new.md'], 'route_blocked': False})
        put(self.project / 'research/ROUND_REVIEW.json', {
            'schema_version': 1, 'run_id': rid, 'work_kind': 'PROOF',
            'core_problem': 'The fixed-target mathematical obstruction',
            'theoretical_obligation': 'Prove the remaining quantified condition',
            'nontriviality_argument': 'The existing result lacks the required integer constraint',
            'contribution_type': 'NONE', 'result_status': 'OPEN',
            'evidence_paths': ['proofs/new.md'], 'goal_impact': self.impact(state['next_task'])})
        return 0

    def advance(self):
        return runner.advance_one(self.project, self.policy, self.path,
                                  self.ledger, self.epoch, ['offline-core'])

    def test_supervision_sees_only_accepted_rounds_after_acceptance(self):
        seen = []

        def review(controller, project, ledger, *, budget_reason=None):
            seen.append((len([event for event in ledger['events']
                              if event['type'] == 'RESEARCH_ROUND']), budget_reason))
            return {'status': 'not_due', 'proceed': True}

        with mock.patch.object(supervision, 'maybe_supervise', side_effect=review), \
             mock.patch.object(runner, 'run_child', side_effect=lambda command: self.complete()):
            self.assertEqual(self.advance(), (0, 'COUNTED_RESEARCH_ROUND'))
        self.assertEqual(seen, [(0, None), (1, None)])

    def test_pending_failed_supervision_blocks_new_model_call_without_state_edits(self):
        before = {str(p.relative_to(self.project)): p.read_bytes()
                  for p in self.project.rglob('*') if p.is_file()}
        with mock.patch.object(supervision, 'maybe_supervise',
                               return_value={'status': 'failed', 'proceed': False}), \
             mock.patch.object(runner, 'run_child') as child:
            self.assertEqual(self.advance(), (3, 'SUPERVISION_FAILED'))
        child.assert_not_called()
        after = {str(p.relative_to(self.project)): p.read_bytes()
                 for p in self.project.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(self.epoch['effective_rounds'], 0)

    def test_budget_supervision_runs_before_existing_route_review(self):
        self.epoch['effective_rounds'] = self.policy['initial_round_budget']
        # A previously scheduled support/stagnation review must not hide the
        # independent budget trigger when the same round exhausts the budget.
        self.epoch.update(review_pending=True, review_reason='support_work_without_theoretical_progress')
        order = []

        def review(controller, project, ledger, *, budget_reason=None):
            order.append(('supervision', budget_reason))
            return {'status': 'applied', 'proceed': True, 'review_id': 'offline-review'}

        def child(command):
            order.append(('route-review', '--route-review' in command))
            self.complete()
            task = 'Prove the exact quantified subclaim with an independently testable certificate.'
            put(self.project / 'research/ROUTE_VERDICT.json', {
                'run_id': 'accepted-1', 'outcome': 'EXTEND',
                'reason': 'A concrete new subclaim preserves the frozen target and has exact supporting evidence.',
                'evidence_paths': ['proofs/new.md'], 'requires_goal_change': False,
                'next_task': task, 'next_goal_impact': self.impact(task)})
            return 0

        with mock.patch.object(supervision, 'maybe_supervise', side_effect=review), \
             mock.patch.object(runner, 'run_child', side_effect=child):
            self.assertEqual(self.advance(), (0, 'EXTENDED'))
        self.assertEqual(order, [('supervision', 'budget_exhausted'),
                                 ('route-review', True), ('supervision', None)])
        self.assertEqual(self.epoch['effective_rounds'], self.policy['initial_round_budget'])
        self.assertEqual(self.epoch['extensions_used'], 1)

    def test_supervision_failure_preserves_already_accepted_research(self):
        responses = [{'status': 'not_due', 'proceed': True},
                     {'status': 'failed', 'proceed': False, 'error': 'offline failure'}]
        with mock.patch.object(supervision, 'maybe_supervise', side_effect=responses), \
             mock.patch.object(runner, 'run_child', side_effect=lambda command: self.complete()):
            self.assertEqual(self.advance(), (3, 'SUPERVISION_FAILED'))
        self.assertEqual(self.current()['last_run'], 'accepted-1')
        self.assertTrue((self.project / 'proofs/new.md').is_file())
        self.assertEqual(self.epoch['effective_rounds'], 1)
        self.assertEqual(route_budget.read_json(self.path)['epochs'][-1]['effective_rounds'], 1)
        self.assertFalse((self.root / 'state/failed_runs').exists())
        status = route_budget.read_json(self.root / 'logs/subject/latest-status.json')
        self.assertTrue(status['wrapper_accepted'])
        self.assertEqual(status['route_outcome'], 'COUNTED_RESEARCH_ROUND')
        self.assertEqual(status['supervision']['status'], 'failed')

    def test_supervision_setup_exception_keeps_postaccepted_status(self):
        with mock.patch.object(supervision, 'maybe_supervise', side_effect=[
                {'status': 'not_due', 'proceed': True}, RuntimeError('project lock busy')]), \
             mock.patch.object(runner, 'run_child', side_effect=lambda command: self.complete()):
            self.assertEqual(self.advance(), (3, 'SUPERVISION_FAILED'))
        self.assertEqual(self.current()['last_run'], 'accepted-1')
        self.assertEqual(self.epoch['effective_rounds'], 1)
        self.assertTrue((self.project / 'proofs/new.md').is_file())
        status = route_budget.read_json(self.root / 'logs/subject/latest-status.json')
        self.assertTrue(status['wrapper_accepted'])
        self.assertEqual(status['supervision']['error'], 'project lock busy')

    def test_supervision_setup_exception_blocks_preflight(self):
        before = (self.project / 'research/STATE.json').read_bytes()
        with mock.patch.object(supervision, 'maybe_supervise', side_effect=OSError('unreadable journal')), \
             mock.patch.object(runner, 'run_child') as child:
            self.assertEqual(self.advance(), (3, 'SUPERVISION_FAILED'))
        child.assert_not_called()
        self.assertEqual((self.project / 'research/STATE.json').read_bytes(), before)

    def test_rejected_round_never_runs_post_acceptance_supervision(self):
        with mock.patch.object(supervision, 'maybe_supervise',
                               return_value={'status': 'not_due', 'proceed': True}) as reviewed, \
             mock.patch.object(runner, 'run_child', return_value=5):
            self.assertEqual(self.advance(), (5, 'NATIVE_CORE_FAILED exit_code=5'))
        self.assertEqual(reviewed.call_count, 1)
        self.assertEqual(self.epoch['effective_rounds'], 0)
        self.assertIsNone(self.current()['last_run'])

    def test_prompt_reads_latest_guidelines_and_frozen_supervision_context(self):
        with mock.patch.object(supervision, 'prompt_context', return_value='SUPERVISION-CONTEXT'):
            first = runner_core.build_prompt(self.project, self.current(), 'one', 'critical')
            put(self.project / 'AGENTS.md', 'NEW-LONG-TERM-METHOD')
            put(self.project / 'prompts/continue.md', 'NEW-NEXT-ROUND-TASK')
            second = runner_core.build_prompt(self.project, self.current(), 'two', 'critical')
        self.assertNotIn('NEW-NEXT-ROUND-TASK', first)
        self.assertIn('NEW-NEXT-ROUND-TASK', second)
        self.assertIn('NEW-LONG-TERM-METHOD', second)
        self.assertIn('SUPERVISION-CONTEXT', second)
        for relative in ('research/SUPERVISION_REPORT.md',
                         'research/supervision/review-1/proposal.json',
                         'AGENTS.md', 'prompts/continue.md'):
            self.assertTrue(runner_core.is_protected(relative), relative)

    def test_research_agent_cannot_rewrite_supervision_audit_trail(self):
        put(self.project / 'research/SUPERVISION_REPORT.md', 'Accepted independent supervision report.')

        def research(project, prompt, rid, *args, **kwargs):
            self.complete(rid)
            put(project / 'research/SUPERVISION_REPORT.md', 'Research agent claims it was independently approved.')
            put(project / 'research/supervision/forged/proposal.json', {'decision': 'approved'})
            return 0, 'offline.log'

        with mock.patch.object(runner_core.shutil, 'which', return_value='offline-codex'), \
             mock.patch.object(runner_core, 'codex_run', side_effect=research), \
             mock.patch.dict('os.environ', {'CRC_TRANSACTION_EXTERNAL': '0'}), \
             mock.patch.object(supervision, 'prompt_context', return_value=''):
            self.assertEqual(runner_core.run_round(self.project, round_num=1, seconds=30, skip_fetch=True), 5)
        self.assertEqual((self.project / 'research/SUPERVISION_REPORT.md').read_text(encoding='utf-8'),
                         'Accepted independent supervision report.')
        self.assertFalse((self.project / 'research/supervision/forged/proposal.json').exists())
        self.assertIsNone(self.current()['last_run'])

    def test_mixed_case_supervision_archive_cannot_be_forged_by_research(self):
        def research(project, prompt, rid, *args, **kwargs):
            self.complete(rid)
            put(project / 'research/SuPeRvIsIoN/forged/verdict.json', {'evidence_verified': True})
            return 0, 'offline.log'

        with mock.patch.object(runner_core.shutil, 'which', return_value='offline-codex'), \
             mock.patch.object(runner_core, 'codex_run', side_effect=research), \
             mock.patch.dict('os.environ', {'CRC_TRANSACTION_EXTERNAL': '0'}), \
             mock.patch.object(supervision, 'prompt_context', return_value=''):
            self.assertEqual(runner_core.run_round(self.project, round_num=1, seconds=30, skip_fetch=True), 5)
        self.assertFalse((self.project / 'research/SuPeRvIsIoN/forged/verdict.json').exists())
        self.assertIsNone(self.current()['last_run'])

    @unittest.skipUnless(os.name == 'nt', 'Windows directory junction regression')
    def test_windows_junction_is_rejected_and_rollback_keeps_external_files(self):
        import _winapi
        snapshot = runner_core.ProjectTransaction(self.project).capture()
        external = self.root / 'outside-project'
        put(external / 'keep.md', 'External bytes must remain untouched.')
        junction = self.project / 'proofs/escape'
        _winapi.CreateJunction(str(external), str(junction))
        self.addCleanup(lambda: junction.rmdir() if junction.exists() else None)
        with self.assertRaisesRegex(RuntimeError, 'junction'):
            list(runner_core.project_files(self.project))
        # Also exercise the lstat fallback used before pathlib gained
        # is_junction, rather than merely checking import compatibility.
        with mock.patch.object(Path, 'is_junction', None):
            with self.assertRaisesRegex(RuntimeError, 'junction'):
                list(runner_core.project_files(self.project))
            snapshot.rollback('reject directory junction')
        self.assertFalse(junction.exists())
        self.assertEqual((external / 'keep.md').read_text(encoding='utf-8'),
                         'External bytes must remain untouched.')


if __name__ == '__main__':
    unittest.main()
