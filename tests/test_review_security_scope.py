"""N02/T04: exact adaptive corruption scope is required for advisory review."""
import copy
import unittest
from unittest import mock

import test_candidate_contract as fixture
from candidate_search import catalog, security_model, security_review
from engine import problem_compiler
from engine.common import object_hash


MISSING = object()


class ReviewSecurityScopeTests(unittest.TestCase):
    setUp = fixture.CandidateContractTests.setUp
    tearDown = fixture.CandidateContractTests.tearDown
    put = fixture.CandidateContractTests.put
    claim = fixture.CandidateContractTests.claim
    files = fixture.CandidateContractTests.files
    candidate_spec = fixture.CandidateContractTests.candidate_spec
    make = fixture.CandidateContractTests.make
    spec_problem = fixture.CandidateContractTests.spec_problem
    add = fixture.CandidateContractTests.add

    def complete_card(self):
        card = security_model.template()
        card['proof_paths'] = ['proofs/derivation.md']
        card['security_game'].update(
            definition='Two-round adaptive-corruption fixture; the corruption budget scope is separately frozen in the fixed model.',
            rounds=2, public_outputs=['transcript'])
        card['parties'] = ['client', 'server', 'auditor']
        card['corruption_model'].update(
            timing='ADAPTIVE', claimed_timing='ADAPTIVE', threshold=1,
            claimed_threshold=1, corrupted_parties=['server'], dropout_model='NONE')
        card['leakage_function'].update(
            name='L-two-rounds', real_observable=['transcript'],
            ideal_leakage=['transcript'], cross_round_linkage='DEFINED')
        card['setup_assumptions'] = copy.deepcopy(self.spec['assumptions'])
        card['abort_behavior'] = {key: False for key in card['abort_behavior']}
        card['simulator_interface'].update(
            ideal_inputs=['public_transcript'], required_inputs=['public_transcript'],
            output_dependencies={'transcript': ['public_transcript']})
        card['reduction_loss'].update(
            parameters=['n', 'rounds'], bit_widths={'n': 32, 'rounds': 2}, rounds=2,
            failure_events=['simulation_abort'],
            loss_bound='A declared two-round union bound, requiring independent proof review.')
        card['composition_scope'].update(
            sessions=1, rounds=2,
            cross_round_collusion='Adaptive corruptions share the same declared two-round public transcript.',
            end_to_end_reduction='Explicit pending two-round simulation proof, not a component-security assertion.')
        for row in card['baseline_comparison']:
            row.update(assumptions='Exact frozen setup; independent source comparison pending.',
                       functionality='The complete two-round public transcript.', cost='UNASSESSED',
                       difference='No novelty or security assertion follows from this fixture.')
        card['attack_traces'] = [{
            'id': 'A-two-rounds', 'kind': 'CORRUPTION_THRESHOLD',
            'game': 'GAME-main', 'proof_step': 'two-round-corruption-accounting',
            'affected_obligations': ['O-1'],
            'execution': [self.trace_step(1, 'server'), self.trace_step(2, 'auditor')],
            'scope': 'Only these fixed primitive two-round data; no protocol attack is executed.',
            'restart_conditions': 'New independently checked evidence within the unchanged frozen model.'}]
        return card

    def trace_step(self, round_number, party):
        return {'round': round_number, 'corrupted_parties': [party],
                'public_inputs': {'query': 'fixed-public-query'},
                'secret_assignment': {'secret': 0},
                'ideal_leakage': {'transcript': 'fixed-public-transcript'},
                'public_output': {'transcript': 'fixed-public-transcript'}}

    def prepare(self, frozen_scope, candidate_scope):
        card = self.complete_card()
        frozen = {'corruption_timing': 'ADAPTIVE', 'corruption_threshold': 1,
                  'leakage_function': 'L-two-rounds', 'party_count': 3,
                  'ideal_interface_sha256': object_hash(security_model.ideal_interface_binding(card))}
        if frozen_scope is not MISSING:
            frozen['corruption_budget_scope'] = frozen_scope
        candidate = copy.deepcopy(frozen)
        if candidate_scope is MISSING:
            candidate.pop('corruption_budget_scope', None)
        else:
            candidate['corruption_budget_scope'] = candidate_scope
        self.spec['security_model'] = frozen
        problem_compiler.import_problem(self.project, self.spec, 'Freeze complete two-round adaptive model')
        self.add(problem_version=2, security_model=candidate)
        self.claim('CLAIM-1', problem_version=2)
        # This is the original interface schema, deliberately unchanged by N02.
        self.assertNotIn('corruption_budget_scope', security_model.ideal_interface_binding(card)['corruption_scope'])
        return security_model.prepare_request(self.project, 'C-0001', 'CLAIM-1', card)

    def review(self, request):
        before = self.files()
        with mock.patch('subprocess.Popen', side_effect=AssertionError('No model, Lean or attack execution')):
            report = security_review.review(self.project, request)
        permitted = ('state/candidates/example/security_review/', 'locks/')
        protected = lambda files: {path: value for path, value in files.items()
                                   if not path.startswith(permitted)}
        self.assertEqual(protected(before), protected(self.files()))
        self.assertEqual(report['finding_level'], 'REVIEW_FINDING')
        for key in ('claim_status_changed', 'candidate_status_changed', 'scientific_acceptance',
                    'construction_progression_allowed', 'safety_gate_passed', 'execution_started'):
            self.assertIs(report[key], False, key)
        return report

    def assert_scope_mismatch(self, frozen_scope, candidate_scope):
        request = self.prepare(frozen_scope, candidate_scope)
        report = self.review(request)
        findings = [row for row in report['findings'] if row['code'] == 'MODEL_SCOPE_MISMATCH']
        self.assertTrue(findings, report)
        self.assertTrue(any('corruption_budget_scope' in row['detail'] for row in findings))
        self.assertEqual(report['decision'], 'NEEDS_INPUT')
        self.assertFalse(report['threat_model_complete'])
        if frozen_scope != candidate_scope:
            self.assertEqual(catalog.show(self.project, 'C-0001')['status'], 'CONDITIONAL')

    def test_cumulative_candidate_cannot_silently_claim_per_round_scope(self):
        self.assert_scope_mismatch('CUMULATIVE', 'PER_ROUND')

    def test_per_round_candidate_cannot_silently_claim_cumulative_scope(self):
        self.assert_scope_mismatch('PER_ROUND', 'CUMULATIVE')

    def test_missing_candidate_adaptive_budget_scope_requires_input(self):
        self.assert_scope_mismatch('CUMULATIVE', MISSING)

    def test_missing_frozen_adaptive_budget_cannot_be_supplied_by_candidate(self):
        self.assert_scope_mismatch(MISSING, 'CUMULATIVE')

    def test_missing_both_adaptive_scopes_is_explicitly_unassessed(self):
        self.assert_scope_mismatch(MISSING, MISSING)

    def test_complete_matching_cumulative_scope_counts_corruptions_across_rounds(self):
        report = self.review(self.prepare('CUMULATIVE', 'CUMULATIVE'))
        self.assertEqual(report['decision'], 'NEEDS_REVIEW')
        self.assertTrue(report['threat_model_complete'])
        self.assertNotIn('MODEL_SCOPE_MISMATCH', {row['code'] for row in report['findings']})
        self.assertEqual(report['attack_plans'][0]['status'], 'OUT_OF_SCOPE')
        self.assertFalse(report['attack_plans'][0]['counterexample_to_frozen_goal'])

    def test_complete_matching_per_round_scope_preserves_finite_trace_limit(self):
        report = self.review(self.prepare('PER_ROUND', 'PER_ROUND'))
        self.assertEqual(report['decision'], 'NEEDS_REVIEW')
        self.assertTrue(report['threat_model_complete'])
        self.assertNotIn('MODEL_SCOPE_MISMATCH', {row['code'] for row in report['findings']})
        self.assertEqual(report['attack_plans'][0]['status'], 'FIXED_TRACE_PLAN_REQUIRES_INDEPENDENT_REVIEW')
        self.assertFalse(report['attack_plans'][0]['counterexample_to_frozen_goal'])
