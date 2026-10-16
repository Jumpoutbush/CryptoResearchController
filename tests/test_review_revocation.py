"""Persist observed revocation in canonical claims; reads never rewrite authority."""
import copy
import unittest
from unittest import mock

import test_discovery as discovery_fixture
import test_knowledge_graph as knowledge_fixture
from engine import claim_graph as claims, knowledge_graph
from engine.common import evidence, object_hash
from knowledge import build as projection
from research_quality import hash_file


class ClaimRevocationReviewTests(unittest.TestCase):
    setUp = knowledge_fixture.KnowledgeGraphTests.setUp
    put = knowledge_fixture.KnowledgeGraphTests.put
    files = knowledge_fixture.KnowledgeGraphTests.files
    legacy_claim = knowledge_fixture.KnowledgeGraphTests.legacy_claim
    register = knowledge_fixture.KnowledgeGraphTests.register
    record = knowledge_fixture.KnowledgeGraphTests.record
    novelty_review = discovery_fixture.DiscoveryTests.novelty_review

    def chain(self, knowledge_dependencies=None):
        for cid, deps in [('A', []), ('B', ['A']), ('C', ['B'])]:
            self.put('proofs/source-' + cid + '.md', 'Exact source argument for fixture ' + cid)
            changes = {'knowledge_dependencies': knowledge_dependencies} if cid == 'A' and knowledge_dependencies else {}
            self.legacy_claim(cid, dependencies=deps, evidence_paths=['proofs/source-' + cid + '.md'], **changes)
            self.review(cid)
        self.assertTrue(all(c['proof_status'] == 'INDEPENDENTLY_REVIEWED' for c in claims.status(self.project)['claims']))

    def review(self, cid='A', kind='proof_and_statement'):
        relative = 'research/review-' + cid + '.md'
        if not (self.project / relative).exists(): self.put(relative, 'Operator proof/statement examination for ' + cid)
        claims.review(self.project, cid, kind, relative, 'independent-operator', 'Recheck the exact original fixture statement')

    def states(self):
        return {c['id']: c for c in claims.status(self.project)['claims']}

    def corrupt_and_restore(self, relative, observe):
        path = self.project / relative; raw = path.read_bytes()
        path.write_bytes(raw + b'\nchanged source')
        observe()
        path.write_bytes(raw)

    def assert_pending(self, ids=('A', 'B', 'C')):
        for cid in ids:
            self.assertEqual(self.states()[cid]['proof_status'], 'PENDING_REVALIDATION')

    def test_explicit_refresh_latches_original_evidence_loss_and_transitive_dependents(self):
        self.chain(); state = (self.project / 'research/STATE.json').read_bytes()
        self.corrupt_and_restore('proofs/source-A.md', lambda: claims.refresh(self.project))
        self.assert_pending()
        self.assertIn('REVALIDATION_REQUIRED:review:proof', self.states()['A']['invalidation_reasons'])
        self.assertEqual((self.project / 'research/STATE.json').read_bytes(), state)
        self.assertTrue(claims.get(self.project, 'A')['revocation_latches'])

    def test_explicit_observation_then_build_keeps_latch_after_disposable_cache_deletion(self):
        self.chain(); projection.build(self.root, self.project)
        def observe_and_build():
            claims.refresh(self.project)
            projection.build(self.root, self.project)
        self.corrupt_and_restore('proofs/source-A.md', observe_and_build)
        projection.cache_path(self.root, self.project).unlink()
        self.assert_pending()
        projection.build(self.root, self.project)
        self.assert_pending()
        self.assertEqual(projection.explain_claim(self.root, self.project, 'A')['claim']['proof_status'], 'PENDING_REVALIDATION')
        trace = projection.explain_claim(self.root, self.project, 'C')['lineage']['cause_paths']
        old_cause = next(step['persisted_revocation'] for path in trace for step in path
            if step.get('claim_id') == 'A' and step.get('persisted_revocation'))
        self.assertIn('EVIDENCE_CHANGED', old_cause['observed_reasons'])

    def test_original_paper_source_restoration_requires_fresh_review_of_knowledge_dependents(self):
        self.register(); self.chain(knowledge_dependencies=['PAPER-1'])
        pin = copy.deepcopy(claims.get(self.project, 'A')['knowledge_pins'])
        def observe_and_build():
            claims.refresh(self.project)
            projection.build(self.root, self.project)
        self.corrupt_and_restore('literature/paper.txt', observe_and_build)
        self.assert_pending()
        self.assertEqual(claims.get(self.project, 'A')['knowledge_pins'], pin)
        self.review('A'); self.review('B'); self.review('C')
        self.assertTrue(all(c['proof_status'] == 'INDEPENDENTLY_REVIEWED' for c in self.states().values()))

    def test_downstream_new_review_cannot_bypass_unreviewed_upstream_or_clear_its_latch(self):
        self.chain()
        self.corrupt_and_restore('proofs/source-A.md', lambda: claims.refresh(self.project))
        self.review('B'); self.review('C'); self.assert_pending()
        self.review('A')
        self.assertEqual(self.states()['A']['proof_status'], 'INDEPENDENTLY_REVIEWED')
        self.assert_pending(('B', 'C'))
        self.review('B'); self.assertEqual(self.states()['B']['proof_status'], 'INDEPENDENTLY_REVIEWED')
        self.assert_pending(('C',))
        self.review('C')
        self.assertTrue(all(c['proof_status'] == 'INDEPENDENTLY_REVIEWED' for c in self.states().values()))

    def test_review_evidence_restoration_requires_only_the_failed_review_scopes(self):
        self.chain()
        self.corrupt_and_restore('research/review-A.md', lambda: claims.refresh(self.project))
        self.assert_pending()
        self.review('A', 'proof')
        self.assert_pending(('A',))
        self.review('A', 'statement')
        self.assertEqual(self.states()['A']['proof_status'], 'INDEPENDENTLY_REVIEWED')
        self.assert_pending(('B', 'C'))

    def test_novelty_only_failure_does_not_revoke_correctness_scope(self):
        self.chain(); self.novelty_review('A')
        self.assertTrue(self.states()['A']['accepted_contribution'])
        self.corrupt_and_restore('literature/mapping.md', lambda: claims.refresh(self.project))
        self.assertEqual(self.states()['A']['proof_status'], 'INDEPENDENTLY_REVIEWED')
        self.assertEqual(self.states()['A']['novelty_status'], 'PENDING')
        self.assertFalse(self.states()['A']['accepted_contribution'])
        self.novelty_review('A')
        self.assertTrue(self.states()['A']['accepted_contribution'])

    def formal(self):
        item = claims.get(self.project, 'A')
        self.put('proofs/tool-input.txt', 'Frozen tool-only source')
        receipt = {'schema_version': 1, 'claim_id': 'A', 'claim_revision': item['revision'],
            'claim_sha256': item['spec_sha256'], 'status': 'TOOL_PASSED_AUDIT_PENDING',
            'source_bindings': evidence(self.project, ['proofs/tool-input.txt']),
            'reason': 'Offline fake tool boundary; no Lean process', 'at': 'fixture'}
        claims.record_tool(self.project, 'A', 'formal_receipt', receipt)
        self.audit_formal(receipt)
        return receipt

    def audit_formal(self, receipt):
        self.put('research/formal-scope.json', {'claim_id': 'A', 'receipt_sha256': object_hash(receipt),
            'verdict': 'MATCHED_AND_AUDITED', 'statement_mapping': 'Exact fixture mapping',
            'axioms_argument': 'Inspect fixture assumptions', 'dependency_scope': 'Exact frozen fixture scope',
            'allowed_axioms': []})
        claims.review(self.project, 'A', 'formal_audit', 'research/formal-scope.json',
            'independent-operator', 'Audit this exact offline tool receipt')

    def test_tool_evidence_restoration_requires_new_tool_then_new_scope_audit(self):
        self.chain(); receipt = self.formal()
        self.assertEqual(self.states()['A']['formal_status'], 'AUDITED_TOOL_CHECK')
        self.corrupt_and_restore('proofs/tool-input.txt', lambda: claims.refresh(self.project))
        self.assertEqual(self.states()['A']['formal_status'], 'NOT_VERIFIED')
        with self.assertRaisesRegex(ValueError, 'revalidation'):
            self.audit_formal(receipt)
        renewed = copy.deepcopy(receipt); renewed['at'] = 'new isolated tool observation'
        claims.record_tool(self.project, 'A', 'formal_receipt', renewed)
        self.assertNotEqual(self.states()['A']['formal_status'], 'AUDITED_TOOL_CHECK')
        self.audit_formal(renewed)
        self.assertEqual(self.states()['A']['formal_status'], 'AUDITED_TOOL_CHECK')

    def test_restored_tool_output_log_also_keeps_formal_scope_revoked(self):
        self.chain(); receipt = self.formal()
        output = self.root / 'logs/example/formal/offline-output.log'
        output.parent.mkdir(parents=True); output.write_bytes(b'Exact isolated tool output')
        receipt.update(output_file=str(output), output_sha256=hash_file(output))
        claims.record_tool(self.project, 'A', 'formal_receipt', receipt); self.audit_formal(receipt)
        raw = output.read_bytes(); output.write_bytes(b'Changed output')
        claims.refresh(self.project); output.write_bytes(raw)
        self.assertEqual(self.states()['A']['formal_status'], 'NOT_VERIFIED')
        claims.record_tool(self.project, 'A', 'formal_receipt', {**receipt, 'at': 'new tool result'})
        renewed = claims.get(self.project, 'A')['formal_receipt']; self.audit_formal(renewed)
        self.assertEqual(self.states()['A']['formal_status'], 'AUDITED_TOOL_CHECK')

    def test_revocation_marker_and_event_tampering_cannot_silently_restore_approval(self):
        self.chain(); self.corrupt_and_restore('proofs/source-A.md', lambda: claims.refresh(self.project))
        baseline = claims.load(self.project)
        for mutate in (
                lambda item: item.pop('revocation_latches'),
                lambda item: item['revocation_latches']['review:proof'].update(observed_reasons=['Changed audit reason']),
                lambda item: item['revocation_latches'].pop('review:proof')):
            with self.subTest(mutate=mutate):
                data = copy.deepcopy(baseline); mutate(data['claims'][0]); claims.save(self.project, data)
                state = self.states()['A']
                self.assertEqual(state['proof_status'], 'PENDING_REVALIDATION')
                self.assertIn('REVOCATION_HISTORY_INVALID', state['invalidation_reasons'])
                with self.assertRaisesRegex(ValueError, 'REVOCATION_HISTORY_INVALID'):
                    self.review('A')

    def test_readonly_status_context_explain_and_dry_run_do_not_persist_observations(self):
        from knowledge.context_builder import build as context
        self.chain(); path = self.project / 'proofs/source-A.md'; raw = path.read_bytes()
        path.unlink(); before = self.files(self.root)
        self.assert_pending()
        context(self.root, self.project, claim_id='A', task='Inspect the exact fixture')
        projection.explain_claim(self.root, self.project, 'C')
        projection.build(self.root, self.project, dry_run=True)
        self.assertEqual(before, self.files(self.root))
        path.write_bytes(raw)
        self.assertEqual(self.states()['A']['proof_status'], 'INDEPENDENTLY_REVIEWED')

    def test_cache_only_recovery_never_writes_canonical_revocation_or_other_authority(self):
        self.chain(); authority = self.project / 'research/discovery/CLAIM_GRAPH.json'; before = authority.read_bytes()
        self.corrupt_and_restore('proofs/source-A.md', lambda: projection.build(self.root, self.project, cache_only=True))
        self.assertEqual(authority.read_bytes(), before)
        self.assertEqual(self.states()['A']['proof_status'], 'INDEPENDENTLY_REVIEWED')

    def test_legacy_memory_refresh_does_not_write_claim_authority(self):
        self.chain(); before = copy.deepcopy(claims.load(self.project)['claims'])
        self.corrupt_and_restore('proofs/source-A.md', lambda: knowledge_graph.refresh(self.project))
        self.assertEqual(claims.load(self.project)['claims'], before)
        self.assertEqual(self.states()['A']['proof_status'], 'INDEPENDENTLY_REVIEWED')

    def test_explicit_withdrawal_still_requires_revision_and_rebinding(self):
        self.chain(); claims.invalidate(self.project, 'A', 'Operator explicitly withdrew this assertion')
        self.review('A')
        self.assert_pending()
        self.legacy_claim('A', statement='Corrected statement after explicit withdrawal', evidence_paths=['proofs/source-A.md'])
        self.review('A')
        self.assertEqual(self.states()['A']['proof_status'], 'INDEPENDENTLY_REVIEWED')
        self.review('B'); self.assert_pending(('B', 'C'))

    def test_build_failure_after_explicit_canonical_observation_preserves_revocation(self):
        self.chain(); original = self.project / 'proofs/source-A.md'; raw = original.read_bytes()
        original.write_bytes(raw + b'\nobserved-invalid')
        claims.refresh(self.project)
        with mock.patch.object(projection, 'derive', side_effect=OSError('Fail disposable projection')):
            with self.assertRaises(OSError): projection.build(self.root, self.project)
        original.write_bytes(raw)
        self.assert_pending()

    def test_default_build_refuses_unobserved_revocation_without_authority_or_cache_writes(self):
        self.chain(); projection.build(self.root, self.project)
        path = self.project / 'proofs/source-A.md'; path.write_bytes(path.read_bytes() + b'\nchanged source')
        before = self.files(self.root)
        pending = claims.pending_revocations(self.project)
        self.assertTrue(pending)
        self.assertEqual(before, self.files(self.root))
        with self.assertRaisesRegex(ValueError, 'CANONICAL_REVOCATION_OBSERVATION_REQUIRED.*claim refresh example'):
            projection.build(self.root, self.project)
        # Existing Windows file locks append their marker while held. No project,
        # budget, event history or disposable cache bytes may change on refusal.
        data_files = lambda files: {key: value for key, value in files.items() if not key.startswith('locks/')}
        self.assertEqual(data_files(before), data_files(self.files(self.root)))

    def test_empty_and_unreviewed_candidate_builds_do_not_require_artificial_revocations(self):
        empty = projection.build(self.root, self.project)
        self.assertEqual(empty['pending_revocations'], [])
        self.legacy_claim()
        self.put('proofs/derivation.md', 'Changed unreviewed candidate derivation')
        raw = (self.project / 'research/discovery/CLAIM_GRAPH.json').read_bytes()
        result = projection.build(self.root, self.project)
        self.assertEqual(result['pending_revocations'], [])
        self.assertEqual(raw, (self.project / 'research/discovery/CLAIM_GRAPH.json').read_bytes())


if __name__ == '__main__':
    unittest.main()
