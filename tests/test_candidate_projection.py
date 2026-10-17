"""Candidate archives project as scoped history without scientific writes."""
import unittest

import test_candidate_contract as fixtures
from knowledge import build
from knowledge.adapters import candidate_resolutions


class CandidateProjectionTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.CandidateContractTests('test_same_title_different_hypothesis_is_not_deduplicated')
        self.f.setUp()

    def tearDown(self):
        self.f.tearDown()

    def test_catalog_without_resolution_history_keeps_legacy_projection_identical(self):
        before = build.derive(self.f.root, self.f.project)
        self.f.add()
        self.assertEqual(build.derive(self.f.root, self.f.project), before)
        self.assertEqual(candidate_resolutions.controller_paths(self.f.root, 'example'), [])

    def test_legacy_manual_refuted_label_does_not_become_verified_archive(self):
        self.f.add()
        from candidate_search import catalog
        catalog.transition(self.f.project, 'C-0001', 'REFUTED', 'Original operator metadata only',
            expected_revision=1, disposition={'scope': 'One construction only',
                'restart_conditions': 'A new construction and independent review', 'evidence_refs': []})
        graph = build.derive(self.f.root, self.f.project)
        self.assertFalse(any(n['kind']=='FAILED_BRANCH' and n.get('origin_role')=='CANDIDATE_RESOLUTION'
                             for n in graph['nodes']))
        self.assertEqual(candidate_resolutions.controller_paths(self.f.root, 'example'), [])

    def retire(self):
        from candidate_search import resolution
        self.f.add(evidence_refs=['proofs/derivation.md'])
        return resolution.retire(self.f.project, 'C-0001', expected_revision=1,
            reason='Only this construction is retired', scope='Exact candidate revision only',
            restart_conditions='New assumptions with independently checked evidence')

    def test_archive_projects_scope_and_source_change_keeps_history_pending(self):
        self.retire()
        before = self.f.files()
        graph = build.derive(self.f.root, self.f.project)
        archived = [n for n in graph['nodes'] if n.get('origin_role')=='CANDIDATE_RESOLUTION']
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0]['kind'], 'FAILED_BRANCH')
        self.assertEqual(archived[0]['validity'], 'SOURCE_BOUND')
        self.assertEqual(archived[0]['conclusion_scope'], 'Exact candidate revision only')
        self.assertFalse(archived[0]['positive_basis'])
        self.assertFalse(archived[0]['family_refuted'])
        self.assertFalse(any(e['from']==archived[0]['id'] and e['relation']=='REFUTES' for e in graph['edges']))
        self.assertEqual(self.f.files(), before)
        self.f.put('proofs/derivation.md', 'An operator changed this source after retirement.')
        changed = build.derive(self.f.root, self.f.project)
        history_node = next(n for n in changed['nodes'] if n.get('origin_role')=='CANDIDATE_RESOLUTION')
        self.assertEqual(history_node['validity'], 'PENDING_REVALIDATION')
        self.assertEqual(history_node['status'], 'RETIRED')

    def test_exact_problem_retrieval_retains_scoped_archive_body_without_acceptance(self):
        self.retire()
        from knowledge import retrieval
        before = self.f.files()
        found = retrieval.search(self.f.root, self.f.project, problem_id='P-1', problem_version=1)
        item = next(v for v in found['candidates'] if 'branch_archive' in v)
        self.assertEqual(item['branch_archive']['conclusion_scope'], 'Exact candidate revision only')
        self.assertEqual(item['branch_archive']['candidate_id'], 'C-0001')
        self.assertEqual(item['role'], 'SCOPED_BRANCH_HISTORY')
        self.assertFalse(item['positive_basis'])
        self.assertFalse(item['scientific_acceptance'])
        self.assertEqual(self.f.files(), before)

    def test_orphan_witness_stops_readonly_projection_without_reenrollment(self):
        self.retire()
        from candidate_search import history
        history.path(self.f.project).unlink()
        before = self.f.files()
        with self.assertRaises(ValueError):
            build.derive(self.f.root, self.f.project)
        self.assertEqual(self.f.files(), before)


class CandidateCertificateProjectionTests(unittest.TestCase):
    def setUp(self):
        import test_candidate_end_to_end as e2e
        self.f = e2e.CandidateEndToEndTests('test_exact_certificate_and_original_independent_review_refute_only_local_candidate')
        self.f.setUp()

    def tearDown(self):
        self.f.tearDown()

    def test_deleted_original_machine_receipt_invalidates_archive_without_erasing_failure(self):
        from candidate_search import resolution
        from candidate_search.verifiers import interface
        card = self.f.refutation()
        result = resolution.resolve(self.f.project,
            resolution.prepare_request(self.f.project, 'C-0001', 'CLAIM-A', card))
        self.assertEqual(result['status'], 'REFUTED')
        before = self.f.files()
        graph = build.derive(self.f.root, self.f.project)
        archived = next(n for n in graph['nodes'] if n.get('origin_role') == 'CANDIDATE_RESOLUTION')
        self.assertEqual(archived['validity'], 'SOURCE_BOUND')
        self.assertEqual(len(archived['controller_evidence_bindings']), 3)
        self.assertEqual(self.f.files(), before)
        receipt = interface._paths(self.f.project, card['verification_request_id'])['receipt']
        relative = receipt.relative_to(self.f.root).as_posix()
        receipt.unlink()
        after = self.f.files()
        changed = build.derive(self.f.root, self.f.project)
        node = next(n for n in changed['nodes'] if n.get('origin_role') == 'CANDIDATE_RESOLUTION')
        self.assertEqual(node['validity'], 'PENDING_REVALIDATION')
        self.assertEqual(node['status'], 'REFUTED')
        self.assertIn('CONTROLLER:' + relative, node['stale_sources'])
        self.assertFalse(node['positive_basis'])
        self.assertNotEqual(graph['source_manifest'], changed['source_manifest'])
        self.assertEqual(self.f.files(), after)

    def test_persisted_statement_revocation_keeps_archive_pending_after_source_bytes_are_restored(self):
        from candidate_search import resolution
        from engine import claim_graph
        card = self.f.refutation()
        report = resolution.resolve(self.f.project,
            resolution.prepare_request(self.f.project, 'C-0001', 'CLAIM-A', card))
        self.assertEqual(report['status'], 'REFUTED')
        source = self.f.project / card['semantic_review_file']
        frozen = source.read_bytes()
        self.f.put(card['semantic_review_file'], {'changed': 'Scope mapping changed after archiving'})
        claim_graph.refresh(self.f.project)
        source.write_bytes(frozen)
        before = self.f.files()
        graph = build.derive(self.f.root, self.f.project)
        archived = next(n for n in graph['nodes'] if n.get('origin_role') == 'CANDIDATE_RESOLUTION')
        self.assertEqual(archived['validity'], 'PENDING_REVALIDATION')
        self.assertIn('AUTHORITY:research/discovery/CLAIM_GRAPH.json', archived['stale_sources'])
        self.assertEqual(archived['status'], 'REFUTED')
        self.assertFalse(archived['positive_basis'])
        self.assertEqual(self.f.files(), before)
