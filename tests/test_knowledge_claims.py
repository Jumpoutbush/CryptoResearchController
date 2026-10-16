"""Offline knowledge provenance through the existing claim and discharge gates."""
import copy
import unittest
from unittest import mock

import test_discovery as fixtures
from engine import claim_graph, discovery_scheduler, research_evaluator
from engine.common import evidence, fresh


class KnowledgeClaimTests(unittest.TestCase):
    # Reuse the isolated fixture helpers without rerunning its inherited tests.
    setUp = fixtures.DiscoveryTests.setUp
    tearDown = fixtures.DiscoveryTests.tearDown
    put = fixtures.DiscoveryTests.put
    claim = fixtures.DiscoveryTests.claim
    review_proof = fixtures.DiscoveryTests.review_proof
    novelty_review = fixtures.DiscoveryTests.novelty_review
    checkpoint = fixtures.DiscoveryTests.checkpoint

    def memory(self, node_id='K-paper', kind='paper', dependencies=None, **changes):
        from engine import knowledge_graph
        self.put('literature/source-' + node_id + '.txt', 'A local source fixture for ' + node_id)
        spec = {'schema_version': 1, 'id': node_id, 'kind': kind,
                'title': 'Source fixture ' + node_id,
                'statement': 'A source assertion requiring independent technical assessment.',
                'sources': [{'path': 'literature/source-' + node_id + '.txt', 'locator': 'Page 1, test fixture'}],
                'dependencies': dependencies or [], 'claim_ids': []}
        spec.update(changes)
        knowledge_graph.import_record(self.project, spec, 'Register isolated source fixture')
        return spec

    def test_source_change_invalidates_memory_to_claim_chain_and_discharge_gate(self):
        self.memory()
        self.memory('K-theorem', 'theorem', ['K-paper'])
        self.claim(knowledge_dependencies=['K-theorem']); self.review_proof()
        self.claim('C-2', ['C-1']); self.review_proof('C-2')
        self.assertTrue(all(c['proof_status'] == 'INDEPENDENTLY_REVIEWED'
                            for c in claim_graph.status(self.project)['claims']))
        discovery_scheduler.start(self.project, 'P-1')
        discharged = [{'id': 'O-1', 'status': 'DISCHARGED', 'claim_id': 'C-2',
                       'gap': 'Independent review currently covers this exact obligation.'}]
        self.checkpoint('r1', obligations=discharged)
        self.put('literature/source-K-paper.txt', 'Corrected primary text with a different premise')
        states = {c['id']: c for c in claim_graph.status(self.project)['claims']}
        self.assertTrue(any(r.startswith('KNOWLEDGE_') for r in states['C-1']['invalidation_reasons']))
        self.assertIn('DEPENDENCY_NOT_VALID:C-1', states['C-2']['invalidation_reasons'])
        self.assertTrue(all(c['proof_status'] == 'PENDING_REVALIDATION' for c in states.values()))
        with self.assertRaises(ValueError):
            self.checkpoint('r2', obligations=discharged)

    def test_explicit_source_invalidation_revokes_existing_theory_gate_and_evaluator(self):
        from engine import knowledge_graph
        import theory_gate
        self.memory()
        self.claim(knowledge_dependencies=['K-paper']); self.review_proof(); self.novelty_review()
        self.assertTrue(claim_graph.require_theory_claim(self.project, 'C-1')['accepted_contribution'])
        self.assertEqual(self.cli(['theory', 'approve', 'example', '--claim', 'C-1',
            '--contribution', 'proofs/derivation.md', '--correctness', 'research/proof-C-1.md',
            '--novelty', 'literature/novelty.json', '--reviewer', 'human-operator',
            '--reason', 'Isolated theory gate regression fixture']), 0)
        theory_gate.check_readiness(self.project)
        checkpoint = {'candidate_claim_ids': ['C-1'], 'obligations': [], 'evidence': {}}
        self.assertTrue(research_evaluator.evaluate_checkpoint(self.project, copy.deepcopy(checkpoint))['scientific_acceptance'])
        knowledge_graph.invalidate(self.project, 'K-paper', 'An upstream assumption was explicitly withdrawn')
        self.assertFalse(research_evaluator.evaluate_checkpoint(self.project, checkpoint)['scientific_acceptance'])
        with self.assertRaises(ValueError): claim_graph.require_theory_claim(self.project, 'C-1')
        with self.assertRaises(ValueError): theory_gate.check_readiness(self.project)

    cli = fixtures.DiscoveryTests.cli

    def test_upstream_revision_requires_explicit_claim_rebind_and_new_review(self):
        from engine import knowledge_graph
        spec = self.memory()
        claim = self.claim(knowledge_dependencies=['K-paper']); self.review_proof()
        first_pin = copy.deepcopy(claim_graph.get(self.project, 'C-1')['knowledge_pins'])
        spec['statement'] += ' The revised domain is explicit.'
        knowledge_graph.import_record(self.project, spec, 'Correct the upstream source statement')
        self.assertEqual(claim_graph.status(self.project)['claims'][0]['proof_status'], 'PENDING_REVALIDATION')
        claim_graph.import_claim(self.project, claim, 'Explicitly bind and recheck the revised source')
        revised = claim_graph.get(self.project, 'C-1')
        self.assertEqual(revised['revision'], 2)
        self.assertNotEqual(revised['knowledge_pins'], first_pin)
        self.assertEqual(revised['history'][0]['knowledge_pins'], first_pin)
        self.assertEqual(revised['reviews'], {})
        self.assertEqual(claim_graph.status(self.project)['claims'][0]['proof_status'], 'CANDIDATE')
        self.review_proof()
        self.assertEqual(claim_graph.status(self.project)['claims'][0]['proof_status'], 'INDEPENDENTLY_REVIEWED')
        with self.assertRaises(ValueError):
            claim_graph.import_claim(self.project, claim, 'No artificial identical revision')

    def test_unrelated_memory_does_not_migrate_or_invalidate_legacy_claims(self):
        self.claim(); self.review_proof()
        before = copy.deepcopy(claim_graph.get(self.project, 'C-1'))
        self.assertNotIn('knowledge_pins', before)
        self.memory()
        self.assertEqual(claim_graph.get(self.project, 'C-1'), before)
        self.assertEqual(claim_graph.status(self.project)['claims'][0]['proof_status'], 'INDEPENDENTLY_REVIEWED')
        self.assertNotIn('knowledge_pins', claim_graph.get(self.project, 'C-1'))

    def test_unknown_duplicate_or_unavailable_knowledge_dependencies_leave_claim_unchanged(self):
        from engine import knowledge_graph
        self.memory(); self.claim()
        before = copy.deepcopy(claim_graph.load(self.project))
        for deps in (['MISSING'], ['K-paper', 'K-paper'], 'K-paper'):
            with self.subTest(deps=deps), self.assertRaises(ValueError):
                self.claim(knowledge_dependencies=deps)
            self.assertEqual(claim_graph.load(self.project), before)
        knowledge_graph.invalidate(self.project, 'K-paper', 'The fixture source is unavailable')
        before = copy.deepcopy(claim_graph.load(self.project))
        with self.assertRaises(ValueError): self.claim(knowledge_dependencies=['K-paper'])
        self.assertEqual(claim_graph.load(self.project), before)

    def test_missing_or_malformed_knowledge_pins_cannot_keep_a_reviewed_claim_valid(self):
        self.memory(); self.claim(knowledge_dependencies=['K-paper']); self.review_proof()
        original = claim_graph.load(self.project)
        for pins in ({}, None):
            corrupted = copy.deepcopy(original)
            corrupted['claims'][0]['knowledge_pins'] = pins
            claim_graph.save(self.project, corrupted)
            state = claim_graph.status(self.project)['claims'][0]
            self.assertEqual(state['proof_status'], 'PENDING_REVALIDATION')
            self.assertFalse(state['accepted_contribution'])

    def test_canonical_control_and_supervision_paths_cannot_certify_claims(self):
        self.claim()
        self.put('research/supervision_report.md', 'Controller scheduling, not scientific evidence')
        self.put('research/supervision/review-1/report.md', 'Controller scheduling history')
        paths = [
            'research/../research/discovery/CLAIM_GRAPH.json',
            'proofs/../research/supervision_report.md',
            'research/../research/supervision/review-1/report.md',
        ]
        for path in paths:
            with self.subTest(path=path), self.assertRaises(ValueError):
                evidence(self.project, [path])

    def test_link_replacement_invalidates_existing_evidence_binding(self):
        path = 'proofs/derivation.md'
        bindings = evidence(self.project, [path])
        target_component = self.project / 'proofs'
        with mock.patch('runner_core.project_link', side_effect=lambda value: value == target_component):
            self.assertFalse(fresh(self.project, bindings))
            with self.assertRaises(ValueError):
                evidence(self.project, [path])


if __name__ == '__main__': unittest.main()
