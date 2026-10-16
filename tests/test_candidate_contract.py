"""R11 offline candidate contracts: no model, attempt or scientific promotion."""
import copy
import json
import os
import unittest
from unittest import mock

import configuration
import route_budget
import research_focus
import test_discovery as fixture
from engine import claim_graph, problem_compiler
from engine.common import object_hash
from candidate_search import catalog


class CandidateContractTests(unittest.TestCase):
    setUp = fixture.DiscoveryTests.setUp
    tearDown = fixture.DiscoveryTests.tearDown
    put = fixture.DiscoveryTests.put
    claim = fixture.DiscoveryTests.claim
    review_proof = fixture.DiscoveryTests.review_proof

    def spec(self, cid='C-0001', **updates):
        value = {'schema_version': 1, 'id': cid, 'title': 'Candidate fixture',
            'goal_anchor_id': catalog.anchor(self.project)['goal_anchor_id'],
            'problem_id': 'P-1', 'problem_version': 1,
            'hypothesis': 'Construction ' + cid + ' resolves the exact integer obligation.',
            'nontriviality_argument': 'An offline test of alternative exact constructions only.',
            'closest_prior_work': [{'source_id': 'PAPER-1', 'check': 'Check original theorem scope',
                                    'full_text_checked': False}],
            'falsification_gate': 'Find an integer violating the exact proposed construction.',
            'proof_obligations': ['O-1'], 'assumptions': self.spec_problem['assumptions'],
            'immutable_constraints': self.spec_problem['immutable_constraints'],
            'domain': 'integers', 'quantifiers': 'for all x', 'security_model': {},
            'estimated_context_bytes': 4096, 'dependency_claims': [], 'evidence_refs': [],
            'failure_scope': 'The exact quantified integer construction only.',
            'restart_conditions': 'A new independently checked construction assumption.'}
        value.update(updates)
        return value

    @property
    def spec_problem(self):
        return self.__dict__['spec']

    def make(self, cid='C-0001', **updates):
        # Discovery fixture stores its fixed problem as self.spec.
        return type(self).candidate_spec(self, cid, **updates)

    candidate_spec = spec

    def add(self, cid='C-0001', **updates):
        return catalog.propose(self.project, self.make(cid, **updates), 'Offline candidate registration')

    def files(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def test_three_candidates_share_anchor_without_science_or_budget_writes(self):
        before = self.files()
        values = [self.add('C-000' + str(i)) for i in range(1, 4)]
        self.assertEqual(len({c['id'] for c in values}), 3)
        self.assertEqual({c['status'] for c in values}, {'PROPOSED'})
        self.assertTrue(all(c['novelty_status'] == 'NOVELTY_PENDING' for c in values))
        after = self.files()
        self.assertEqual(before, {k: v for k, v in after.items()
                                  if not k.startswith(('state/candidates/', 'locks/candidates-'))})
        self.assertEqual(len(catalog.list_candidates(self.project)['candidates']), 3)

    def test_same_title_different_hypothesis_is_not_deduplicated(self):
        self.add(); self.add('C-0002')
        self.assertEqual(len(catalog.list_candidates(self.project)['candidates']), 2)

    def test_renamed_equivalent_candidate_is_rejected(self):
        first = self.add()
        spec = self.make('C-0002', hypothesis=first['spec']['hypothesis'].upper(), title='Renamed')
        with self.assertRaisesRegex(ValueError, 'DUPLICATE'):
            catalog.propose(self.project, spec, 'Renamed duplicate')

    def test_metadata_wording_cannot_create_a_duplicate_scientific_route(self):
        first = self.add()
        for field, value in [('falsification_gate', 'A differently phrased counterexample search'),
                             ('restart_conditions', 'Another retry description'),
                             ('failure_scope', 'A rewritten scope description'),
                             ('estimated_context_bytes', 42)]:
            spec = self.make('C-0002', hypothesis=first['spec']['hypothesis'], **{field: value})
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'DUPLICATE'):
                catalog.propose(self.project, spec, 'Metadata duplicate')

    def test_nan_security_dimensions_are_rejected(self):
        with self.assertRaises(ValueError): self.add(security_model={'threshold': float('nan')})

    def test_rejected_branch_is_kept_and_still_prevents_duplicate(self):
        first = self.add()
        self.disposition('C-0001', 'REFUTED')
        with self.assertRaisesRegex(ValueError, 'DUPLICATE'):
            catalog.propose(self.project, self.make('C-0002', hypothesis=first['spec']['hypothesis']), 'Retry')
        self.assertEqual(catalog.show(self.project, 'C-0001')['status'], 'REFUTED')

    def disposition(self, cid, status):
        return catalog.transition(self.project, cid, status, 'Scoped offline rejection', expected_revision=1,
            disposition={'scope': 'Only this construction', 'restart_conditions': 'A new version with evidence',
                         'evidence_refs': []})

    def test_fourth_screening_candidate_refused_and_refuted_releases_slot(self):
        for i in range(1, 5): self.add('C-000' + str(i))
        for i in range(1, 4):
            catalog.transition(self.project, 'C-000' + str(i), 'SCREENING', 'Screen', expected_revision=1)
        with self.assertRaisesRegex(ValueError, 'ACTIVE_LIMIT'):
            catalog.transition(self.project, 'C-0004', 'SCREENING', 'Screen', expected_revision=1)
        self.disposition('C-0001', 'REFUTED')
        catalog.transition(self.project, 'C-0004', 'SCREENING', 'Screen', expected_revision=1)

    def test_model_status_and_scientific_promotion_are_rejected(self):
        for status in ('READY_FOR_ATTEMPT', 'PROVED', 'INDEPENDENTLY_REVIEWED'):
            with self.subTest(status=status), self.assertRaises(ValueError): self.add(status=status)

    def test_immutable_edit_requires_explicit_revision(self):
        self.add()
        changed = self.make(security_model={'adversary': 'new trusted setting'})
        with self.assertRaises(ValueError): catalog.propose(self.project, changed, 'Replace')
        revised = catalog.propose(self.project, changed, 'Explicit assumption revision',
                                  revise=True, expected_revision=1)
        self.assertEqual(revised['revision'], 2)
        self.assertEqual(revised['status'], 'CONDITIONAL')
        self.assertEqual(catalog.show(self.project, 'C-0001', revision=1)['spec']['security_model'], {})
        with self.assertRaisesRegex(ValueError, 'CONDITIONAL'):
            catalog.transition(self.project, 'C-0001', 'READY_FOR_ATTEMPT', 'Approve', expected_revision=2)

    def test_reduced_corruption_threshold_cannot_disguise_same_goal(self):
        self.spec['security_model'] = {'corruption_threshold': 3, 'adversary': 'malicious'}
        problem_compiler.import_problem(self.project, self.spec, 'Pinned security model fixture')
        with self.assertRaisesRegex(ValueError, 'corruption'):
            self.add(problem_version=2, security_model={'corruption_threshold': 2, 'adversary': 'malicious'})

    def test_missing_baseline_assumptions_or_changed_quantifiers_rejected(self):
        for updates in ({'assumptions': []}, {'immutable_constraints': []}, {'quantifiers': 'exists x'},
                        {'domain': 'positive integers'}):
            with self.subTest(updates=updates), self.assertRaises(ValueError): self.add(**updates)

    def test_goal_binding_and_falsification_required(self):
        for updates in ({'goal_anchor_id': '0' * 64}, {'falsification_gate': ''}, {'proof_obligations': []}):
            with self.subTest(updates=updates), self.assertRaises(ValueError): self.add(**updates)

    def test_invalid_id_cross_project_problem_and_parent_cycle_rejected(self):
        for updates in ({'id': '../other'}, {'problem_id': 'other/P-1'}, {'problem_id': 'P-unknown'},
                        {'parent': {'id': 'C-0001', 'revision': 1}}):
            with self.subTest(updates=updates), self.assertRaises(ValueError): self.add(**updates)
        self.add(); self.add('C-0002', parent={'id': 'C-0001', 'revision': 1})
        with self.assertRaisesRegex(ValueError, 'cyclic'):
            catalog.propose(self.project, self.make(parent={'id': 'C-0002', 'revision': 1}), 'Cycle',
                            revise=True, expected_revision=1)

    def test_refuted_parent_does_not_revoke_independent_sibling(self):
        self.add(); self.add('C-0002')
        self.disposition('C-0001', 'REFUTED')
        self.assertEqual(catalog.show(self.project, 'C-0002')['status'], 'PROPOSED')

    def test_stale_revision_compare_and_swap_refused(self):
        self.add()
        with self.assertRaisesRegex(ValueError, 'revision'):
            catalog.transition(self.project, 'C-0001', 'SCREENING', 'Stale', expected_revision=2)

    def test_unverified_theorem_blocks_ready_without_model_receipt_override(self):
        self.claim('LEMMA-1')
        item = claim_graph.get(self.project, 'LEMMA-1')
        self.add(dependency_claims=[{'id': item['id'], 'revision': item['revision'],
                                    'spec_sha256': item['spec_sha256']}])
        with self.assertRaisesRegex(ValueError, 'INDEPENDENT'):
            catalog.transition(self.project, 'C-0001', 'READY_FOR_ATTEMPT', 'Model says true', expected_revision=1)

    def test_independent_fresh_statement_and_proof_allow_ready_but_not_proved(self):
        self.claim('LEMMA-1'); self.review_proof('LEMMA-1')
        item = claim_graph.get(self.project, 'LEMMA-1')
        self.add(dependency_claims=[{'id': item['id'], 'revision': item['revision'],
                                    'spec_sha256': item['spec_sha256']}])
        value = catalog.transition(self.project, 'C-0001', 'READY_FOR_ATTEMPT', 'Reviewed dependency', expected_revision=1)
        self.assertEqual(value['status'], 'READY_FOR_ATTEMPT')
        self.assertEqual(value['novelty_status'], 'NOVELTY_PENDING')
        self.put('proofs/derivation.md', 'Changed after independent review')
        shown = catalog.show(self.project, 'C-0001')
        self.assertFalse(shown['eligible_for_attempt'])

    def test_manual_active_transition_is_forbidden(self):
        self.add()
        with self.assertRaisesRegex(ValueError, 'attempt'):
            catalog.transition(self.project, 'C-0001', 'ACTIVE', 'No owner', expected_revision=1)

    def test_fixed_problem_sha_and_goal_changes_are_live_stale(self):
        self.add(); self.put('GOAL.md', 'A changed operator target')
        self.assertFalse(catalog.show(self.project, 'C-0001')['eligible_for_attempt'])
        with self.assertRaises(ValueError):
            catalog.transition(self.project, 'C-0001', 'SCREENING', 'Wrong goal', expected_revision=1)

    def test_catalog_tampering_or_missing_event_rejected_without_repair(self):
        self.add(); path = catalog.path(self.project)
        value = json.loads(path.read_text(encoding='utf8')); original = path.read_bytes()
        value['candidates'][0]['revisions'][0]['spec']['hypothesis'] = 'Altered'
        configuration.atomic_json(path, value)
        with self.assertRaises(ValueError): catalog.list_candidates(self.project)
        path.write_bytes(original); value = json.loads(original); value['events'].pop()
        configuration.atomic_json(path, value)
        with self.assertRaises(ValueError): catalog.list_candidates(self.project)

    def test_atomic_write_failure_leaves_old_catalog(self):
        self.add(); path = catalog.path(self.project); old = path.read_bytes()
        with mock.patch('configuration.os.replace', side_effect=OSError('injected atomic failure')):
            with self.assertRaises(OSError): self.add('C-0002')
        self.assertEqual(path.read_bytes(), old)
        self.assertEqual(len(catalog.list_candidates(self.project)['candidates']), 1)

    def test_reads_are_side_effect_free_and_do_not_call_models(self):
        self.add(); before = self.files()
        with mock.patch('subprocess.Popen', side_effect=AssertionError('No process')):
            catalog.list_candidates(self.project); catalog.show(self.project, 'C-0001')
        self.assertEqual(before, self.files())

    def test_draft_snapshot_is_pinned_without_problem_import(self):
        proposal = copy.deepcopy(self.spec); proposal['id'] = 'P-DRAFT'
        self.put('research/candidates/draft.json', proposal)
        value = self.make(); value.pop('problem_id'); value.pop('problem_version')
        value['problem_proposal_file'] = 'research/candidates/draft.json'
        record = catalog.propose(self.project, value, 'Draft only')
        self.assertEqual(record['problem_binding']['status'], 'DRAFT_PENDING')
        self.assertEqual(len(problem_compiler.pool(self.project)['problems']), 1)
        self.put('research/candidates/draft.json', 'Destroyed after pin')
        self.assertEqual(catalog.show(self.project, 'C-0001')['problem_binding']['spec'], proposal)
        with self.assertRaisesRegex(ValueError, 'fixed problem'):
            catalog.transition(self.project, 'C-0001', 'READY_FOR_ATTEMPT', 'Draft not import', expected_revision=1)

    def test_policy_cannot_raise_hard_active_limit(self):
        (self.root / 'config/candidate_policy.json').write_text(json.dumps(
            {'schema_version': 1, 'max_active_candidates': 4}), encoding='utf8')
        with self.assertRaises(ValueError): self.add()

    def register_route(self):
        state = configuration.load_json(self.project / 'research/STATE.json')
        path, ledger, epoch = route_budget.load_ledger(self.root, self.project, state)
        route_budget.save_ledger(path, ledger)
        return path, ledger

    def test_missing_registered_budget_stops_without_zero_enrollment(self):
        path, ledger = self.register_route()
        path.unlink(); before = self.files()
        with self.assertRaisesRegex(ValueError, 'missing'): self.add()
        self.assertFalse(path.exists())
        self.assertEqual(before, {k: v for k, v in self.files().items()
                                  if not k.startswith('locks/candidates-')})

    def test_candidate_does_not_register_legacy_route_or_spend_budget(self):
        path, ledger = self.register_route(); before = path.read_bytes()
        self.add(); self.assertEqual(path.read_bytes(), before)
        catalog.transition(self.project, 'C-0001', 'SCREENING', 'Offline screen', expected_revision=1)
        self.assertEqual(path.read_bytes(), before)

    def test_route_switch_cannot_be_silently_refocused(self):
        self.register_route()
        state = copy.deepcopy(self.state); state['research_route'] = 'OTHER'
        self.put('research/STATE.json', state)
        with self.assertRaisesRegex(ValueError, 'refocus'): self.add()

    def test_forged_legacy_focus_is_not_a_valid_anchor(self):
        path, ledger = self.register_route()
        route_budget.registry_path(path).unlink()
        ledger.pop('budget_registration_id', None)
        ledger['epochs'][-1]['focus']['anchor_id'] = '0' * 64
        configuration.atomic_json(path, ledger)
        with self.assertRaisesRegex(ValueError, 'focus integrity'): catalog.anchor(self.project)

    def test_symlink_evidence_draft_and_store_rejected(self):
        source = self.put('proofs/real.md', 'Bound candidate evidence')
        link = self.project / 'proofs/linked.md'
        try: os.symlink(source, link)
        except (OSError, NotImplementedError): self.skipTest('Creating symlink not permitted on this host')
        with self.assertRaises(ValueError): self.add(evidence_refs=['proofs/linked.md'])

    def test_metadata_revision_keeps_rejected_old_version(self):
        self.add(); self.disposition('C-0001', 'COVERED')
        revised = catalog.propose(self.project, self.make(restart_conditions='New independently checked case'),
            'New scoped input', revise=True, expected_revision=1)
        self.assertEqual(revised['revision'], 2)
        self.assertEqual(catalog.show(self.project, 'C-0001', revision=1)['status'], 'COVERED')

    def test_identical_scientific_problem_renamed_cannot_bypass_duplicate(self):
        first = self.add()
        other = copy.deepcopy(self.spec); other['id'] = 'P-RENAMED'; other['title'] = 'Another title'
        problem_compiler.import_problem(self.project, other, 'Renamed problem fixture')
        with self.assertRaisesRegex(ValueError, 'DUPLICATE'):
            self.add('C-0002', hypothesis=first['spec']['hypothesis'], problem_id='P-RENAMED')

    def test_consistently_rehashed_manual_active_event_still_rejected(self):
        self.add()
        catalog.transition(self.project, 'C-0001', 'SCREENING', 'Screen', expected_revision=1)
        path = catalog.path(self.project); value = json.loads(path.read_text(encoding='utf8'))
        value['events'][-1]['record']['status'] = 'ACTIVE'
        value['events'][-1]['sha256'] = object_hash({k: v for k, v in value['events'][-1].items() if k != 'sha256'})
        value['candidates'][0]['revisions'][0]['status'] = 'ACTIVE'
        configuration.atomic_json(path, value)
        with self.assertRaisesRegex(ValueError, 'attempt-owner'): catalog.list_candidates(self.project)

    def test_consistently_rehashed_unscoped_rejection_event_still_rejected(self):
        self.add(); self.disposition('C-0001', 'REFUTED')
        path = catalog.path(self.project); value = json.loads(path.read_text(encoding='utf8'))
        value['events'][-1]['record'].pop('disposition')
        value['events'][-1]['sha256'] = object_hash({k: v for k, v in value['events'][-1].items() if k != 'sha256'})
        value['candidates'][0]['revisions'][0].pop('disposition')
        configuration.atomic_json(path, value)
        with self.assertRaisesRegex(ValueError, 'scoped disposition'): catalog.list_candidates(self.project)
