"""Discovery invariants, exact witnesses and simulated model/verifier boundaries."""
import contextlib
import copy
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
import configuration
import research
import research_quality
import runner
import runner_core
import route_budget
import theory_gate
from engine import claim_graph as graph, deep_reasoning as deep, discovery_scheduler as scheduler
from engine import falsification, formal_verifier, problem_compiler
from engine.common import goal_binding, ledger, object_hash

SOURCE = Path(__file__).resolve().parents[1]


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='discovery space ')
        self.root = Path(self.tmp.name)
        shutil.copytree(SOURCE / 'config', self.root / 'config')
        shutil.copytree(SOURCE / 'prompts', self.root / 'prompts')
        shutil.copytree(SOURCE / 'method', self.root / 'method')
        self.project = self.root / 'projects/example'; self.project.mkdir(parents=True)
        self.put('PROJECT.json', {'id': 'example', 'checks': []})
        self.put('GOAL.md', 'Keep the exact integer target and immutable security requirements.')
        self.put('AGENTS.md', 'Do not weaken the target.')
        self.put('RESEARCH_PROFILE.json', {'profiles': [], 'read_order': []})
        self.put('literature/queries.json', {'queries': ['exact integer completion']})
        self.state = {'phase': 'CONSTRUCTION', 'decision': 'CONTINUE', 'last_run': None,
                      'research_route': 'C/MAIN', 'priority_problem': 'Exact integer completion',
                      'next_task': 'Prove the precise quantified statement under its unchanged assumptions.'}
        self.put('research/STATE.json', self.state)
        self.put('proofs/derivation.md', 'A candidate derivation requiring independent verification.')
        self.patches = [mock.patch.object(configuration, 'ROOT', self.root),
            mock.patch.object(research, 'ROOT', self.root), mock.patch.object(runner_core, 'ROOT', self.root),
            mock.patch.object(runner_core, 'METHOD', self.root / 'method'), mock.patch.object(runner, 'HERE', self.root)]
        for patch in self.patches: patch.start()
        self.spec = {'schema_version': 1, 'id': 'P-1', 'title': 'Toy exact invariant',
            'statement': 'For every integer x, x*x >= 0.', 'quantifiers': 'for all x', 'domain': 'integers',
            'input_contract': 'x is an integer', 'output_contract': 'a nonnegative exact square',
            'goal_connection': 'Check an exact integer obligation without changing the research goal',
            'nontriviality_argument': 'Infrastructure fixture only; no research novelty is claimed',
            'assumptions': ['x is an integer'], 'immutable_constraints': ['Exact integer arithmetic'],
            'baseline_exclusions': ['This elementary result is not a new cryptographic contribution'],
            'contribution_type': 'COMPLEXITY_THEOREM', 'source_paths': [],
            'obligations': [{'id': 'O-1', 'statement': 'Exact invariant', 'acceptance_criterion': 'Independent proof review'}]}
        self.problem = problem_compiler.import_problem(self.project, self.spec, 'Initial test contract')

    def tearDown(self):
        for patch in reversed(self.patches): patch.stop()
        self.tmp.cleanup()

    def put(self, rel, obj):
        path = self.project / rel; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) if isinstance(obj, (dict, list)) else obj, encoding='utf8')
        return path

    def cli(self, argv):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return research.main(argv)

    def claim(self, cid='C-1', deps=None, **updates):
        spec = {'schema_version': 1, 'id': cid, 'statement': 'For all integer x, x*x >= 0',
            'assumptions': ['x is an integer'], 'dependencies': deps or [], 'proposer': 'model-proposer',
            'problem_id': 'P-1', 'problem_version': 1, 'obligation_ids': ['O-1'],
            'nontriviality_argument': 'Test fixture only, never a scientific novelty claim',
            'contribution_type': 'COMPLEXITY_THEOREM', 'evidence_paths': ['proofs/derivation.md'],
            'verification_mode': 'INDEPENDENT_MANUAL',
            'formal_applicability_reason': 'This fixture tests manual review, without claiming a Lean check',
            'machine_statement': {'domain': 'INTEGER', 'variables': ['x'], 'preconditions': [], 'conclusion': 'x*x >= 0'}}
        spec.update(updates)
        graph.import_claim(self.project, spec, 'Register fixture')
        return spec

    def review_proof(self, cid='C-1'):
        for kind in ('proof', 'statement'):
            self.put('research/' + kind + '-' + cid + '.md', 'Independent operator review fixture for ' + kind)
            graph.review(self.project, cid, kind, 'research/' + kind + '-' + cid + '.md', 'independent-operator', 'Reviewed this exact test claim')

    def checkpoint(self, rid, **updates):
        item = scheduler.active(self.project)
        obj = {'schema_version': 1, 'attempt_id': item['id'], 'run_id': rid,
            'problem_sha256': item['problem_sha256'], 'outcome': 'OPEN',
            'obligations': [{'id': 'O-1', 'status': 'OPEN', 'claim_id': None, 'gap': 'The exact lemma remains unproved'}],
            'candidate_claim_ids': [], 'evidence_paths': ['proofs/derivation.md'],
            'next_action': 'Resolve the remaining lemma without changing its assumptions.'}
        obj.update(updates)
        self.put(deep.checkpoint_path(item), obj)
        return deep.validate_checkpoint(self.project, rid)

    def test_problem_revisions_do_not_silently_replace_active_statement(self):
        scheduler.start(self.project, 'P-1')
        spec = copy.deepcopy(self.spec); spec['statement'] = 'A revised, explicit different statement'
        problem_compiler.import_problem(self.project, spec, 'Operator revises the next problem')
        self.assertEqual(scheduler.check(self.project)['problem_version'], 1)
        self.assertIn(self.spec['statement'], deep.context(self.project))

    def test_goal_relaxation_blocks_before_model_budget_is_spent(self):
        scheduler.start(self.project, 'P-1'); self.put('GOAL.md', 'Weakened goal')
        with self.assertRaises(ValueError): scheduler.begin_call(self.project, 'r1')
        self.assertEqual(len(scheduler.active(self.project)['calls']), 0)

    def test_unpinned_idea_can_be_added_without_invalidating_attempt(self):
        scheduler.start(self.project, 'P-1')
        self.assertEqual(self.cli(['ideas', 'add', 'example', '--title', 'An extra idea', '--text', 'A future candidate lemma, not yet selected']), 0)
        scheduler.check(self.project)
        self.assertEqual(self.cli(['ideas', 'attach', 'example', '--id', 'IDEA-0001']), 0)
        with self.assertRaises(ValueError): scheduler.check(self.project)

    def test_failed_calls_are_charged_and_budget_does_not_restart(self):
        configuration.atomic_json(self.root / 'config/projects/example.json', {'discovery_policy': {'initial_round_budget': 2, 'stagnation_rounds': 2}})
        scheduler.start(self.project, 'P-1')
        for rid in ('r1', 'r2'):
            scheduler.begin_call(self.project, rid); scheduler.finish_call(self.project, rid, accepted=False)
        item = scheduler.active(self.project)
        self.assertEqual(item['status'], 'BUDGET_EXHAUSTED'); self.assertEqual(len(item['calls']), 2)
        with self.assertRaises(ValueError): scheduler.begin_call(self.project, 'r3')
        scheduler.extend(self.project, 'Operator chooses one bounded extension')
        self.assertEqual(len(scheduler.active(self.project)['calls']), 2)
        self.assertEqual(scheduler.active(self.project)['budget'], 6)
        with self.assertRaises(ValueError): scheduler.extend(self.project, 'Unbounded extensions forbidden')

    def test_deep_and_falsification_slots_reuse_exact_obligations(self):
        scheduler.start(self.project, 'P-1'); scheduler.begin_call(self.project, 'r1')
        checkpoint = self.checkpoint('r1'); scheduler.finish_call(self.project, 'r1', accepted=True, checkpoint=checkpoint)
        context = deep.context(self.project)
        self.assertIn('MODE: FALSIFICATION', context); self.assertIn('The exact lemma remains unproved', context)
        self.assertEqual(runner_core.plan_route(self.project, self.state)[0], 'critical')

    def test_model_cannot_drop_or_self_certify_an_obligation(self):
        scheduler.start(self.project, 'P-1')
        with self.assertRaises(ValueError): self.checkpoint('r1', obligations=[])
        with self.assertRaises(ValueError): self.checkpoint('r1', outcome='PROVED')
        with self.assertRaises(ValueError): self.checkpoint('r1', obligations=[{'id': 'O-1', 'status': 'DISCHARGED', 'claim_id': 'FAKE', 'gap': 'The model says true'}])

    def test_reviewed_claim_can_close_only_its_registered_obligation(self):
        self.claim(); self.review_proof(); scheduler.start(self.project, 'P-1')
        result = self.checkpoint('r1', obligations=[{'id': 'O-1', 'status': 'DISCHARGED', 'claim_id': 'C-1', 'gap': 'Independent statement and proof reviews are current'}])
        self.assertEqual(result['obligations'][0]['status'], 'DISCHARGED')

    def test_cycles_and_missing_dependencies_rejected(self):
        with self.assertRaises(ValueError): self.claim('C-1', ['MISSING'])
        self.claim('C-1'); self.claim('C-2', ['C-1'])
        with self.assertRaises(ValueError): self.claim('C-1', ['C-2'])

    def test_transitive_invalidation_and_revised_dependency_pins(self):
        first = self.claim(); self.review_proof()
        self.claim('C-2', ['C-1']); self.review_proof('C-2')
        self.claim('C-3', ['C-2']); self.review_proof('C-3')
        self.assertTrue(all(c['proof_status'] == 'INDEPENDENTLY_REVIEWED' for c in graph.status(self.project)['claims']))
        first['statement'] += ' with an explicit domain clarification'
        graph.import_claim(self.project, first, 'Correct upstream statement')
        states = {c['id']: c for c in graph.status(self.project)['claims']}
        self.assertIn('DEPENDENCY_REVISED:C-1', states['C-2']['invalidation_reasons'])
        self.assertEqual(states['C-3']['proof_status'], 'PENDING_REVALIDATION')
        self.assertEqual(len(graph.get(self.project, 'C-1')['history']), 1)
        old = graph.get(self.project, 'C-2')['spec']
        graph.import_claim(self.project, old, 'Explicitly rebind to corrected upstream version')
        self.assertEqual(graph.get(self.project, 'C-2')['revision'], 2)

    def test_changed_review_evidence_invalidates_dependents(self):
        self.claim(); self.review_proof(); self.claim('C-2', ['C-1']); self.review_proof('C-2')
        self.put('research/proof-C-1.md', 'Changed proof review needs rechecking')
        self.assertTrue(all(c['proof_status'] != 'INDEPENDENTLY_REVIEWED' for c in graph.status(self.project)['claims']))

    def test_self_review_rejected_and_new_claim_stays_unverified(self):
        self.claim()
        with self.assertRaises(ValueError): graph.review(self.project, 'C-1', 'proof', 'proofs/derivation.md', 'MODEL-PROPOSER', 'Self-approval')
        self.assertFalse(graph.status(self.project)['claims'][0]['accepted_contribution'])

    def test_empty_graph_cannot_bypass_theory_gate_for_compiled_problem(self):
        with self.assertRaises(ValueError): graph.require_theory_claim(self.project, 'FAKE')

    def test_exact_modular_counterexample_invalidates_downstream_claims(self):
        machine = {'domain': 'INTEGER', 'variables': ['a', 'q'], 'preconditions': ['q > 1', 'a % q == 0'], 'conclusion': 'a == q'}
        self.claim(machine_statement=machine); self.review_proof(); self.claim('C-2', ['C-1']); self.review_proof('C-2')
        receipt = falsification.search(self.project, 'C-1', witness={'a': 0, 'q': 7})
        self.assertEqual(receipt['status'], 'EXACT_COUNTEREXAMPLE')
        states = graph.status(self.project)['claims']
        self.assertIn('MACHINE_STATEMENT_REFUTED', states[0]['invalidation_reasons'])
        self.assertIn('DEPENDENCY_NOT_VALID:C-1', states[1]['invalidation_reasons'])
        falsification.search(self.project, 'C-1', witness={'a': 7, 'q': 7})
        self.assertIsNotNone(graph.get(self.project, 'C-1')['counterexample_receipt'])

    def test_bounded_no_counterexample_never_proves_universal_statement(self):
        self.claim(); result = falsification.search(self.project, 'C-1', -3, 3)
        self.assertEqual(result['status'], 'SEARCHED_NOT_FOUND')
        self.assertEqual(graph.status(self.project)['claims'][0]['proof_status'], 'CANDIDATE')

    def test_counterexample_must_satisfy_preconditions_and_expression_is_not_code(self):
        spec = {'domain': 'INTEGER', 'variables': ['x'], 'preconditions': ['x > 0'], 'conclusion': 'x > 1'}
        self.assertFalse(falsification.check_witness(spec, {'x': 0})['is_counterexample'])
        self.assertTrue(falsification.check_witness(spec, {'x': 1})['is_counterexample'])
        guarded = {'domain': 'INTEGER', 'variables': ['a', 'q'], 'preconditions': ['q > 1', 'a % q == 0'], 'conclusion': 'a == q'}
        self.assertFalse(falsification.check_witness(guarded, {'a': 0, 'q': 0})['is_counterexample'])
        for unsafe in ["__import__('os').system('echo bad') == 0", 'x**999999 == 0', 'x.__class__ == 0']:
            with self.assertRaises(ValueError): falsification.validate_statement({**spec, 'conclusion': unsafe})

    def test_unavailable_lean_does_not_run_or_install_anything(self):
        self.claim(); self.put('proofs/lean/Check.lean', 'theorem target : True := True.intro')
        with mock.patch.object(formal_verifier.shutil, 'which', return_value=None), mock.patch.object(formal_verifier.subprocess, 'run') as child:
            result = formal_verifier.run(self.project, 'C-1', 'proofs/lean/Check.lean', 'target')
            child.assert_not_called()
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertFalse(graph.status(self.project)['claims'][0]['accepted_contribution'])

    def fake_codex(self, project, prompt, rid, *args, **kwargs):
        self.put('reports/' + rid + '.md', 'RUN_ID: ' + rid + '\n' + 'A concrete bounded mathematical derivation fixture. ' * 10)
        state = configuration.load_json(project / 'research/STATE.json'); state['last_run'] = rid
        state['next_task'] = 'Check the remaining exact lemma with the saved counterexample boundary.'
        self.put('research/STATE.json', state)
        self.put('proofs/derivation.md', 'New candidate mathematical step ' + rid)
        self.put('research/ROUND_REVIEW.json', {'schema_version': 1, 'run_id': rid, 'work_kind': 'PROOF',
            'core_problem': 'Fixed precise integer problem', 'theoretical_obligation': 'O-1',
            'nontriviality_argument': 'Test fixture only, no actual research claim', 'contribution_type': 'NONE',
            'result_status': 'OPEN', 'evidence_paths': ['proofs/derivation.md']})
        self.checkpoint(rid)
        return 0, 'simulated-codex.log'

    def test_native_round_persists_mathematical_checkpoint_and_call_budget(self):
        scheduler.start(self.project, 'P-1')
        with mock.patch.object(runner_core.shutil, 'which', return_value='/simulated/codex'), mock.patch.object(runner_core, 'codex_run', side_effect=self.fake_codex), mock.patch.object(runner_core, 'git_checkpoint', return_value='SKIPPED_TEST'):
            code = runner_core.run_round(self.project, round_num=1, seconds=30, skip_fetch=True)
        self.assertEqual(code, 0)
        item = scheduler.active(self.project)
        self.assertEqual(item['calls'][0]['status'], 'ACCEPTED')
        self.assertIn('The exact lemma remains unproved', deep.context(self.project))
        archives = list((self.root / 'state/discovery/checkpoints/example').rglob('*.json'))
        self.assertEqual(len(archives), 1)

    def test_model_cannot_write_controller_owned_claim_graph_and_failed_call_stays_charged(self):
        scheduler.start(self.project, 'P-1')
        def attack(*args, **kwargs):
            result = self.fake_codex(*args, **kwargs)
            self.put('research/discovery/CLAIM_GRAPH.json', {'schema_version': 1, 'claims': [{'id': 'FORGED'}]})
            return result
        with mock.patch.object(runner_core.shutil, 'which', return_value='/simulated/codex'), mock.patch.object(runner_core, 'codex_run', side_effect=attack):
            code = runner_core.run_round(self.project, round_num=1, seconds=30, skip_fetch=True)
        self.assertNotEqual(code, 0); self.assertEqual(graph.load(self.project)['claims'], [])
        self.assertEqual(scheduler.active(self.project)['calls'][0]['status'], 'FAILED')
        self.assertIsNone(scheduler.active(self.project)['checkpoint'])

    def novelty_review(self, cid='C-1'):
        self.put('literature/primary.txt', 'Fixture primary text; not actual prior-art research')
        self.put('literature/mapping.md', 'Fixture theorem-to-theorem technical mapping')
        technical = {'schema_version': 1, 'claim_id': cid,
            'paper': {'title': 'Mock source', 'version': '1', 'source_file': 'literature/primary.txt',
                      'sha256': research_quality.hash_file(self.project / 'literature/primary.txt')},
            'fulltext_status': 'TECHNICALLY_CHECKED', 'author_claim': 'Fixture claim',
            'technical_statement': 'Exact fixture statement', 'source_location': 'Page 1, Theorem 1',
            'construction_mapping': 'Explicit fixture mapping', 'reduction_argument': 'A fixture derivation',
            'limitations': 'No real scientific assessment', 'coverage_verdict': 'PARTIAL_OVERLAP',
            'derivation_paths': ['literature/mapping.md'],
            'comparison': [{'dimension': dim, 'idea': 'Fixed condition', 'paper': 'Different condition',
                'relation': 'IDEA_STRONGER', 'source_location': 'Page 1', 'argument': 'Fixture comparison'}
                for dim in sorted(research_quality.DIMENSIONS)]}
        self.put('literature/technical.json', technical)
        self.put('literature/novelty.json', {'claim_id': cid,
            'claim_sha256': graph.get(self.project, cid)['spec_sha256'], 'verdict': 'NEW_THEORETICAL_CONTRIBUTION',
            'technical_reviews': ['literature/technical.json'], 'nontriviality_argument': 'Fixture test only',
            'novelty_mechanism': 'No real novelty is claimed by this fixture', 'search_scope': 'Simulated review boundary'})
        graph.review(self.project, cid, 'novelty', 'literature/novelty.json', 'independent-operator', 'Test the explicit technical review gate')

    def test_novelty_and_proof_are_distinct_and_upstream_failure_revokes_system_gate(self):
        self.claim(); self.review_proof()
        with self.assertRaises(ValueError): graph.require_theory_claim(self.project, 'C-1')
        self.novelty_review()
        self.assertTrue(graph.require_theory_claim(self.project, 'C-1')['accepted_contribution'])
        result = self.cli(['theory', 'approve', 'example', '--claim', 'C-1',
            '--contribution', 'proofs/derivation.md', '--correctness', 'research/proof-C-1.md',
            '--novelty', 'literature/novelty.json', '--reviewer', 'human-operator', '--reason', 'Explicit review fixture'])
        self.assertEqual(result, 0); theory_gate.check_readiness(self.project)
        graph.invalidate(self.project, 'C-1', 'An upstream sign error is confirmed')
        with self.assertRaises(ValueError): theory_gate.check_readiness(self.project)

    def test_changed_primary_source_revokes_novelty_without_changing_review_file(self):
        self.claim(); self.review_proof(); self.novelty_review()
        self.assertTrue(graph.status(self.project)['claims'][0]['accepted_contribution'])
        self.put('literature/primary.txt', 'A new primary paper revision')
        self.assertFalse(graph.status(self.project)['claims'][0]['accepted_contribution'])

    def test_lean_tool_success_alone_never_becomes_a_verified_theorem(self):
        self.put('proofs/lean/Check.lean', 'theorem target : True := True.intro')
        self.put('proofs/lean/lean-toolchain', 'leanprover/lean4:v4.29.1')
        self.put('proofs/lean/lake-manifest.json', {'version': '1.1.0', 'packages': []})
        self.claim(verification_mode='FORMAL_REQUIRED', formal_target={'file': 'proofs/lean/Check.lean', 'declaration': 'target'})
        def launch(argv, **kwargs):
            audit = self.project / 'proofs/lean' / argv[-1]
            self.assertIn('#print axioms target', audit.read_text())
            self.assertNotIn('--install', argv)
            kwargs['stdout'].write(b"'target' does not depend on any axioms\ntarget : True\n")
            return mock.Mock(wait=mock.Mock(return_value=0))
        with mock.patch.object(formal_verifier.shutil, 'which', return_value='/simulated/elan'), mock.patch.object(formal_verifier.subprocess, 'run', return_value=mock.Mock(returncode=0, stdout='Lean version 4.29.1', stderr='')), mock.patch.object(formal_verifier.subprocess, 'Popen', side_effect=launch):
            result = formal_verifier.run(self.project, 'C-1', 'proofs/lean/Check.lean', 'target')
        self.assertEqual(result['status'], 'TOOL_PASSED_AUDIT_PENDING')
        status = graph.status(self.project)['claims'][0]
        self.assertEqual(status['proof_status'], 'CANDIDATE'); self.assertFalse(status['accepted_contribution'])
        self.put('research/formal-audit.json', {'claim_id': 'C-1', 'receipt_sha256': object_hash(result),
            'verdict': 'MATCHED_AND_AUDITED', 'statement_mapping': 'Fixture of explicit statement matching',
            'axioms_argument': 'Fixture no new axioms', 'dependency_scope': 'Fixture target only', 'allowed_axioms': []})
        graph.review(self.project, 'C-1', 'formal_audit', 'research/formal-audit.json', 'independent-operator', 'A simulated formal-audit boundary test')
        self.assertEqual(graph.status(self.project)['claims'][0]['proof_status'], 'INDEPENDENTLY_REVIEWED')
        Path(result['output_file']).write_text('Tampered verifier log')
        self.assertEqual(graph.status(self.project)['claims'][0]['proof_status'], 'CANDIDATE')

    def test_lean_unfinished_proof_marker_rejected_before_execution(self):
        self.claim(); self.put('proofs/lean/Check.lean', 'theorem target : False := by sorry')
        self.put('proofs/lean/lean-toolchain', 'leanprover/lean4:v4.29.1')
        self.put('proofs/lean/lake-manifest.json', {'packages': []})
        with mock.patch.object(formal_verifier.shutil, 'which', return_value='/simulated/elan'), mock.patch.object(formal_verifier.subprocess, 'run') as child:
            with self.assertRaises(ValueError): formal_verifier.run(self.project, 'C-1', 'proofs/lean/Check.lean', 'target')
            child.assert_not_called()

    def test_new_candidate_is_automatically_checked_and_remains_pending_review(self):
        spec = self.claim()
        # Remove the separately imported fixture so the attempt can propose a new node.
        (self.project / 'research/discovery/CLAIM_GRAPH.json').unlink()
        scheduler.start(self.project, 'P-1'); scheduler.begin_call(self.project, 'r1')
        rel = 'research/attempts/attempt-0001/proposals/C-1.json'; self.put(rel, spec)
        checkpoint = self.checkpoint('r1', candidate_claim_files=[rel], candidate_claim_ids=['C-1'],
            evidence_paths=['proofs/derivation.md', rel])
        scheduler.finish_call(self.project, 'r1', accepted=True, checkpoint=checkpoint)
        check = scheduler.active(self.project)['calls'][0]['independent_checks'][0]
        self.assertEqual(check['counterexample_check']['status'], 'SEARCHED_NOT_FOUND')
        self.assertEqual(graph.get(self.project, 'C-1')['spec']['proposer'], 'codex:r1')
        self.assertFalse(graph.status(self.project)['claims'][0]['accepted_contribution'])

    def test_wrapper_rejection_restores_project_but_keeps_failed_attempt_charge(self):
        scheduler.start(self.project, 'P-1')
        policy, _, _ = route_budget.policy_for(self.root, self.project)
        path, data, epoch = route_budget.load_ledger(self.root, self.project, self.state)
        def launch(command):
            preflight_task = configuration.load_json(self.project / 'research/STATE.json')['next_task']
            with mock.patch.dict('os.environ', {'CRC_TRANSACTION_EXTERNAL': '1'}), mock.patch.object(runner_core.shutil, 'which', return_value='/simulated/codex'), mock.patch.object(runner_core, 'codex_run', side_effect=self.fake_codex), mock.patch.object(runner_core, 'git_checkpoint', return_value='SKIPPED_TEST'):
                code = runner_core.run_round(self.project, round_num=1, seconds=30, skip_fetch=True)
            state = configuration.load_json(self.project / 'research/STATE.json')
            state['next_task'] = preflight_task; self.put('research/STATE.json', state)
            return code
        # The inner core succeeds. The wrapper detects an unadvanced task.
        with mock.patch.object(runner, 'run_child', side_effect=launch):
            code, outcome = runner.advance_one(self.project, policy, path, data, epoch, ['simulated-core'])
        self.assertEqual(code, 3); self.assertEqual(outcome, 'NEXT_TASK_NOT_ADVANCED')
        restored = configuration.load_json(self.project / 'research/STATE.json')
        self.assertEqual(restored['last_run'], self.state['last_run'])
        item = scheduler.active(self.project)
        self.assertEqual(item['calls'][0]['status'], 'FAILED'); self.assertIsNone(item['checkpoint'])

    def test_independent_attempt_cap_cannot_be_reset_by_closing(self):
        for _ in range(3): scheduler.start(self.project, 'P-1'); scheduler.close(self.project, 'Recorded unresolved gap')
        with self.assertRaises(ValueError): scheduler.start(self.project, 'P-1')

    def test_project_discovery_override_preserves_other_config(self):
        path = self.root / 'config/projects/example.json'
        configuration.atomic_json(path, {'execution': {'max_seconds': 1337}})
        override = self.root / 'override.json'; configuration.atomic_json(override, {'initial_round_budget': 4})
        self.assertEqual(self.cli(['discovery', 'example', '--file', str(override)]), 0)
        self.assertEqual(configuration.settings_for(self.project)['execution']['max_seconds'], 1337)
        self.assertEqual(scheduler.policy(self.project)['initial_round_budget'], 4)

    def test_route_budget_stops_attempt_before_new_model_call(self):
        scheduler.start(self.project, 'P-1')
        policy, _, _ = route_budget.policy_for(self.root, self.project)
        path, data, epoch = route_budget.load_ledger(self.root, self.project, self.state)
        epoch['effective_rounds'] = policy['initial_round_budget']
        with mock.patch.object(runner, 'run_child') as child:
            code, reason = runner.advance_one(self.project, policy, path, data, epoch, ['simulated-core'])
            child.assert_not_called()
        self.assertEqual(code, 3); self.assertIn('ROUTE_REVIEW', reason)
        self.assertEqual(len(scheduler.active(self.project)['calls']), 0)

    def test_fresh_prose_alone_does_not_reset_mathematical_stagnation(self):
        scheduler.start(self.project, 'P-1')
        for number in range(1, 4):
            rid = 'r' + str(number)
            scheduler.begin_call(self.project, rid)
            self.put('proofs/derivation.md', 'Another fresh explanation without any independently checked result: ' + rid)
            checkpoint = self.checkpoint(rid)
            scheduler.finish_call(self.project, rid, accepted=True, checkpoint=checkpoint)
        item = scheduler.active(self.project)
        self.assertEqual(item['status'], 'PAUSED_STAGNATION')
        self.assertTrue(item['calls'][-1]['evaluation']['candidate_artifacts_changed'])
        self.assertFalse(item['calls'][-1]['evaluation']['scientific_acceptance'])


if __name__ == '__main__': unittest.main()
