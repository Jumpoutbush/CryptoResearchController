"""Offline verification of transactional rounds and portable research budgets."""
import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import configuration
import route_budget
import runner
import runner_core

SOURCE = Path(__file__).resolve().parents[1]


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) if isinstance(value, (dict, list)) else value, encoding='utf-8')


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for directory in ('config', 'method', 'profiles'):
            shutil.copytree(SOURCE / directory, self.root / directory)
        (self.root / 'runner_core.py').write_text('# test placeholder', encoding='utf-8')
        self.project = self.root / 'projects/subject'
        self.project.mkdir(parents=True)
        put(self.project / 'PROJECT.json', {'id': 'subject'})
        put(self.project / 'GOAL.md', '# Fixed research goal\nStudy one explicit, falsifiable cryptographic claim.')
        put(self.project / 'AGENTS.md', '# Instructions\nPreserve the target and evidence.')
        put(self.project / 'RESEARCH_PROFILE.json', {'profiles': [], 'read_order': []})
        put(self.project / 'literature/queries.json', {'queries': []})
        put(self.project / 'research/STATE.json', self.state())
        put(self.project / 'proofs/original.md', 'Accepted original evidence.\n')
        self.patches = [
            mock.patch.object(runner_core, 'ROOT', self.root),
            mock.patch.object(runner_core, 'METHOD', self.root / 'method'),
            mock.patch.object(runner, 'HERE', self.root),
            mock.patch.object(runner, 'CORE', self.root / 'runner_core.py'),
            mock.patch.object(configuration, 'ROOT', self.root),
            mock.patch.dict('os.environ', {'CRC_TRANSACTION_EXTERNAL': '0', 'CRC_DEFER_CHECKPOINT': '0'}),
        ]
        for patch in self.patches: patch.start()

    def tearDown(self):
        for patch in reversed(self.patches): patch.stop()
        self.temp.cleanup()

    @staticmethod
    def state():
        return {'phase': 'FALSIFICATION', 'decision': 'CONTINUE', 'research_route': 'C/TEST',
                'priority_problem': 'One precise research obstruction with independently testable evidence.',
                'next_task': 'Perform a decisive counterexample search and save the exact counterexample.',
                'last_run': None, 'open_obligations': [], 'verified_results': [],
                'publication_status': 'NOT_ESTABLISHED'}

    def current(self):
        return json.loads((self.project / 'research/STATE.json').read_text())

    def complete(self, rid='round-1', *, route=None, next_task=None):
        state = self.current()
        state['last_run'] = rid
        if route is not None: state['research_route'] = route
        if next_task is not None: state['next_task'] = next_task
        else: state['next_task'] = 'Check the remaining quantified condition using the independently recorded evidence.'
        put(self.project / 'research/STATE.json', state)
        put(self.project / f'reports/{rid}.md', f'RUN_ID: {rid}\n' + 'Substantive evidence was generated and exact tests are recorded. ' * 10)
        put(self.project / 'proofs/new.md', 'A new proof obligation with exact assumptions and an independently testable claim.')
        put(self.project / 'research/ROUTE_SIGNAL.json', {'run_id': rid, 'progress_type': 'PROOF_STEP',
            'reason': 'A precise new proof obligation has been isolated and independently recorded.',
            'evidence_paths': ['proofs/new.md'], 'route_blocked': False})
        put(self.project / 'research/ROUND_REVIEW.json', {'schema_version':1,'run_id':rid,'work_kind':'PROOF',
            'core_problem':'Decisive fixed-target mathematical obstruction','theoretical_obligation':'Prove the remaining quantified condition',
            'nontriviality_argument':'Existing lemma does not cover the original integer constraints',
            'contribution_type':'NONE','result_status':'OPEN','evidence_paths':['proofs/new.md']})

    def advance(self, child):
        policy, _, _ = route_budget.policy_for(self.root, self.project)
        ledger_path, ledger, epoch = route_budget.load_ledger(self.root, self.project, self.current())
        with mock.patch.object(runner, 'run_child', side_effect=child), mock.patch.object(runner_core, 'git_checkpoint', return_value='TEST_CHECKPOINT'):
            result = runner.advance_one(self.project, policy, ledger_path, ledger, epoch, ['python', 'core'])
        return result, ledger, epoch

    def test_inspection_is_read_only_and_no_fetch_alias(self):
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*'))
        with mock.patch.object(runner, 'run_child', return_value=0) as child:
            self.assertEqual(runner.main(['--project', str(self.project), '--dry-run', '--no-fetch']), 0)
            self.assertIn('--skip-fetch', child.call_args.args[0])
        self.assertEqual(runner.main(['--project', str(self.project), '--route-status']), 0)
        self.assertEqual(before, sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*')))

    def test_project_identity_and_budget_survive_relocation(self):
        route_budget.set_project_override(self.root, self.project, {'initial_round_budget': 11})
        policy, _, _ = route_budget.policy_for(self.root, self.project)
        path, ledger, epoch = route_budget.load_ledger(self.root, self.project, self.current())
        epoch['effective_rounds'] = 3
        route_budget.save_ledger(path, ledger)
        moved = self.root / 'relocated/subject'
        moved.parent.mkdir()
        shutil.move(self.project, moved)
        moved_policy, _, _ = route_budget.policy_for(self.root, moved)
        _, _, moved_epoch = route_budget.load_ledger(self.root, moved, json.loads((moved / 'research/STATE.json').read_text()))
        self.assertEqual(policy['initial_round_budget'], 11)
        self.assertEqual(moved_policy['initial_round_budget'], 11)
        self.assertEqual(moved_epoch['effective_rounds'], 3)

    def test_budget_updates_preserve_other_settings(self):
        put(self.root / 'config/projects/subject.json', {'execution': {'max_seconds': 1800}})
        path = route_budget.set_project_override(self.root, self.project, {'initial_round_budget': 10})
        updated = json.loads(path.read_text())
        self.assertEqual(updated['execution']['max_seconds'], 1800)
        self.assertEqual(updated['route_policy']['initial_round_budget'], 10)

    def test_wrapper_accepts_and_counts_one_round(self):
        def child(command):
            self.complete()
            return 0
        result, ledger, epoch = self.advance(child)
        self.assertEqual(result, (0, 'COUNTED_RESEARCH_ROUND'))
        self.assertEqual(epoch['effective_rounds'], 1)
        self.assertEqual(epoch['stagnation'], 0)
        self.assertTrue((self.project / 'proofs/new.md').is_file())

    def test_wrapper_rejects_unchanged_next_task_and_restores_evidence(self):
        def child(command):
            task = self.current()['next_task']
            self.complete(next_task=task)
            (self.project / 'proofs/original.md').write_text('Invalid replacement')
            return 0
        result, _, epoch = self.advance(child)
        self.assertEqual(result[0], 3)
        self.assertEqual(epoch['effective_rounds'], 0)
        self.assertEqual(self.current()['last_run'], None)
        self.assertEqual(self.current()['decision'], 'NEEDS_REVIEW')
        self.assertFalse((self.project / 'proofs/new.md').exists())
        self.assertFalse((self.project / 'reports/round-1.md').exists())
        self.assertEqual((self.project / 'proofs/original.md').read_text(), 'Accepted original evidence.\n')
        self.assertTrue(list((self.root / 'state/failed_runs').rglob('new.md')))

    def test_wrapper_restores_unauthorized_route_change(self):
        def child(command):
            self.complete(route='D/CHANGED')
            return 0
        result, _, _ = self.advance(child)
        self.assertEqual(result[1], 'UNCONTROLLED_ROUTE_CHANGE')
        self.assertEqual(self.current()['research_route'], 'C/TEST')
        self.assertEqual(self.current()['last_run'], None)

    def test_review_uses_audit_and_commits_final_extension(self):
        policy, _, _ = route_budget.policy_for(self.root, self.project)
        path, ledger, epoch = route_budget.load_ledger(self.root, self.project, self.current())
        epoch['effective_rounds'] = policy['initial_round_budget']
        route_budget.save_ledger(path, ledger)
        def child(command):
            self.assertIn('--audit', command)
            self.complete()
            put(self.project / 'research/ROUTE_VERDICT.json', {'run_id': 'round-1', 'outcome': 'EXTEND',
                'reason': 'A concrete new subclaim has been identified with reproducible proof evidence.',
                'evidence_paths': ['proofs/new.md'], 'requires_goal_change': False,
                'next_task': 'Prove the new quantified subclaim and retain an independently checkable certificate.'})
            return 0
        def checkpoint(project, rid):
            self.assertEqual(self.current()['decision'], 'CONTINUE')
            self.assertEqual(json.loads(path.read_text())['epochs'][-1]['extensions_used'], 1)
            return 'FINAL_CHECKPOINT'
        with mock.patch.object(runner, 'run_child', side_effect=child), mock.patch.object(runner_core, 'git_checkpoint', side_effect=checkpoint):
            self.assertEqual(runner.advance_one(self.project, policy, path, ledger, epoch, ['python', 'core']), (0, 'EXTENDED'))

    def test_agent_cannot_create_its_own_theory_approval(self):
        def native(project,prompt,rid,*args,**kwargs):
            self.complete(rid)
            put(project/'research/THEORY_READINESS.json',{'decision':'APPROVED'})
            return 0,'test-log'
        with mock.patch.object(runner_core.shutil,'which',return_value='fake-codex'), mock.patch.object(runner_core,'codex_run',side_effect=native):
            self.assertEqual(runner_core.run_round(self.project,round_num=1,seconds=30,skip_fetch=True),5)
        self.assertFalse((self.project/'research/THEORY_READINESS.json').exists())
        self.assertEqual(self.current()['last_run'],None)

    def test_core_rolls_back_malformed_gates_and_protected_inputs(self):
        original = self.current()
        def codex(project, prompt, rid, *args, **kwargs):
            self.complete(rid)
            put(project / 'GOAL.md', 'Unauthorized goal')
            put(project / 'research/GATES.json', '{ invalid JSON')
            return 0, 'fake.log'
        with mock.patch.object(runner_core.shutil, 'which', return_value='/fake/codex'), mock.patch.object(runner_core, 'codex_run', side_effect=codex):
            self.assertEqual(runner_core.run_round(self.project, round_num=1, seconds=30, skip_fetch=True), 2)
        self.assertEqual(self.current(), original)
        self.assertTrue((self.project / 'GOAL.md').read_text().startswith('# Fixed'))
        self.assertFalse((self.project / 'proofs/new.md').exists())
        self.assertFalse((self.project / 'research/GATES.json').exists())
        self.assertTrue(list((self.root / 'state/failed_runs').rglob('GATES.json')))

    def test_core_interruption_restores_full_project(self):
        original = self.current()
        def codex(project, prompt, rid, *args, **kwargs):
            self.complete(rid)
            put(project / 'inputs/CONTEXT.md', 'Unauthorized input')
            raise KeyboardInterrupt
        with mock.patch.object(runner_core.shutil, 'which', return_value='/fake/codex'), mock.patch.object(runner_core, 'codex_run', side_effect=codex):
            with self.assertRaises(KeyboardInterrupt):
                runner_core.run_round(self.project, round_num=1, seconds=30, skip_fetch=True)
        self.assertEqual(self.current(), original)
        self.assertFalse((self.project / 'inputs/CONTEXT.md').exists())
        self.assertFalse((self.project / 'proofs/new.md').exists())

    def test_stop_request_skips_subprocess(self):
        put(self.project / '.control/STOP_REQUESTED', 'stop')
        with mock.patch.object(runner, 'run_child') as child:
            result, _, _ = self.advance(child)
        self.assertEqual(result, (0, 'SKIPPED_BY_STOP_REQUEST'))
        child.assert_not_called()

    def test_snapshot_reuses_large_asset_and_restores_file_directory_change(self):
        pdf = self.project / 'literature/pdfs/sample.pdf'
        put(pdf, '%PDF-1.7\n' + 'Original source bytes. ' * 300)
        first = runner_core.ProjectTransaction(self.project).capture()
        before = {p.name for p in first.blobs.iterdir()}
        with mock.patch.object(runner_core.shutil, 'copy2', wraps=shutil.copy2) as copied:
            second = runner_core.ProjectTransaction(self.project).capture()
            self.assertEqual(copied.call_count, 0)
        original = self.project / 'proofs/original.md'
        original.unlink()
        original.mkdir()
        put(original / 'new.txt', 'Invalid nested file')
        second.rollback('file became a directory')
        self.assertTrue(original.is_file())
        self.assertEqual(before, {p.name for p in first.blobs.iterdir()})

    def test_agent_cannot_switch_pinned_idea_in_state(self):
        state = self.current()
        state['selected_idea'] = {'id': 'IDEA-0001', 'version': 1}
        put(self.project / 'research/STATE.json', state)
        def child(command):
            self.complete()
            changed = self.current()
            changed['selected_idea']['version'] = 2
            put(self.project / 'research/STATE.json', changed)
            return 0
        result, _, _ = self.advance(child)
        self.assertEqual(result[1], 'UNCONTROLLED_IDEA_CHANGE')
        self.assertEqual(self.current()['selected_idea']['version'], 1)
        self.assertEqual(self.current()['last_run'], None)

    def test_automatic_route_pivot_releases_original_idea_pin(self):
        state = self.current()
        pin = {'id': 'IDEA-0001', 'version': 1}
        state['selected_idea'] = pin
        put(self.project / 'research/STATE.json', state)
        put(self.project / 'ideas/INDEX.json', {'schema_version': 1, 'active_idea': pin, 'ideas': [], 'events': []})
        policy, _, _ = route_budget.policy_for(self.root, self.project)
        path, ledger, epoch = route_budget.load_ledger(self.root, self.project, state)
        candidate = {'route': 'B/FEASIBILITY', 'goal_compatible': True, 'requires_goal_change': False,
            'novelty_question_identified': True, 'priority': 1,
            'priority_problem': 'A different precise subclaim preserves the fixed research objective.',
            'next_task': 'Run the smallest decisive feasibility test for the alternative construction.',
            'evidence_paths': ['proofs/original.md'], 'theoretical_contribution': {
                'type':'PROTOCOL_CONSTRUCTION','statement':'An explicit alternative property',
                'novelty_mechanism':'A new relation invariant','closest_prior_work':'Fixed original comparison',
                'nontriviality_argument':'The existing result lacks the needed integer interface',
                'proof_obligation':'Prove the full quantified invariant','evidence_paths':['proofs/original.md']}}
        put(self.project / 'research/ROUTE_VERDICT.json', {'run_id': 'pivot-1', 'outcome': 'PIVOT_PROVISIONAL',
            'reason': 'The original route has a concrete counterexample and the alternative preserves the goal.',
            'failure_class':'COUNTEREXAMPLE','failed_claim':'C-001','failure_scope':'CORE_ROUTE',
            'scope_argument':'Only this exact route is rejected','dependency_argument':'This constraint is necessary for the core construction',
            'satisfied_preconditions':'The fixed bounded input conditions hold','violated_conclusion':'The claimed exact equality fails',
            'evidence_paths': ['proofs/original.md'], 'requires_goal_change': False, 'candidates': [candidate]})
        after = copy.deepcopy(state); after['last_run'] = 'pivot-1'
        result = runner.apply_review(self.project, ledger, epoch, policy, after)
        self.assertEqual(result, 'PIVOT_PROVISIONAL')
        self.assertEqual(self.current()['selected_idea'], None)
        self.assertEqual(self.current()['origin_idea'], pin)
        self.assertEqual(json.loads((self.project / 'ideas/INDEX.json').read_text())['active_idea'], None)

    def test_failed_registered_check_rejects_and_restores_round(self):
        original = self.current()
        put(self.project / 'scripts/check.py', 'raise SystemExit(7)\n')
        manifest = json.loads((self.project / 'PROJECT.json').read_text())
        manifest['checks'] = [['scripts/check.py']]
        put(self.project / 'PROJECT.json', manifest)
        def codex(project, prompt, rid, *args, **kwargs):
            self.complete(rid)
            return 0, 'fake.log'
        with mock.patch.object(runner_core.shutil, 'which', return_value='/fake/codex'), mock.patch.object(runner_core, 'codex_run', side_effect=codex):
            self.assertEqual(runner_core.run_round(self.project, round_num=1, seconds=30, skip_fetch=True), 5)
        self.assertEqual(self.current(), original)
        self.assertFalse((self.project / 'proofs/new.md').exists())
        status = json.loads((self.root / 'logs/subject/latest-status.json').read_text())
        self.assertEqual(status['registered_checks'][0]['exit_code'], 7)
        self.assertTrue(Path(status['registered_checks'][0]['log_path']).is_file())

    def test_persisted_execution_timeout_is_used(self):
        put(self.root / 'config/projects/subject.json', {'execution': {'max_seconds': 1234}})
        with mock.patch.object(runner_core, 'run_round', return_value=0) as executed:
            self.assertEqual(runner_core.main(['--project', str(self.project), '--no-fetch']), 0)
        self.assertEqual(executed.call_args.kwargs['seconds'], 1234)

    def test_ignored_extracted_text_does_not_block_checkpoint(self):
        if shutil.which('git') is None: self.skipTest('git unavailable')
        (self.root / '.gitignore').write_text('**/literature/text/\n',encoding='utf8')
        subprocess.run(['git', 'init', '-b', 'main', str(self.root)], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(self.root), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Tester', '-c', 'user.email=tester@localhost', 'commit', '-m', 'initial'], check=True, capture_output=True)
        (self.project / 'literature/text').mkdir()
        put(self.project / 'literature/text/paper.txt', 'Derived untracked extraction')
        put(self.project / 'proofs/new.md', 'Accepted proof evidence')
        self.assertEqual(runner_core.git_checkpoint(self.project, 'test-round'), 'OK')
        staged = subprocess.run(['git', '-C', str(self.root), 'diff', '--cached', '--quiet'], capture_output=True)
        self.assertEqual(staged.returncode, 0)
        last = subprocess.run(['git', '-C', str(self.root), 'show', '--name-only', '--format='], capture_output=True, text=True).stdout
        self.assertIn('proofs/new.md', last)
        self.assertNotIn('literature/text', last)

    def test_root_git_checkpoint_does_not_stage_other_project(self):
        if shutil.which('git') is None: self.skipTest('git unavailable')
        subprocess.run(['git', 'init', '-b', 'main', str(self.root)], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(self.root), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Tester', '-c', 'user.email=tester@localhost', 'commit', '-m', 'initial'], check=True, capture_output=True)
        put(self.project / 'proofs/new.md', 'Accepted evidence')
        put(self.project / 'ideas/IDEA-0001/v001.md', 'Versioned user research idea')
        put(self.project / 'ideas/INDEX.json', {'active_idea': {'id': 'IDEA-0001', 'version': 1}})
        put(self.project / 'inputs/NOTATION.md', 'Fixed notation supplied by user')
        put(self.project / 'literature/CATALOG.json', {'papers': []})
        put(self.root / 'config/projects/subject.json', {'route_policy': {'initial_round_budget': 9}})
        put(self.root / 'projects/other/private.md', 'Unrelated untracked work')
        path, ledger, _ = route_budget.load_ledger(self.root, self.project, self.current())
        route_budget.save_ledger(path, ledger)
        self.assertEqual(runner_core.git_checkpoint(self.project, 'test-round'), 'OK')
        last = subprocess.run(['git', '-C', str(self.root), 'show', '--name-only', '--format='], check=True, capture_output=True, text=True).stdout
        self.assertIn('projects/subject/proofs/new.md', last)
        self.assertIn('state/routes/subject.json', last)
        self.assertIn('ideas/IDEA-0001/v001.md', last)
        self.assertIn('ideas/INDEX.json', last)
        self.assertIn('inputs/NOTATION.md', last)
        self.assertIn('literature/CATALOG.json', last)
        self.assertIn('config/projects/subject.json', last)
        self.assertNotIn('projects/other', last)
        dirty = subprocess.run(['git', '-C', str(self.root), 'status', '--porcelain'], check=True, capture_output=True, text=True).stdout
        self.assertIn('projects/other', dirty)


if __name__ == '__main__':
    unittest.main()
