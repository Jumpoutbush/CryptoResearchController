"""Idea onboarding, protected inputs and complete initialization receipts."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
import configuration
import research
import runner_core
from engine import initialization as init, discovery_scheduler as scheduler, problem_compiler
from research_quality import hash_file

SOURCE = Path(__file__).resolve().parents[1]


class InitializationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='initialization space ')
        self.root = Path(self.tmp.name)
        for directory in ('config', 'templates', 'method', 'prompts', 'profiles'):
            shutil.copytree(SOURCE / directory, self.root / directory)
        self.patches = [mock.patch.object(configuration, 'ROOT', self.root), mock.patch.object(research, 'ROOT', self.root),
            mock.patch.object(runner_core, 'ROOT', self.root), mock.patch.object(runner_core, 'METHOD', self.root / 'method')]
        for patch in self.patches: patch.start()
        self.idea = self.root / 'idea.md'; self.idea.write_text('A user idea with exact privacy goals.\nKeep the threat model and all original constraints.', encoding='utf8')
        self.assertEqual(self.cli(['new', 'fresh', '--idea-file', str(self.idea), '--title', 'New cryptography problem'])[0], 0)
        self.project = self.root / 'projects/fresh'

    def tearDown(self):
        for patch in reversed(self.patches): patch.stop()
        self.tmp.cleanup()

    def cli(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out): code = research.main(argv)
        return code, out.getvalue()

    def put(self, rel, value):
        path = self.project / rel; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) if isinstance(value, (dict, list)) else value, encoding='utf8')
        return path

    def manifest(self, status='READY_FOR_PROBLEM_REVIEW'):
        for rel in init.DOCUMENTS:
            self.put(rel, '# Derived draft\n\n' + 'Use supplied user constraints; this is an unproved initialization fixture. ' * 3)
        problem = configuration.load_json(self.root / 'templates/project/research/PROBLEM_TEMPLATE.json')
        problem.update(title='Exact test problem', statement='For every integer x, x*x >= 0',
            quantifiers='For all integers x', domain='Integers', input_contract='An exact integer x',
            output_contract='A nonnegative square', assumptions=['x is an integer'],
            immutable_constraints=['Exact arithmetic only'], goal_connection='Verify an initialization fixture',
            nontriviality_argument='Fixture only; not a research result', baseline_exclusions=['No scientific novelty claimed'],
            obligations=[{'id':'O-001','statement':'Show the exact square is nonnegative','acceptance_criterion':'Independent proof review'}])
        self.put('research/PROBLEM_PROPOSAL.json', problem)
        self.put('research/PROOF_OBLIGATIONS.json', {'schema_version': 1, 'obligations': [
            {'id': 'O-001', 'statement': 'Prove the exact fixture claim under unchanged assumptions',
             'status': 'OPEN', 'acceptance_criterion': 'Independent proof and statement review', 'dependencies': []}]})
        self.put('literature/SEARCH_PLAN.json', {'queries': ['precise cryptographic claim theorem', 'unchanged adversary privacy proof'],
            'scope': 'Fixture query generation only; no actual literature has been checked'})
        manifest = {'schema_version': 1, 'run_id': 'r1', 'status': status, 'source_bindings': init.input_bindings(self.project),
            'documents': [{'file': rel, 'sha256': hash_file(self.project / rel), 'status': 'DRAFT',
                           'source_paths': ['GOAL.md']} for rel in init.DOCUMENTS], 'unresolved_inputs': []}
        self.put('research/INITIALIZATION.json', manifest)
        state = configuration.load_json(self.project / 'research/STATE.json')
        state.update(initialization_required=False, initialization_status=status, phase='INTAKE',
                     decision='CONTINUE' if status == 'READY_FOR_PROBLEM_REVIEW' else 'PAUSE')
        self.put('research/STATE.json', state)
        return manifest

    def test_raw_idea_pinned_and_initialization_prompt_is_copied_and_injected(self):
        state = configuration.load_json(self.project / 'research/STATE.json')
        self.assertEqual(state['selected_idea'], {'id': 'IDEA-0001', 'version': 1})
        self.assertEqual((self.project / 'ideas/IDEA-0001/v001.md').read_text().strip(), self.idea.read_text().strip())
        self.assertTrue((self.project / 'prompts/initialize_from_idea.md').is_file())
        code, output = self.cli(['prompt', 'fresh', '--initialize'])
        self.assertEqual(code, 0, output); self.assertIn('从用户 idea 完成新科研项目初始化', output)
        self.assertIn('research/INITIALIZATION.json', output); self.assertIn('A user idea with exact privacy goals.', output)

    def test_initialize_preview_writes_no_state_and_does_not_call_model(self):
        before = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with mock.patch.object(research, 'run_child') as child:
            code, output = self.cli(['initialize', 'fresh', '--dry-run'])
            child.assert_not_called()
        self.assertEqual(code, 0, output)
        after = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_initialize_single_round_uses_unified_runner_and_preserves_raw_idea(self):
        before = (self.project / 'ideas/IDEA-0001/v001.md').read_bytes()
        with mock.patch.object(research, 'run_child', return_value=0) as child:
            code, output = self.cli(['initialize', 'fresh', '--max-seconds', '120', '--no-fetch'])
        self.assertEqual(code, 0, output)
        args = child.call_args.args[0]
        self.assertIn('--rounds', args); self.assertEqual(args[args.index('--rounds') + 1], '1')
        self.assertEqual((self.project / 'ideas/IDEA-0001/v001.md').read_bytes(), before)
        self.assertTrue(configuration.load_json(self.project / 'research/STATE.json')['initialization_required'])

    def test_complete_manifest_can_apply_generated_queries_but_keeps_custom_queries(self):
        self.manifest(); init.validate(self.project, 'r1'); init.finalize(self.project, 'r1')
        query = configuration.load_json(self.project / 'literature/queries.json')
        self.assertEqual(query['queries'][0], 'precise cryptographic claim theorem')
        self.put('literature/queries.json', {'queries': ['user customized fixed query'], 'generated_initial_query': False})
        init.finalize(self.project, 'r1')
        self.assertEqual(configuration.load_json(self.project / 'literature/queries.json')['queries'], ['user customized fixed query'])

    def test_missing_document_stale_input_or_forged_proof_status_is_rejected(self):
        self.manifest(); (self.project / 'research/ROADMAP.md').unlink()
        with self.assertRaises((ValueError, OSError)): init.validate(self.project, 'r1')
        self.manifest(); self.put('GOAL.md', 'Changed raw source invalidates initialization')
        with self.assertRaises(ValueError): init.validate(self.project, 'r1')
        self.manifest()
        obligations = configuration.load_json(self.project / 'research/PROOF_OBLIGATIONS.json')
        obligations['obligations'][0]['status'] = 'PROVED'; self.put('research/PROOF_OBLIGATIONS.json', obligations)
        manifest = configuration.load_json(self.project / 'research/INITIALIZATION.json')
        for doc in manifest['documents']:
            if doc['file'] == 'research/PROOF_OBLIGATIONS.json': doc['sha256'] = hash_file(self.project / doc['file'])
        self.put('research/INITIALIZATION.json', manifest)
        with self.assertRaises(ValueError): init.validate(self.project, 'r1')

    def test_blocking_gaps_cannot_be_ready_or_start_a_research_attempt(self):
        manifest = self.manifest(); manifest['unresolved_inputs'] = [{'question': 'Specify the adversary corruption model', 'blocking': True}]
        self.put('research/INITIALIZATION.json', manifest)
        with self.assertRaises(ValueError): init.validate(self.project, 'r1')
        self.manifest(status='NEEDS_INPUT')
        problem = configuration.load_json(self.project / 'research/PROBLEM_PROPOSAL.json')
        problem_compiler.import_problem(self.project, problem, 'User reviews the candidate problem')
        with self.assertRaises(ValueError): scheduler.start(self.project, problem['id'])

    def test_problem_start_enters_proof_without_rediscovering_or_switching_route(self):
        self.manifest(); spec = configuration.load_json(self.project / 'research/PROBLEM_PROPOSAL.json')
        problem_compiler.import_problem(self.project, spec, 'Explicitly reviewed fixed problem')
        before = configuration.load_json(self.project / 'research/STATE.json')
        scheduler.start(self.project, spec['id'])
        after = configuration.load_json(self.project / 'research/STATE.json')
        self.assertEqual(after['phase'], 'PROOF'); self.assertEqual(after['research_route'], before['research_route'])
        self.assertEqual(after['selected_idea'], before['selected_idea'])


if __name__ == '__main__': unittest.main()
