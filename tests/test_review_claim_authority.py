"""Canonical claim binding integrity and lossless same-revision audit receipts."""
import copy
import unittest

import test_discovery as fixtures
from engine import claim_graph as graph
from engine.common import evidence, object_hash


class ClaimAuthorityReviewTests(unittest.TestCase):
    setUp = fixtures.DiscoveryTests.setUp
    tearDown = fixtures.DiscoveryTests.tearDown
    put = fixtures.DiscoveryTests.put
    claim = fixtures.DiscoveryTests.claim
    review_proof = fixtures.DiscoveryTests.review_proof
    novelty_review = fixtures.DiscoveryTests.novelty_review

    def claim_state(self, cid='C-1'):
        return next(c for c in graph.status(self.project)['claims'] if c['id'] == cid)

    def tool(self, reason='First exact isolated tool result'):
        item = graph.get(self.project, 'C-1')
        return {'schema_version': 1, 'claim_id': 'C-1', 'claim_revision': item['revision'],
                'claim_sha256': item['spec_sha256'], 'status': 'TOOL_PASSED_AUDIT_PENDING',
                'source_bindings': evidence(self.project, ['proofs/derivation.md']),
                'reason': reason, 'at': '2026-10-16T00:00:00Z'}

    def test_missing_ordinary_pin_closes_canonical_and_transitive_acceptance(self):
        self.claim(); self.review_proof()
        self.claim('C-2', ['C-1']); self.review_proof('C-2'); self.novelty_review('C-2')
        self.claim('C-3', ['C-2']); self.review_proof('C-3'); self.novelty_review('C-3')
        self.assertTrue(self.claim_state('C-3')['accepted_contribution'])
        data = graph.load(self.project)
        data['claims'][1]['dependency_pins'] = {}
        graph.save(self.project, data)
        graph.invalidate(self.project, 'C-1', 'Explicitly withdraw the upstream assertion')
        for cid in ('C-2', 'C-3'):
            state = self.claim_state(cid)
            self.assertEqual(state['proof_status'], 'PENDING_REVALIDATION')
            self.assertEqual(state['novelty_status'], 'PENDING')
            self.assertFalse(state['accepted_contribution'])
        self.assertIn('DEPENDENCY_BINDING_INVALID', self.claim_state('C-2')['invalidation_reasons'])
        self.assertEqual(graph.get(self.project, 'C-2')['dependency_pins'], {})

    def test_malformed_pin_shapes_and_types_fail_closed_without_repair(self):
        self.claim(); self.review_proof()
        self.claim('C-2', ['C-1']); self.review_proof('C-2')
        baseline = graph.load(self.project)
        valid = copy.deepcopy(baseline['claims'][1]['dependency_pins']['C-1'])
        invalid = [None, [], {}, {'OTHER': valid}, {'C-1': None},
                   {'C-1': {**valid, 'revision': True}}, {'C-1': {**valid, 'revision': 0}},
                   {'C-1': {**valid, 'revision': '1'}}, {'C-1': {**valid, 'revision': -1}},
                   {'C-1': {**valid, 'spec_sha256': 'f' * 63}},
                   {'C-1': {**valid, 'spec_sha256': 7}},
                   {'C-1': {**valid, 'spec_sha256': 'G' * 64}},
                   {'C-1': {**valid, 'extra': 'unbound'}},
                   {'C-1': valid, 'OTHER': valid}]
        for pins in invalid:
            with self.subTest(pins=pins):
                data = copy.deepcopy(baseline); data['claims'][1]['dependency_pins'] = pins
                graph.save(self.project, data)
                before = (self.project / 'research/discovery/CLAIM_GRAPH.json').read_bytes()
                self.assertEqual(self.claim_state('C-2')['proof_status'], 'PENDING_REVALIDATION')
                self.assertIn('DEPENDENCY_BINDING_INVALID', self.claim_state('C-2')['invalidation_reasons'])
                self.assertEqual((self.project / 'research/discovery/CLAIM_GRAPH.json').read_bytes(), before)

    def test_pin_corruption_also_closes_a_previously_audited_formal_gate(self):
        self.claim(); self.review_proof()
        self.claim('C-2', ['C-1']); self.review_proof('C-2')
        tool = self.tool(); tool.update(claim_id='C-2', claim_sha256=graph.get(self.project, 'C-2')['spec_sha256'])
        graph.record_tool(self.project, 'C-2', 'formal_receipt', tool)
        self.put('research/audit.json', {'claim_id': 'C-2', 'receipt_sha256': object_hash(tool),
            'verdict': 'MATCHED_AND_AUDITED', 'statement_mapping': 'Exact isolated mapping',
            'axioms_argument': 'All fixture axioms checked', 'dependency_scope': 'Pinned upstream fixture',
            'allowed_axioms': []})
        graph.review(self.project, 'C-2', 'formal_audit', 'research/audit.json', 'auditor', 'Inspect exact tool receipt')
        self.assertEqual(self.claim_state('C-2')['formal_status'], 'AUDITED_TOOL_CHECK')
        data = graph.load(self.project); data['claims'][1]['dependency_pins'] = {}
        graph.save(self.project, data)
        self.assertEqual(self.claim_state('C-2')['formal_status'], 'NOT_VERIFIED')

    def test_missing_pin_field_can_only_be_rebound_by_explicit_new_revision(self):
        self.claim(); self.review_proof()
        spec = self.claim('C-2', ['C-1']); self.review_proof('C-2')
        data = graph.load(self.project); data['claims'][1].pop('dependency_pins'); graph.save(self.project, data)
        self.assertEqual(self.claim_state('C-2')['proof_status'], 'PENDING_REVALIDATION')
        self.assertNotIn('dependency_pins', graph.get(self.project, 'C-2'))
        graph.import_claim(self.project, spec, 'Operator explicitly rebinds a damaged old dependency record')
        item = graph.get(self.project, 'C-2')
        self.assertEqual(item['revision'], 2)
        self.assertEqual(item['dependency_pins']['C-1']['revision'], 1)
        self.assertEqual(item['reviews'], {})
        self.assertEqual(self.claim_state('C-2')['proof_status'], 'CANDIDATE')

    def test_same_revision_reviews_retain_both_complete_receipts(self):
        self.claim()
        self.put('research/first-review.md', 'First independent exact derivation')
        graph.review(self.project, 'C-1', 'proof', 'research/first-review.md', 'first-reviewer', 'First explicit proof reason')
        first = copy.deepcopy(graph.get(self.project, 'C-1')['reviews']['proof'])
        self.put('research/second-review.md', 'Second independent proof examination')
        graph.review(self.project, 'C-1', 'proof', 'research/second-review.md', 'second-reviewer', 'Second explicit proof reason')
        item = graph.get(self.project, 'C-1'); history = item['receipt_history']
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]['receipt'], first)
        self.assertEqual(history[0]['receipt_sha256'], object_hash(first))
        self.assertEqual(history[1]['receipt'], item['reviews']['proof'])
        self.assertNotEqual(history[0]['operation_id'], history[1]['operation_id'])
        self.assertEqual(history[1]['previous_record_sha256'], history[0]['record_sha256'])
        self.assertEqual(history[1]['supersedes_operation_id'], history[0]['operation_id'])
        self.assertEqual(item['current_receipt_ids']['review:proof']['operation_id'], history[1]['operation_id'])
        self.assertEqual(history[0]['claim_revision'], 1)
        self.assertEqual(history[0]['claim_sha256'], item['spec_sha256'])
        self.assertEqual(history[0]['source_bindings'], first['evidence'])
        self.put('research/first-review.md', 'The original evidence has since been overwritten')
        self.assertEqual(graph.get(self.project, 'C-1')['receipt_history'][0], history[0])

    def test_same_revision_tools_preserve_full_receipts_and_original_payload_hash(self):
        self.claim()
        first = self.tool(); untouched = copy.deepcopy(first)
        graph.record_tool(self.project, 'C-1', 'formal_receipt', first)
        second = self.tool('Second exact tool outcome with a different diagnostic')
        second['status'] = 'FAILED'
        graph.record_tool(self.project, 'C-1', 'formal_receipt', second)
        item = graph.get(self.project, 'C-1'); history = item['receipt_history']
        self.assertEqual(first, untouched)
        self.assertEqual([entry['receipt'] for entry in history], [first, second])
        self.assertEqual([entry['source_bindings'] for entry in history], [first['source_bindings'], second['source_bindings']])
        self.assertEqual(item['formal_receipt'], second)
        self.assertEqual(item['formal_receipt_sha256'], object_hash(second))
        self.assertEqual(history[1]['supersedes_record_sha256'], history[0]['record_sha256'])
        self.assertEqual(history[0]['reason'], first['reason'])

    def test_receipt_history_and_current_pointer_tampering_fail_closed(self):
        self.claim(); self.review_proof()
        baseline = graph.load(self.project)
        changes = (
            lambda item: item['receipt_history'][0]['receipt'].update(reason='Unbound changed history'),
            lambda item: item['receipt_history'][0].update(reason='Changed envelope reason'),
            lambda item: item['current_receipt_ids']['review:proof'].update(operation_id='not-the-latest'),
            lambda item: item['current_receipt_ids'].pop('review:proof'),
            lambda item: item['reviews']['proof'].update(reason='Changed current payload'),
            lambda item: item['receipt_history'].reverse(),
            lambda item: [item.pop(key) for key in ('receipt_history', 'receipt_history_schema_version',
                'receipt_history_availability', 'current_receipt_ids', 'legacy_current_receipts')],
        )
        for change in changes:
            with self.subTest(change=change):
                data = copy.deepcopy(baseline); change(data['claims'][0]); graph.save(self.project, data)
                self.assertEqual(self.claim_state()['proof_status'], 'PENDING_REVALIDATION')
                self.assertIn('RECEIPT_HISTORY_INVALID', self.claim_state()['invalidation_reasons'])

    def test_new_revision_keeps_the_old_revision_complete_receipt_chain(self):
        spec = self.claim(); self.review_proof()
        old = graph.get(self.project, 'C-1')
        spec['statement'] += ' with an explicitly clarified domain'
        graph.import_claim(self.project, spec, 'Explicit claim revision after review')
        current = graph.get(self.project, 'C-1')
        self.assertEqual(current['receipt_history'], [])
        self.assertEqual(current['history'][0]['receipt_history'], old['receipt_history'])
        self.assertEqual(current['history'][0]['current_receipt_ids'], old['current_receipt_ids'])

    def test_audit_event_must_reference_the_complete_matching_review_receipt(self):
        self.claim(); self.review_proof(); baseline = graph.load(self.project)
        for changes in ({'operation_id': '0' * 32}, {'record_sha256': '0' * 64},
                        {'reviewer': 'unrecorded replacement'}, {'kind': 'novelty'}, {'type': 'TOOL_RESULT'}):
            with self.subTest(changes=changes):
                data = copy.deepcopy(baseline)
                event = next(e for e in data['events'] if e['type'] == 'INDEPENDENT_REVIEW')
                event.update(changes); graph.save(self.project, data)
                self.assertEqual(self.claim_state()['proof_status'], 'PENDING_REVALIDATION')
                self.assertIn('RECEIPT_HISTORY_INVALID', self.claim_state()['invalidation_reasons'])

    def test_legacy_missing_operation_history_is_not_fabricated_or_silently_rewritten(self):
        self.claim(); self.review_proof()
        data = graph.load(self.project); item = data['claims'][0]
        for key in ('receipt_history', 'receipt_history_schema_version', 'receipt_history_availability',
                    'current_receipt_ids', 'legacy_current_receipts'):
            item.pop(key, None)
        previous = copy.deepcopy(item['reviews'])
        for event in data['events']:
            for key in ('operation_id', 'record_sha256', 'receipt_sha256'):
                event.pop(key, None)
        graph.save(self.project, data)
        before = (self.project / 'research/discovery/CLAIM_GRAPH.json').read_bytes()
        self.assertEqual(self.claim_state()['proof_status'], 'INDEPENDENTLY_REVIEWED')
        self.assertEqual((self.project / 'research/discovery/CLAIM_GRAPH.json').read_bytes(), before)
        self.put('research/renewed-review.md', 'A newly observed exact proof review')
        graph.review(self.project, 'C-1', 'proof', 'research/renewed-review.md', 'new-reviewer', 'Newly recorded operator reasoning')
        current = graph.get(self.project, 'C-1')
        self.assertEqual(current['receipt_history_availability'], 'LEGACY_OPERATIONS_UNAVAILABLE')
        self.assertEqual(len(current['receipt_history']), 1)
        self.assertEqual(current['legacy_current_receipts']['review:proof']['receipt'], previous['proof'])
        self.assertEqual(current['legacy_current_receipts']['review:proof']['availability'],
                         'CURRENT_SNAPSHOT_ONLY_OPERATION_HISTORY_UNAVAILABLE')
        self.assertIsNone(current['receipt_history'][0]['supersedes_operation_id'])
        self.assertEqual(self.claim_state()['proof_status'], 'INDEPENDENTLY_REVIEWED')

    def test_multiple_review_kinds_chain_every_operation_and_supersede_only_its_slot(self):
        self.claim(); self.review_proof()
        self.put('research/second-proof.md', 'An additional exact proof examination')
        graph.review(self.project, 'C-1', 'proof', 'research/second-proof.md', 'another-reviewer', 'Explicitly repeat the proof check')
        records = graph.get(self.project, 'C-1')['receipt_history']
        self.assertEqual([r['slot'] for r in records], ['review:proof', 'review:statement', 'review:proof'])
        self.assertEqual(records[2]['previous_operation_id'], records[1]['operation_id'])
        self.assertEqual(records[2]['supersedes_operation_id'], records[0]['operation_id'])


if __name__ == '__main__':
    unittest.main()
