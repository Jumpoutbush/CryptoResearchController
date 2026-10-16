"""Offline v3.3 contract and proposal-package regressions.

Fake executor outputs exercise controller enforcement; these tests do not measure
a live model's ability to recognise mathematical relevance or certify a proof.
"""
import json
import unittest
from pathlib import Path
from unittest import mock

import supervision
import route_budget
import research_quality
import test_supervision as fixtures


PACKAGE_FILES = {'verdict.json', 'guide.patch', 'evidence_map.json',
                 'manifest.json', 'guidance.md'}


class SupervisionV33Tests(unittest.TestCase):
    # Reuse helpers without inheriting (and rerunning) every v3.2 test.
    setUp = fixtures.SupervisionTests.setUp
    put = fixtures.SupervisionTests.put
    read = fixtures.SupervisionTests.read
    digest = staticmethod(fixtures.SupervisionTests.digest)
    enable = fixtures.SupervisionTests.enable
    rounds = fixtures.SupervisionTests.rounds
    unchanged = fixtures.SupervisionTests.unchanged
    assert_unchanged = fixtures.SupervisionTests.assert_unchanged
    supervise = fixtures.SupervisionTests.supervise

    def proposal(self, controller, project, review_dir, prompt, policy):
        inputs = json.loads((review_dir / 'input.json').read_text(encoding='utf-8-sig'))
        objective = 'Search for a minimal malicious trace violating the exact authorization invariant.'
        return {
            'schema_version': 2, 'review_id': inputs['review_id'],
            'goal_sha256': inputs['goal_sha256'], 'snapshot_sha256': inputs['snapshot_sha256'],
            'verdict': {
                'decision': 'REFOCUS', 'core_goal_changed': False,
                'main_obligation': 'PROOF:O-1', 'evidence_verified': False,
                'reason': 'The unresolved exact authorization obligation needs a decisive adversarial witness before more auxiliary work.',
                'next_action': objective, 'requires_human_approval': False},
            'next_task': {
                'anchor_id': inputs['focus']['anchor_id'], 'target_obligation': 'PROOF:O-1',
                'objective': objective,
                'steps': ['Write the quantified authorization condition with the frozen adversary.',
                          'Search the smallest execution trace for an exact violating witness.'],
                'falsification': 'One admissible malicious trace with an unauthorized accepted output falsifies this candidate.',
                'expected_evidence': ['An exact reproducible malicious trace or a documented bounded negative search.']},
            'evidence': [{'path': 'proofs/current.md', 'sha256': self.digest(project / 'proofs/current.md'),
                          'reason': 'The current proof explicitly leaves the authorization invariant unresolved.'}],
            'agents_guidance': '', 'method_change_reason': ''}

    def ready(self):
        self.enable()
        self.rounds(3)

    def packages(self):
        home = self.root / 'state/supervision/example/reviews'
        return sorted(path.parent for path in home.glob('*/attempt-*/proposal/manifest.json'))

    def guides(self):
        return {rel: (self.project / rel).read_bytes() for rel in ('AGENTS.md', 'prompts/continue.md')}

    def classify_accepted_rounds(self, scope, mainline_progress):
        paths = []
        for index, event in enumerate(self.ledger['events']):
            if event.get('type') != 'RESEARCH_ROUND':
                continue
            relative = 'proofs/accepted-lemma-' + str(index) + '.md'
            self.put(relative, f'Accepted round {event["run_id"]}: exact auxiliary lemma with independent witness {index}.\n')
            paths.append(relative)
            event.update(anchor_id=self.epoch['focus']['anchor_id'],
                         goal_alignment={'scope': scope, 'mainline_progress': mainline_progress},
                         evidence_hashes={relative: self.digest(self.project / relative)})
            if scope == 'DIRECT_DEPENDENCY':
                event['goal_alignment'].update(
                    consumer_claim='The exact authorization invariant.',
                    dependency_argument='The core invariant invokes this quantified transition directly.')
        route_budget.save_ledger(self.route_path, self.ledger)
        return paths

    def rejected(self, mutate):
        self.ready()
        science, guides = self.unchanged(), self.guides()

        def invalid(*args):
            proposal = self.proposal(*args)
            mutate(proposal)
            return proposal

        result, execute = self.supervise(invalid)
        execute.assert_called_once()
        self.assertEqual(result['status'], 'failed', result)
        self.assertFalse(result['proceed'])
        self.assertEqual(self.guides(), guides)
        self.assert_unchanged(science)

    def test_executor_schema_requires_the_v33_structured_verdict(self):
        schema = supervision._schema()
        self.assertEqual(schema['properties']['schema_version']['enum'], [2])
        self.assertEqual(set(schema['required']), {
            'schema_version', 'review_id', 'goal_sha256', 'snapshot_sha256', 'verdict',
            'next_task', 'evidence', 'agents_guidance', 'method_change_reason'})
        verdict = schema['properties']['verdict']
        self.assertFalse(verdict['additionalProperties'])
        self.assertEqual(set(verdict['required']), {
            'decision', 'core_goal_changed', 'main_obligation', 'evidence_verified',
            'reason', 'next_action', 'requires_human_approval'})

    def test_actual_executor_rejects_legacy_or_malformed_wire_versions(self):
        directory = self.root / 'state/mock version downgrade'
        directory.mkdir(parents=True)
        policy = supervision.policy_for(self.root, self.project)
        process = mock.Mock(returncode=0)
        for payload in ({'schema_version': 1}, {'schema_version': 2.0},
                        {'simulated': True}, []):
            with self.subTest(output=payload):
                def launch(command, **kwargs):
                    (directory / 'output.json').write_text(json.dumps(payload), encoding='utf-8')
                    return process

                with mock.patch.object(supervision.shutil, 'which', return_value='fake-offline-codex'), \
                     mock.patch.object(supervision.subprocess, 'Popen', side_effect=launch), \
                     self.assertRaises(ValueError):
                    supervision._execute(self.root, self.project, directory,
                                         'Offline schema boundary regression.', policy)

    def test_short_term_refocus_keeps_agents_and_preserves_science(self):
        self.ready()
        science, agents = self.unchanged(), (self.project / 'AGENTS.md').read_bytes()
        result, execute = self.supervise()
        execute.assert_called_once()
        self.assertEqual(result['status'], 'applied', result)
        self.assertTrue(result['proceed'])
        self.assertEqual((self.project / 'AGENTS.md').read_bytes(), agents)
        self.assertIn('minimal malicious trace', (self.project / 'prompts/continue.md').read_text(encoding='utf-8'))
        self.assert_unchanged(science)

    def test_short_term_schedule_does_not_write_the_agents_file(self):
        self.ready()
        agents = (self.project / 'AGENTS.md').read_bytes()
        original_write = supervision._write
        writes = []

        def track_write(path, content):
            writes.append(Path(path))
            return original_write(path, content)

        with mock.patch.object(supervision, '_write', side_effect=track_write):
            result, _ = self.supervise()
        self.assertEqual(result['status'], 'applied', result)
        self.assertIn(self.project / 'prompts/continue.md', writes)
        self.assertNotIn(self.project / 'AGENTS.md', writes)
        self.assertEqual((self.project / 'AGENTS.md').read_bytes(), agents)

    def test_justified_long_term_method_change_uses_only_managed_region(self):
        self.ready()
        agents = (self.project / 'AGENTS.md').read_bytes()

        def method_change(*args):
            proposal = self.proposal(*args)
            proposal['agents_guidance'] = 'Require each auxiliary lemma to name the unchanged core construction claim that consumes it.'
            proposal['method_change_reason'] = 'Repeated unused supporting lemmas justify a persistent dependency check across future research rounds.'
            return proposal

        result, _ = self.supervise(method_change)
        self.assertEqual(result['status'], 'applied', result)
        applied = (self.project / 'AGENTS.md').read_bytes()
        self.assertTrue(applied.startswith(agents))
        self.assertIn(b'unchanged core construction claim', applied)

    def test_proposal_package_is_persisted_before_any_guide_is_changed(self):
        self.ready()
        science, guides = self.unchanged(), self.guides()
        original_write = supervision._write
        observed = []

        def observe(path, content):
            if Path(path) in {self.project / rel for rel in guides} and not observed:
                packages = self.packages()
                self.assertEqual(len(packages), 1)
                self.assertTrue(PACKAGE_FILES.issubset({p.name for p in packages[0].iterdir()}))
                self.assertEqual(self.guides(), guides)
                for name in PACKAGE_FILES:
                    self.assertGreater((packages[0] / name).stat().st_size, 0)
                observed.append(packages[0])
            return original_write(path, content)

        with mock.patch.object(supervision, '_write', side_effect=observe):
            result, _ = self.supervise()
        self.assertEqual(result['status'], 'applied', result)
        self.assertEqual(len(observed), 1)
        self.assert_unchanged(science)
        archive = self.project / 'research/supervision' / result['review_id']
        for name in PACKAGE_FILES:
            self.assertEqual((archive / name).read_bytes(), (observed[0] / name).read_bytes(), name)
        verdict = json.loads((archive / 'verdict.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(verdict['decision'], 'REFOCUS')
        self.assertIs(verdict['evidence_verified'], False)

    def test_tampered_pending_patch_is_rejected_before_guide_commit(self):
        self.ready()
        science, guides = self.unchanged(), self.guides()
        original_apply = supervision._apply
        tampered = []

        def alter_then_apply(*args, **kwargs):
            packages = self.packages()
            self.assertEqual(len(packages), 1)
            patch = packages[0] / 'guide.patch'
            patch.write_bytes(patch.read_bytes() + b'\nforged post-validation instructions\n')
            tampered.append(patch)
            return original_apply(*args, **kwargs)

        with mock.patch.object(supervision, '_apply', side_effect=alter_then_apply):
            result, _ = self.supervise()
        self.assertEqual(len(tampered), 1)
        self.assertEqual(result['status'], 'failed', result)
        self.assertFalse(result['proceed'])
        self.assertEqual(self.guides(), guides)
        self.assert_unchanged(science)

    def test_prepared_proposal_rejects_external_state_or_route_edit(self):
        self.ready()
        science, guides = self.unchanged(), self.guides()
        original_apply = supervision._apply
        for label, target, key in (
                ('state', self.project / 'research/STATE.json', 'research/STATE.json'),
                ('route', self.route_path, 'route-ledger')):
            with self.subTest(edited_file=label):
                before = target.read_bytes()
                if label == 'state':
                    state = json.loads(before.decode('utf-8-sig'))
                    state['next_task'] = 'A human supplied a newer scheduling instruction after proposal preparation.'
                    edited = json.dumps(state, ensure_ascii=False).encode('utf-8')
                else:
                    # A byte-level disk edit must invalidate the exact route
                    # version even if the JSON's mathematical contents agree.
                    edited = before + b'\n'
                observed = []

                def edit_then_apply(*args, **kwargs):
                    self.assertTrue(self.packages())
                    target.write_bytes(edited)
                    observed.append(target)
                    return original_apply(*args, **kwargs)

                with mock.patch.object(supervision, '_apply', side_effect=edit_then_apply):
                    result, _ = self.supervise()
                self.assertEqual(observed, [target])
                self.assertEqual(result['status'], 'failed', result)
                self.assertFalse(result['proceed'])
                self.assertEqual(target.read_bytes(), edited)
                self.assertEqual(self.guides(), guides)
                expected = {**science, key: edited}
                self.assertEqual(self.unchanged(), expected)
                packages = self.packages()
                self.assertEqual(len(packages), 1 if label == 'state' else 2)
                for package in packages:
                    self.assertTrue(PACKAGE_FILES.issubset({path.name for path in package.iterdir()}))
                    self.assertTrue((package.parent / 'failure.json').is_file())
                # Reset only this deliberate fixture edit before replaying the
                # second conflict. The supervisor itself never restores it.
                target.write_bytes(before)

    def test_failed_application_keeps_pending_package_for_audit(self):
        self.ready()
        science, guides = self.unchanged(), self.guides()
        with mock.patch.object(supervision, '_commit', side_effect=OSError('Simulated offline disk failure')):
            result, _ = self.supervise()
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(self.guides(), guides)
        self.assert_unchanged(science)
        packages = self.packages()
        self.assertEqual(len(packages), 1)
        self.assertTrue(PACKAGE_FILES.issubset({p.name for p in packages[0].iterdir()}))
        self.assertTrue((packages[0].parent / 'failure.json').is_file())

    def test_tampered_versioned_guidance_blocks_next_prompt(self):
        self.ready()
        result, _ = self.supervise()
        self.assertEqual(result['status'], 'applied', result)
        guide = self.project / 'research/supervision' / result['review_id'] / 'guidance.md'
        self.assertTrue(guide.is_file())
        guide.write_bytes(guide.read_bytes() + b'\nForged later instruction.\n')
        with self.assertRaises(ValueError):
            supervision.prompt_context(self.root, self.project)

    def test_human_approval_pause_stops_next_call_without_rewriting_state(self):
        self.ready()
        science = self.unchanged()

        def pause(*args):
            proposal = self.proposal(*args)
            proposal['verdict'].update(decision='PAUSE', requires_human_approval=True)
            return proposal

        result, _ = self.supervise(pause)
        self.assertEqual(result['status'], 'applied', result)
        self.assertFalse(result['proceed'])
        second, execute = self.supervise()
        execute.assert_not_called()
        self.assertFalse(second['proceed'])
        self.assert_unchanged(science)

    def test_known_quality_findings_cannot_be_dismissed_with_continue(self):
        self.ready()
        science, guides = self.unchanged(), self.guides()

        def attempt_continue(controller, project, review_dir, prompt, policy):
            proposal = self.proposal(controller, project, review_dir, prompt, policy)
            proposal['verdict']['decision'] = 'CONTINUE'
            request = json.loads((review_dir / 'input.json').read_text(encoding='utf-8-sig'))
            for code in ('SUPPORT_DRIFT', 'REPEATED_EVIDENCE', 'CORE_OBLIGATION_STALLED'):
                with self.subTest(finding=code):
                    request['quality_assessment'] = {'findings': [{'code': code}]}
                    with self.assertRaises(ValueError):
                        supervision._validate(proposal, request, project)
            # The production call also receives a valid bounded refocus after
            # each negative verdict check, without mutating its source request.
            proposal['verdict']['decision'] = 'REFOCUS'
            return proposal

        result, _ = self.supervise(attempt_continue)
        self.assertEqual(result['status'], 'applied', result)
        self.assertEqual((self.project / 'AGENTS.md').read_bytes(), guides['AGENTS.md'])
        self.assert_unchanged(science)

    def test_three_support_receipts_require_refocus_and_preserve_budget_and_evidence(self):
        self.ready()
        evidence_paths = self.classify_accepted_rounds('SUPPORT', False)
        evidence = {path: (self.project / path).read_bytes() for path in evidence_paths}
        science, guides = self.unchanged(), self.guides()
        assessments = []

        def review(decision):
            def execute(controller, project, review_dir, prompt, policy):
                request = json.loads((review_dir / 'input.json').read_text(encoding='utf-8-sig'))
                assessments.append(request['quality_assessment'])
                proposal = self.proposal(controller, project, review_dir, prompt, policy)
                proposal['verdict'].update(
                    decision=decision,
                    reason='Three accepted rounds study auxiliary lemmas without an explicit consumer in the frozen core construction; return to its unresolved security obligation.')
                proposal['evidence'] = [
                    {'path': path, 'sha256': self.digest(project / path),
                     'reason': 'This accepted supporting lemma has no recorded mainline progress or core consumer.'}
                    for path in evidence_paths]
                return proposal
            return execute

        rejected, _ = self.supervise(review('CONTINUE'))
        self.assertEqual(rejected['status'], 'failed', rejected)
        self.assertFalse(rejected['proceed'])
        self.assertEqual(self.guides(), guides)
        self.assert_unchanged(science)
        applied, _ = self.supervise(review('REFOCUS'))
        self.assertEqual(applied['status'], 'applied', applied)
        self.assertTrue(applied['proceed'])
        self.assertEqual(len(assessments), 2)
        for assessment in assessments:
            self.assertEqual(assessment['assessment'], 'DRIFT')
            codes = {finding['code'] for finding in assessment['findings']}
            self.assertTrue({'SUPPORT_DRIFT', 'CORE_OBLIGATION_STALLED'} <= codes)
        self.assertEqual({path: (self.project / path).read_bytes() for path in evidence_paths}, evidence)
        self.assertEqual((self.project / 'AGENTS.md').read_bytes(), guides['AGENTS.md'])
        self.assertIn('minimal malicious trace', (self.project / 'prompts/continue.md').read_text(encoding='utf-8'))
        self.assertEqual(supervision.status(self.root, self.project, self.ledger)['attempts_used'], 2)
        self.assert_unchanged(science)

    def test_fresh_direct_dependency_receipts_allow_bounded_continue(self):
        self.ready()
        self.classify_accepted_rounds('DIRECT_DEPENDENCY', True)
        science = self.unchanged()

        def continue_dependency(controller, project, review_dir, prompt, policy):
            request = json.loads((review_dir / 'input.json').read_text(encoding='utf-8-sig'))
            self.assertEqual(request['quality_assessment']['assessment'], 'ON_TRACK')
            self.assertEqual(request['quality_assessment']['findings'], [])
            proposal = self.proposal(controller, project, review_dir, prompt, policy)
            proposal['verdict'].update(
                decision='CONTINUE',
                reason='The recent exact lemmas have distinct historical evidence and are direct dependencies consumed by the unchanged core authorization invariant.')
            return proposal

        result, execute = self.supervise(continue_dependency)
        execute.assert_called_once()
        self.assertEqual(result['status'], 'applied', result)
        self.assertTrue(result['proceed'])
        self.assert_unchanged(science)

    def test_supervision_outputs_cannot_count_as_scientific_progress(self):
        excluded = ('research/SUPERVISION_REPORT.md',
                    'research/supervision/review-fixture/REPORT.md',
                    'research/SuPeRvIsIoN/review-fixture/verdict.json')
        for relative in excluded:
            self.put(relative, 'Supervision schedules a new task; this is no mathematical result.\n')
        review_snapshot = supervision._snapshot(self.project, self.ledger)
        for relative in excluded:
            self.assertNotIn(relative, review_snapshot['hashes'])
            self.assertNotIn(relative, review_snapshot['evidence'])
            with self.subTest(path=relative):
                self.assertIsNone(route_budget.evidence_path(self.project, relative))
                with self.assertRaises(ValueError):
                    research_quality.scientific_files(self.project, [relative])
        snapshot = route_budget.evidence_snapshot(self.project)
        folded = {path.casefold() for path in snapshot}
        self.assertTrue(all(path.casefold() not in folded for path in excluded))
        self.assertIn('proofs/current.md', snapshot)
        self.assertIsNotNone(route_budget.evidence_path(self.project, 'proofs/current.md'))
        self.assertEqual(len(research_quality.scientific_files(self.project, ['proofs/current.md'])), 1)

    def test_state_is_available_for_review_but_cannot_be_scientific_progress(self):
        self.ready()
        science = self.unchanged()
        relative = 'research/STATE.json'
        self.assertIsNone(route_budget.evidence_path(self.project, relative))
        self.assertNotIn(relative, route_budget.evidence_snapshot(self.project))
        with self.assertRaises(ValueError):
            research_quality.scientific_files(self.project, [relative])

        def review_state(controller, project, review_dir, prompt, policy):
            request = json.loads((review_dir / 'input.json').read_text(encoding='utf-8-sig'))
            self.assertEqual(request['evidence'][relative], self.digest(project / relative))
            proposal = self.proposal(controller, project, review_dir, prompt, policy)
            proposal['evidence'] = [{'path': relative, 'sha256': request['evidence'][relative],
                                     'reason': 'Scheduling context records the unchanged open core obligation; it does not certify a scientific result.'}]
            return proposal

        result, execute = self.supervise(review_state)
        execute.assert_called_once()
        self.assertEqual(result['status'], 'applied', result)
        self.assert_unchanged(science)


def rejection_test(mutate):
    def test(self):
        self.rejected(mutate)
    return test


for name, mutate in {
    'non_integer_wire_schema_version': lambda p: p.update(schema_version=2.0),
    'unreviewed_proof_certification': lambda p: p['verdict'].update(evidence_verified=True),
    'relaxed_frozen_goal': lambda p: p['verdict'].update(core_goal_changed=True),
    'approval_with_continue': lambda p: p['verdict'].update(decision='CONTINUE', requires_human_approval=True),
    'approval_with_refocus': lambda p: p['verdict'].update(requires_human_approval=True),
    'unknown_main_obligation': lambda p: p['verdict'].update(main_obligation='PROOF:MISSING'),
    'different_main_obligation': lambda p: p['verdict'].update(main_obligation='GOAL'),
    'conflicting_next_action': lambda p: p['verdict'].update(next_action='Work on an unrelated unused auxiliary lemma.'),
    'short_verdict_reason': lambda p: p['verdict'].update(reason='Fine'),
    'non_boolean_core_goal_changed': lambda p: p['verdict'].update(core_goal_changed=0),
    'non_boolean_evidence_verified': lambda p: p['verdict'].update(evidence_verified=0),
    'extra_verdict_state_edit': lambda p: p['verdict'].update(state={'decision': 'CONTINUE'}),
    'unjustified_long_term_change': lambda p: p.update(agents_guidance='Replace the standing methods with a new research discipline.'),
    'short_long_term_reason': lambda p: p.update(agents_guidance='Require direct dependencies.', method_change_reason='Better'),
    'unused_method_change_reason': lambda p: p.update(method_change_reason='This long-term rationale has no actual long-term method change attached.'),
}.items():
    setattr(SupervisionV33Tests, 'test_rejects_' + name, rejection_test(mutate))


if __name__ == '__main__':
    unittest.main()
