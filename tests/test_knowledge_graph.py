"""Long term research memory invariants, using only isolated offline fixtures."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

import configuration
from engine import claim_graph, knowledge_graph as knowledge, problem_compiler
from engine.knowledge_links import link_records
from research_quality import hash_file


SOURCE = Path(__file__).resolve().parents[1]


class KnowledgeGraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='knowledge graph space ')
        self.root = Path(self.tmp.name)
        shutil.copytree(SOURCE / 'config', self.root / 'config')
        self.project = self.root / 'projects/example'
        self.project.mkdir(parents=True)
        self.put('PROJECT.json', {'id': 'example', 'checks': []})
        self.put('GOAL.md', 'Keep the exact frozen target, threat model and proof obligations.')
        self.put('AGENTS.md', 'Do not weaken the user goal or promote unreviewed statements.')
        self.put('RESEARCH_PROFILE.json', {'profiles': [], 'read_order': []})
        self.put('research/STATE.json', {'phase': 'PROOF', 'decision': 'CONTINUE',
            'research_route': 'MAIN', 'last_run': None,
            'next_task': 'Resolve the original exact statement under its frozen assumptions.'})
        self.put('proofs/derivation.md', '# Candidate derivation\nA local argument awaits independent review.\n')
        self.put('literature/paper.txt', '# Source paper\nTheorem 1: every integer square is nonnegative.\nScope: integers only.\n')
        self.patch = mock.patch.object(configuration, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def put(self, relative, value):
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2)
                        if isinstance(value, (dict, list)) else value, encoding='utf8')
        return path

    def files(self, directory=None):
        directory = directory or self.project
        return {p.relative_to(directory).as_posix(): p.read_bytes()
                for p in directory.rglob('*') if p.is_file() and not p.is_symlink()}

    def legacy_claim(self, cid='C-1', dependencies=None, **updates):
        problem = {'schema_version': 1, 'id': 'P-1', 'title': 'Exact fixture invariant',
            'statement': 'Every integer square is nonnegative.', 'quantifiers': 'for every x',
            'domain': 'integers', 'input_contract': 'an integer x',
            'output_contract': 'a proof that x*x >= 0', 'goal_connection': 'Frozen exact fixture',
            'nontriviality_argument': 'Infrastructure fixture; no new scientific claim is made.',
            'assumptions': ['x is an integer'], 'immutable_constraints': ['Integer arithmetic'],
            'baseline_exclusions': ['No novel theorem is asserted'],
            'contribution_type': 'COMPLEXITY_THEOREM', 'source_paths': [],
            'obligations': [{'id': 'O-1', 'statement': 'The exact integer invariant',
                             'acceptance_criterion': 'Independent proof and statement review'}]}
        if not problem_compiler.pool(self.project)['problems']:
            problem_compiler.import_problem(self.project, problem, 'Register offline problem fixture')
        spec = {'schema_version': 1, 'id': cid,
            'statement': 'Every integer square is nonnegative.', 'assumptions': ['x is an integer'],
            'dependencies': dependencies or [], 'proposer': 'fixture-proposer',
            'problem_id': 'P-1', 'problem_version': 1, 'obligation_ids': ['O-1'],
            'nontriviality_argument': 'Infrastructure fixture only; no scientific novelty claim.',
            'contribution_type': 'COMPLEXITY_THEOREM', 'evidence_paths': ['proofs/derivation.md'],
            'verification_mode': 'INDEPENDENT_MANUAL',
            'formal_applicability_reason': 'Offline graph fixture, no Lean assertion.'}
        spec.update(updates)
        return claim_graph.import_claim(self.project, spec, 'Register offline claim fixture')

    def record(self, node_id='PAPER-1', kind='paper', path='literature/paper.txt',
               locator='lines:1-3', dependencies=None, **updates):
        spec = {'schema_version': 1, 'id': node_id, 'kind': kind,
            'title': 'Offline research source ' + node_id,
            'statement': 'Source-backed fixture, requiring independent scientific review.',
            'sources': [{'path': path, 'locator': locator}],
            'dependencies': dependencies or []}
        spec.update(updates)
        return spec

    def register(self, spec=None, **updates):
        return knowledge.import_record(self.project, spec or self.record(**updates),
                                       'Register isolated offline research memory fixture')

    def node_status(self, node_id):
        return next(n for n in knowledge.status(self.project)['memory_nodes'] if n['id'] == node_id)

    def assert_rejected_or_pending(self, node_id):
        """Corruption may reject the read, but must never regain source validity."""
        try:
            item = self.node_status(node_id)
        except (ValueError, KeyError, TypeError, AttributeError):
            return
        self.assertEqual(item['validity'], 'PENDING_REVALIDATION')
        with self.assertRaises((ValueError, KeyError, TypeError, AttributeError)):
            knowledge.pin_dependencies(self.project, [node_id])

    def chain(self):
        self.register()
        self.register(self.record('THEOREM-1', 'theorem', dependencies=['PAPER-1']))
        self.register(self.record('EVIDENCE-1', 'evidence', 'proofs/derivation.md', 'lines:1-2',
                                  dependencies=['THEOREM-1']))
        self.register(self.record('OBLIGATION-1', 'obligation', 'proofs/derivation.md', 'lines:1-2',
                                  dependencies=['EVIDENCE-1']))

    def test_queries_do_not_create_storage_or_change_existing_files(self):
        before = self.files()
        directories = sorted(str(p.relative_to(self.project)) for p in self.project.rglob('*') if p.is_dir())
        knowledge.status(self.project)
        knowledge.search(self.project, 'integer')
        for action in (knowledge.get, knowledge.trace, knowledge.impact):
            with self.assertRaises(ValueError):
                action(self.project, 'DOES-NOT-EXIST')
        self.assertEqual(self.files(), before)
        self.assertEqual(sorted(str(p.relative_to(self.project)) for p in self.project.rglob('*') if p.is_dir()),
                         directories)
        self.assertFalse((self.project / 'research/discovery').exists())

    def test_import_reuses_canonical_graph_and_preserves_existing_claim_events(self):
        self.legacy_claim()
        before = copy.deepcopy(claim_graph.load(self.project))
        self.register(claim_ids=['C-1'])
        after = claim_graph.load(self.project)
        self.assertEqual(after['claims'], before['claims'])
        self.assertEqual(after['events'], before['events'])
        self.assertEqual(after['memory']['nodes'][0]['id'], 'PAPER-1')
        self.assertFalse((self.project / 'research/KNOWLEDGE_GRAPH.json').exists())
        self.assertEqual(claim_graph.status(self.project)['claims'][0]['proof_status'], 'CANDIDATE')

    def test_source_bound_records_do_not_claim_independent_scientific_verification(self):
        self.register(metadata={'status': 'PROVED_SELF_CONTAINED', 'independent_review': True})
        result = self.node_status('PAPER-1')
        self.assertEqual(result['validity'], 'SOURCE_BOUND')
        self.assertEqual(result['verification_status'], 'UNVERIFIED_SOURCE')
        self.assertNotIn('accepted_contribution', result)

    def test_exact_line_reference_and_file_digest_are_retained(self):
        spec = self.record(locator='lines:2-2')
        spec['sources'][0]['sha256'] = hash_file(self.project / 'literature/paper.txt')
        self.register(spec)
        item = knowledge.get(self.project, 'PAPER-1')
        self.assertEqual(item['spec']['sources'][0]['locator'], 'lines:2-2')
        self.assertEqual(item['source_bindings']['literature/paper.txt'],
                         hash_file(self.project / 'literature/paper.txt'))

    def test_json_pointer_reference_requires_an_existing_entry_and_preserves_metadata(self):
        self.put('literature/SEED_PAPERS.json', {'papers': [{'id': 'P01',
            'title': 'Historical metadata', 'full_text_status': 'FULL_TEXT_UNCHECKED'}]})
        self.register(self.record(path='literature/SEED_PAPERS.json', locator='json:/papers/0',
            metadata={'full_text_status': 'FULL_TEXT_UNCHECKED'}))
        self.assertEqual(knowledge.get(self.project, 'PAPER-1')['spec']['metadata']['full_text_status'],
                         'FULL_TEXT_UNCHECKED')
        with self.assertRaises(ValueError):
            self.register(self.record('BAD-POINTER', path='literature/SEED_PAPERS.json',
                                      locator='json:/papers/99'))

    def test_paper_page_locator_remains_a_declaration_not_original_page_verification(self):
        self.register(locator='page:4; theorem:2.1', metadata={'binary_available': False,
            'hash_scope': 'web tool response archive ONLY, not the source PDF'})
        item = knowledge.get(self.project, 'PAPER-1')
        self.assertEqual(item['spec']['sources'][0]['locator'], 'page:4; theorem:2.1')
        self.assertFalse(item['spec']['metadata']['binary_available'])
        self.assertEqual(self.node_status('PAPER-1')['verification_status'], 'UNVERIFIED_SOURCE')

    def test_upstream_edit_invalidates_entire_dependency_chain_but_not_unrelated_node(self):
        self.chain()
        self.put('proofs/unrelated.md', 'A separate source.\n')
        self.register(self.record('UNRELATED', 'evidence', 'proofs/unrelated.md', 'lines:1-1'))
        self.put('literature/paper.txt', '# Source paper\nThe upstream theorem was corrected.\nScope changed.\n')
        for node_id in ('PAPER-1', 'THEOREM-1', 'EVIDENCE-1', 'OBLIGATION-1'):
            with self.subTest(node=node_id):
                self.assertEqual(self.node_status(node_id)['validity'], 'PENDING_REVALIDATION')
        self.assertEqual(self.node_status('UNRELATED')['validity'], 'SOURCE_BOUND')

    def test_deleted_source_is_pending_revalidation_and_history_is_retained(self):
        self.chain()
        old = copy.deepcopy(knowledge.get(self.project, 'THEOREM-1'))
        (self.project / 'literature/paper.txt').unlink()
        self.assertEqual(self.node_status('OBLIGATION-1')['validity'], 'PENDING_REVALIDATION')
        self.assertEqual(knowledge.get(self.project, 'THEOREM-1')['spec_sha256'], old['spec_sha256'])

    def test_manual_invalidation_propagates_and_cannot_be_cleared_by_refresh(self):
        self.chain()
        knowledge.invalidate(self.project, 'PAPER-1', 'Original paper version has been withdrawn')
        self.assertEqual(self.node_status('OBLIGATION-1')['validity'], 'PENDING_REVALIDATION')
        knowledge.refresh(self.project)
        self.assertEqual(self.node_status('PAPER-1')['validity'], 'PENDING_REVALIDATION')
        self.assertIn('withdrawn', json.dumps(knowledge.get(self.project, 'PAPER-1'), ensure_ascii=False))

    def test_reimport_is_idempotent_without_artificial_revision_or_audit_event(self):
        spec = self.record()
        first = self.register(spec)
        path = self.project / 'research/discovery/CLAIM_GRAPH.json'
        before = path.read_bytes()
        again = self.register(copy.deepcopy(spec))
        self.assertEqual(again['revision'], first['revision'])
        self.assertEqual(path.read_bytes(), before)

    def test_revision_history_does_not_silently_rebind_dependent_pins(self):
        self.chain()
        before = copy.deepcopy(knowledge.get(self.project, 'THEOREM-1')['dependency_pins'])
        old = copy.deepcopy(knowledge.get(self.project, 'PAPER-1'))
        spec = self.record(statement='Explicitly revised source interpretation with unchanged frozen goal.')
        revised = self.register(spec)
        self.assertEqual(revised['revision'], old['revision'] + 1)
        self.assertEqual(knowledge.get(self.project, 'THEOREM-1')['dependency_pins'], before)
        self.assertEqual(knowledge.get(self.project, 'PAPER-1', old['revision'])['spec'], old['spec'])
        self.assertEqual(self.node_status('THEOREM-1')['validity'], 'PENDING_REVALIDATION')

    def test_transitive_trace_and_impact_include_only_reachable_nodes(self):
        self.chain()
        self.register(self.record('UNRELATED', 'failed_path'))
        trace = json.dumps(knowledge.trace(self.project, 'OBLIGATION-1'), ensure_ascii=False)
        impact = json.dumps(knowledge.impact(self.project, 'PAPER-1'), ensure_ascii=False)
        for node_id in ('PAPER-1', 'THEOREM-1', 'EVIDENCE-1', 'OBLIGATION-1'):
            self.assertIn(node_id, trace)
            self.assertIn(node_id, impact)
        self.assertNotIn('UNRELATED', trace)
        self.assertNotIn('UNRELATED', impact)

    def test_failed_path_scope_is_preserved_without_rejecting_the_global_goal(self):
        before = self.files()
        self.register(self.record('FAIL-1', 'failed_path', metadata={
            'failure_scope': 'Only the local integer lemma under the stated hypotheses',
            'route_blocked': False, 'failure_class': 'COUNTEREXAMPLE'}))
        item = knowledge.get(self.project, 'FAIL-1')
        self.assertFalse(item['spec']['metadata']['route_blocked'])
        for relative in ('GOAL.md', 'AGENTS.md', 'research/STATE.json'):
            self.assertEqual((self.project / relative).read_bytes(), before[relative])

    def test_immutable_project_state_budget_and_scientific_sources_survive_mutations(self):
        ledger = self.root / 'state/routes/example.json'
        ledger.parent.mkdir(parents=True)
        ledger.write_text('{"spent_rounds": 19, "budget": 20}', encoding='utf8')
        before, old_ledger = self.files(), ledger.read_bytes()
        self.register()
        knowledge.invalidate(self.project, 'PAPER-1', 'Recheck exact origin')
        knowledge.refresh(self.project)
        for relative, original in before.items():
            self.assertEqual((self.project / relative).read_bytes(), original, relative)
        self.assertEqual(ledger.read_bytes(), old_ledger)

    def test_wrong_source_hash_is_rejected_without_creating_storage(self):
        spec = self.record()
        spec['sources'][0]['sha256'] = '0' * 64
        before = self.files()
        with self.assertRaises(ValueError):
            self.register(spec)
        self.assertEqual(self.files(), before)
        self.assertFalse((self.project / 'research/discovery').exists())

    def test_out_of_range_line_locators_are_rejected_atomically(self):
        for locator in ('lines:0-1', 'lines:3-2', 'lines:1-200', 'lines:1-0'):
            with self.subTest(locator=locator):
                before = self.files()
                with self.assertRaises(ValueError):
                    self.register(locator=locator)
                self.assertEqual(self.files(), before)

    def test_missing_or_unsafe_dependency_fails_without_mutating_existing_graph(self):
        self.register()
        for dependencies in (['UNKNOWN'], ['PAPER-1', 'PAPER-1'], ['../escape'], ['SELF']):
            with self.subTest(dependencies=dependencies):
                before = self.files()
                with self.assertRaises(ValueError):
                    self.register(self.record('SELF', 'theorem', dependencies=dependencies))
                self.assertEqual(self.files(), before)

    def test_cycle_introduced_by_revision_is_rejected_atomically(self):
        self.chain()
        before = self.files()
        with self.assertRaises(ValueError):
            self.register(dependencies=['OBLIGATION-1'])
        self.assertEqual(self.files(), before)

    def test_invalid_node_schema_never_writes_storage(self):
        for updates in ({'schema_version': True}, {'schema_version': 2}, {'id': '../escape'},
                        {'kind': 'approved_theorem'}, {'title': ''}, {'statement': ''},
                        {'sources': []}, {'metadata': []}):
            with self.subTest(updates=updates):
                before = self.files()
                spec = self.record()
                spec.update(updates)
                with self.assertRaises(ValueError):
                    self.register(spec)
                self.assertEqual(self.files(), before)

    def test_unsafe_source_paths_and_control_records_cannot_certify_memory(self):
        self.put('research/ROUND_REVIEW.json', {'result': 'CLAIMED'})
        self.put('research/supervision/report.md', 'Controller decision is not scientific evidence.\n')
        for relative in ('../outside.txt', 'C:/Windows/win.ini', 'proofs/../research/STATE.json',
                         'research/STATE.json', 'research/ROUND_REVIEW.json',
                         'research/supervision/report.md', 'GOAL.md', 'AGENTS.md'):
            with self.subTest(path=relative):
                before = self.files()
                with self.assertRaises((ValueError, OSError)):
                    self.register(path=relative, locator='lines:1-1')
                self.assertEqual(self.files(), before)

    def test_internal_source_symlink_is_rejected(self):
        link = self.project / 'literature/link.txt'
        try:
            link.symlink_to(self.project / 'literature/paper.txt')
        except (OSError, NotImplementedError) as exc:
            self.skipTest('Host cannot create symbolic links: ' + str(exc))
        with self.assertRaises((ValueError, OSError)):
            self.register(path='literature/link.txt', locator='lines:1-1')

    @unittest.skipUnless(os.name == 'nt', 'Windows junction semantics')
    def test_source_directory_junction_is_rejected_even_when_it_points_inside_project(self):
        import _winapi
        junction = self.project / 'proofs/junction'
        _winapi.CreateJunction(str(self.project / 'literature'), str(junction))
        self.addCleanup(lambda: junction.rmdir() if junction.exists() else None)
        with self.assertRaises((ValueError, OSError)):
            self.register(path='proofs/junction/paper.txt', locator='lines:1-1')

    def test_atomic_write_failure_preserves_existing_graph_and_history(self):
        self.register()
        before = self.files()
        with mock.patch.object(configuration.os, 'replace', side_effect=OSError('injected disk failure')):
            with self.assertRaises(OSError):
                self.register(statement='Revised interpretation that must not be half applied.')
        self.assertEqual(self.files(), before)

    def test_refresh_is_idempotent_and_readonly_status_does_not_append_events(self):
        self.chain()
        self.put('literature/paper.txt', 'Corrected upstream source.\n')
        knowledge.refresh(self.project)
        before = self.files()
        knowledge.status(self.project)
        knowledge.trace(self.project, 'OBLIGATION-1')
        knowledge.impact(self.project, 'PAPER-1')
        knowledge.refresh(self.project)
        self.assertEqual(self.files(), before)

    def test_existing_registries_are_indexed_without_promoting_legacy_statuses(self):
        legacy = {
            'research/CLAIM_INDEX.json': {'schema_version': 1, 'claims': [{
                'id': 'OLD-CL-1', 'statement': 'A historical candidate claim',
                'status': 'PROVED_SELF_CONTAINED', 'independent_review': 'PENDING',
                'evidence': ['proofs/derivation.md'], 'blocking_obligations': ['OLD-OB-1']}]},
            'research/CLAIM_REGISTER.json': {'version': '2.0', 'claims': [{
                'id': 'OLD-CL-2', 'claim': 'Historical register candidate',
                'status': 'HISTORICAL_TO_REVERIFY', 'evidence_ids': [], 'independent_review': False}]},
            'research/PROOF_OBLIGATIONS.json': {'schema_version': 1, 'obligations': [{
                'id': 'OLD-OB-1', 'title': 'Original security proof obligation',
                'status': 'OPEN', 'blocking': True, 'evidence': ['proofs/derivation.md']}]},
            'literature/SEED_PAPERS.json': {'papers': [{'id': 'OLD-P1', 'title': 'Seed metadata',
                'full_text_status': 'FULL_TEXT_UNCHECKED', 'theorem_level_overlap': 'NOT_AUDITED'}]},
            'literature/seed_sources.json': {'sources': [{'id': 'OLD-P2', 'title': 'Historical seed source',
                'status': 'HISTORICAL_BIBLIOGRAPHY_UNVERIFIED'}]},
            'research/FAILED_PATHS.md': '# Failed paths\n\n## OLD-FP-1\nA local counterexample only; the global goal remains open.\n',
        }
        for relative, content in legacy.items():
            self.put(relative, content)
        before = self.files()
        knowledge.refresh(self.project)
        current = knowledge.status(self.project)
        payload = json.dumps(current, ensure_ascii=False)
        for marker in ('OLD-CL-1', 'OLD-CL-2', 'OLD-OB-1', 'OLD-P1', 'OLD-P2', 'OLD-FP-1'):
            self.assertIn(marker, payload)
        self.assertEqual(current['claim_nodes'], [])
        for node in current['memory_nodes']:
            self.assertEqual(node['verification_status'], 'UNVERIFIED_SOURCE')
        for relative, content in before.items():
            self.assertEqual((self.project / relative).read_bytes(), content, relative)

    def test_search_is_bounded_and_kind_filter_does_not_change_graph(self):
        self.chain()
        before = self.files()
        result = knowledge.search(self.project, 'Offline research source', kind='theorem', limit=1)
        payload = json.dumps(result, ensure_ascii=False)
        self.assertIn('THEOREM-1', payload)
        self.assertNotIn('OBLIGATION-1', payload)
        self.assertEqual(self.files(), before)

    def test_claim_and_memory_namespaces_prevent_ambiguous_identifier_rebinding(self):
        self.legacy_claim('C-1')
        self.register(self.record('C-1', 'theorem'))
        with self.assertRaises(ValueError):
            knowledge.get(self.project, 'C-1')
        self.assertEqual(knowledge.get(self.project, 'memory:C-1')['spec']['kind'], 'theorem')
        self.assertEqual(knowledge.get(self.project, 'claim:C-1')['spec']['problem_id'], 'P-1')

    def test_trace_and_impact_cross_memory_and_existing_claim_dependency_edges(self):
        self.register()
        self.register(self.record('THEOREM-1', 'theorem', dependencies=['PAPER-1']))
        self.legacy_claim('C-1', knowledge_dependencies=['THEOREM-1'])
        self.legacy_claim('C-2', dependencies=['C-1'])
        trace = json.dumps(knowledge.trace(self.project, 'claim:C-2'), ensure_ascii=False)
        impact = json.dumps(knowledge.impact(self.project, 'memory:PAPER-1'), ensure_ascii=False)
        for node_id in ('PAPER-1', 'THEOREM-1', 'C-1', 'C-2'):
            with self.subTest(node=node_id):
                self.assertIn(node_id, trace)
                self.assertIn(node_id, impact)

    def test_stored_spec_tampering_is_not_treated_as_current_source_bound_memory(self):
        self.register()
        path = self.project / 'research/discovery/CLAIM_GRAPH.json'
        graph = json.loads(path.read_text(encoding='utf8'))
        graph['memory']['nodes'][0]['spec']['statement'] = 'Forged conclusion without a matching revision digest.'
        configuration.atomic_json(path, graph)
        before = path.read_bytes()
        self.assertEqual(self.node_status('PAPER-1')['validity'], 'PENDING_REVALIDATION')
        self.assertEqual(path.read_bytes(), before)

    def test_duplicate_stored_memory_ids_fail_closed_without_repairing_history(self):
        self.register()
        path = self.project / 'research/discovery/CLAIM_GRAPH.json'
        graph = json.loads(path.read_text(encoding='utf8'))
        graph['memory']['nodes'].append(copy.deepcopy(graph['memory']['nodes'][0]))
        configuration.atomic_json(path, graph)
        before = path.read_bytes()
        with self.assertRaises(ValueError):
            knowledge.status(self.project)
        self.assertEqual(path.read_bytes(), before)

    def test_restoring_original_source_bytes_restores_freshness_without_clearing_explicit_revocation(self):
        self.chain()
        path = self.project / 'literature/paper.txt'
        original = path.read_bytes()
        path.write_text('Temporary divergent source bytes.\n', encoding='utf8')
        self.assertEqual(self.node_status('OBLIGATION-1')['validity'], 'PENDING_REVALIDATION')
        path.write_bytes(original)
        self.assertEqual(self.node_status('OBLIGATION-1')['validity'], 'SOURCE_BOUND')
        knowledge.invalidate(self.project, 'PAPER-1', 'Retraction survives restoration of identical bytes')
        knowledge.refresh(self.project)
        self.assertEqual(self.node_status('PAPER-1')['validity'], 'PENDING_REVALIDATION')
        self.assertEqual(self.node_status('OBLIGATION-1')['validity'], 'PENDING_REVALIDATION')

    def test_explicit_revalidation_creates_revision_and_preserves_revoked_history_and_old_pins(self):
        self.chain()
        knowledge.invalidate(self.project, 'PAPER-1', 'Retraction requires a new source interpretation')
        old = copy.deepcopy(knowledge.get(self.project, 'PAPER-1'))
        pins = copy.deepcopy(knowledge.get(self.project, 'THEOREM-1')['dependency_pins'])
        revised = self.register()
        self.assertEqual(revised['revision'], old['revision'] + 1)
        self.assertEqual(self.node_status('PAPER-1')['validity'], 'SOURCE_BOUND')
        self.assertEqual(self.node_status('THEOREM-1')['validity'], 'PENDING_REVALIDATION')
        self.assertEqual(knowledge.get(self.project, 'THEOREM-1')['dependency_pins'], pins)
        historical = knowledge.get(self.project, 'PAPER-1', old['revision'])
        self.assertEqual(historical['invalidated'], old['invalidated'])

    def test_automatic_source_refresh_and_later_restore_never_rebind_manual_dependency_pins(self):
        knowledge.refresh(self.project)
        source = next(n for n in knowledge.status(self.project)['memory_nodes']
                      if n['metadata'].get('source_path') == 'literature/paper.txt'
                      and n['metadata'].get('index_role') == 'source_file')
        self.register(self.record('THEOREM-1', 'theorem', 'proofs/derivation.md', 'lines:1-2',
                                  dependencies=[source['id']]))
        pins = copy.deepcopy(knowledge.get(self.project, 'THEOREM-1')['dependency_pins'])
        path = self.project / 'literature/paper.txt'
        original = path.read_bytes()
        path.write_text('A changed source, awaiting revalidation.\n', encoding='utf8')
        knowledge.refresh(self.project)
        self.assertGreater(knowledge.get(self.project, source['id'])['revision'], source['revision'])
        self.assertEqual(self.node_status('THEOREM-1')['validity'], 'PENDING_REVALIDATION')
        path.write_bytes(original)
        knowledge.refresh(self.project)
        self.assertEqual(self.node_status('THEOREM-1')['validity'], 'PENDING_REVALIDATION')
        self.assertEqual(knowledge.get(self.project, 'THEOREM-1')['dependency_pins'], pins)

    def test_legacy_claim_evidence_links_are_traceable_and_proof_changes_propagate(self):
        self.put('research/CLAIM_INDEX.json', {'schema_version': 1, 'claims': [{
            'id': 'LEGACY-C1', 'statement': 'A historical theorem with an exact local derivation',
            'status': 'CONDITIONAL', 'evidence': ['proofs/derivation.md']}]})
        knowledge.refresh(self.project)
        current = knowledge.status(self.project)
        claim = next(n for n in current['memory_nodes']
                     if n['metadata'].get('original_id') == 'LEGACY-C1')
        trace = knowledge.trace(self.project, claim['key'])
        self.assertTrue(any(n.get('path') == 'proofs/derivation.md' for n in trace['nodes']),
                        'Legacy evidence paths must be actual graph edges, not only metadata text')
        self.put('proofs/derivation.md', '# Revised local proof\nIts exact statement changed.\n')
        self.assertEqual(self.node_status(claim['id'])['validity'], 'PENDING_REVALIDATION')

    def test_legacy_obligation_evidence_links_propagate_missing_sources(self):
        self.put('research/PROOF_OBLIGATIONS.json', {'schema_version': 1, 'obligations': [{
            'id': 'LEGACY-O1', 'title': 'Open obligation tied to an existing derivation',
            'status': 'OPEN', 'evidence': ['proofs/derivation.md']}]})
        knowledge.refresh(self.project)
        obligation = next(n for n in knowledge.status(self.project)['memory_nodes']
                          if n['metadata'].get('original_id') == 'LEGACY-O1')
        (self.project / 'proofs/derivation.md').unlink()
        self.assertEqual(self.node_status(obligation['id'])['validity'], 'PENDING_REVALIDATION')

    def test_legacy_evidence_id_links_propagate_and_declared_digest_mismatch_survives_refresh(self):
        self.put('research/EVIDENCE.json', {'version': '2.0', 'items': [{
            'id': 'EV-1', 'path': 'proofs/derivation.md',
            'sha256': hash_file(self.project / 'proofs/derivation.md'),
            'review_status': 'SELF_RECORDED_ONLY'}]})
        self.put('research/CLAIM_REGISTER.json', {'version': '2.0', 'claims': [{
            'id': 'LEGACY-C1', 'claim': 'Historical candidate using an evidence ledger',
            'status': 'CONDITIONAL', 'evidence_ids': ['EV-1'], 'independent_review': False}]})
        knowledge.refresh(self.project)
        claim = next(n for n in knowledge.status(self.project)['memory_nodes']
                     if n['metadata'].get('original_id') == 'LEGACY-C1')
        trace = knowledge.trace(self.project, claim['key'])
        self.assertTrue(any(n.get('path') == 'proofs/derivation.md' for n in trace['nodes']))
        self.put('proofs/derivation.md', 'A different proof file without an updated evidence ledger digest.\n')
        self.assertEqual(self.node_status(claim['id'])['validity'], 'PENDING_REVALIDATION')
        knowledge.refresh(self.project)
        self.assertEqual(self.node_status(claim['id'])['validity'], 'PENDING_REVALIDATION')
        self.assertEqual(knowledge.status(self.project)['claim_nodes'], [])

    def test_missing_legacy_evidence_is_retained_as_invalid_with_an_explanation(self):
        self.put('research/CLAIM_INDEX.json', {'schema_version': 1, 'claims': [{
            'id': 'LEGACY-MISSING', 'statement': 'A candidate with a missing original proof',
            'evidence': ['proofs/nonexistent-original.md']}]})
        knowledge.refresh(self.project)
        claim = next(n for n in knowledge.status(self.project)['memory_nodes']
                     if n['metadata'].get('original_id') == 'LEGACY-MISSING')
        self.assertEqual(claim['validity'], 'PENDING_REVALIDATION')
        self.assertIn('proofs/nonexistent-original.md', json.dumps(claim, ensure_ascii=False))

    def test_obligation_addresses_relationship_is_traceable_without_certifying_or_invalidating_theorem(self):
        self.put('research/PROOF_OBLIGATIONS.json', {'schema_version': 1, 'obligations': [{
            'id': 'LEGACY-O1', 'title': 'An unresolved original obligation', 'status': 'OPEN'}]})
        self.put('research/CLAIM_INDEX.json', {'schema_version': 1, 'claims': [{
            'id': 'LEGACY-C1', 'statement': 'Candidate addressing an open obligation',
            'status': 'CONDITIONAL', 'blocking_obligations': ['LEGACY-O1']}]})
        knowledge.refresh(self.project)
        nodes = knowledge.status(self.project)['memory_nodes']
        claim = next(n for n in nodes if n['metadata'].get('original_id') == 'LEGACY-C1')
        obligation = next(n for n in nodes if n['metadata'].get('original_id') == 'LEGACY-O1')
        trace = knowledge.trace(self.project, claim['key'])
        self.assertTrue(any(e.get('relation') == 'addresses' and e.get('to') == obligation['key']
                            for e in trace['edges']))
        knowledge.invalidate(self.project, obligation['key'], 'Review the evidence for this obligation')
        self.assertEqual(self.node_status(claim['id'])['validity'], 'SOURCE_BOUND')
        self.assertEqual(self.node_status(obligation['id'])['validity'], 'PENDING_REVALIDATION')

    def test_corrupt_source_bindings_refs_and_provenance_cannot_become_source_bound(self):
        self.chain()
        graph_path = self.project / 'research/discovery/CLAIM_GRAPH.json'
        original = json.loads(graph_path.read_text(encoding='utf8'))
        cases = {
            'remove_bindings': lambda n: n.pop('source_bindings'),
            'empty_bindings': lambda n: n.update(source_bindings={}),
            'unrelated_source': lambda n: n.update(source_bindings={
                'proofs/derivation.md': hash_file(self.project / 'proofs/derivation.md')}),
            'remove_refs': lambda n: n.pop('sources'),
            'empty_refs': lambda n: n.update(sources=[]),
            'changed_locator': lambda n: n['sources'][0].update(locator='lines:1-1'),
            'changed_excerpt': lambda n: n['sources'][0].update(excerpt='Forged original text'),
            'changed_ref_digest': lambda n: n['sources'][0].update(sha256='0' * 64),
            'remove_provenance_digest': lambda n: n.pop('provenance_sha256'),
            'changed_provenance_digest': lambda n: n.update(provenance_sha256='0' * 64),
        }
        for name, mutate in cases.items():
            with self.subTest(corruption=name):
                graph = copy.deepcopy(original)
                node = next(n for n in graph['memory']['nodes'] if n['id'] == 'PAPER-1')
                mutate(node)
                configuration.atomic_json(graph_path, graph)
                before = self.files()
                self.assert_rejected_or_pending('PAPER-1')
                self.assertEqual(self.files(), before)

    def test_corrupt_dependency_pins_never_rebind_or_restore_source_validity(self):
        self.chain()
        graph_path = self.project / 'research/discovery/CLAIM_GRAPH.json'
        original = json.loads(graph_path.read_text(encoding='utf8'))
        cases = {
            'remove_pins': lambda n: n.pop('dependency_pins'),
            'empty_pins': lambda n: n.update(dependency_pins={}),
            'changed_revision': lambda n: n['dependency_pins']['PAPER-1'].update(revision=99),
            'bool_revision': lambda n: n['dependency_pins']['PAPER-1'].update(revision=True),
            'changed_digest': lambda n: n['dependency_pins']['PAPER-1'].update(spec_sha256='0' * 64),
            'extra_dependency': lambda n: n['dependency_pins'].update(UNKNOWN={
                'revision': 1, 'spec_sha256': '0' * 64}),
        }
        for name, mutate in cases.items():
            with self.subTest(corruption=name):
                graph = copy.deepcopy(original)
                node = next(n for n in graph['memory']['nodes'] if n['id'] == 'THEOREM-1')
                mutate(node)
                configuration.atomic_json(graph_path, graph)
                before = self.files()
                self.assert_rejected_or_pending('THEOREM-1')
                self.assertEqual(self.files(), before)

    def test_outer_identity_and_revision_corruption_fail_closed(self):
        self.register()
        graph_path = self.project / 'research/discovery/CLAIM_GRAPH.json'
        original = json.loads(graph_path.read_text(encoding='utf8'))
        for revision in (True, 0, -1, 1.0, '1', None):
            with self.subTest(revision=revision):
                graph = copy.deepcopy(original)
                graph['memory']['nodes'][0]['revision'] = revision
                configuration.atomic_json(graph_path, graph)
                before = self.files()
                self.assert_rejected_or_pending('PAPER-1')
                self.assertEqual(self.files(), before)
        graph = copy.deepcopy(original)
        graph['memory']['nodes'][0]['id'] = 'FORGED-IDENTITY'
        configuration.atomic_json(graph_path, graph)
        before = self.files()
        self.assert_rejected_or_pending('FORGED-IDENTITY')
        self.assertEqual(self.files(), before)

    def test_deleted_or_edited_revocation_cannot_silently_restore_source_validity(self):
        self.register()
        knowledge.invalidate(self.project, 'PAPER-1', 'The original source is revoked')
        graph_path = self.project / 'research/discovery/CLAIM_GRAPH.json'
        original = json.loads(graph_path.read_text(encoding='utf8'))
        for name, mutate in {
            'delete': lambda n: n.pop('invalidated'),
            'clear': lambda n: n.update(invalidated=None),
            'change_reason': lambda n: n['invalidated'].update(reason='A different unaudited reason'),
        }.items():
            with self.subTest(revocation=name):
                graph = copy.deepcopy(original)
                mutate(graph['memory']['nodes'][0])
                configuration.atomic_json(graph_path, graph)
                before = self.files()
                self.assert_rejected_or_pending('PAPER-1')
                self.assertEqual(self.files(), before)

    def test_malformed_readonly_revisions_and_queries_are_rejected_without_writes(self):
        self.register()
        before = self.files()
        for revision in (True, False, 1.0, '1', 0, -1, [], {}):
            with self.subTest(revision=revision):
                with self.assertRaises(ValueError):
                    knowledge.get(self.project, 'PAPER-1', revision=revision)
                self.assertEqual(self.files(), before)
        for action in (knowledge.get, knowledge.trace, knowledge.impact):
            for node_id in (None, 17, '', []):
                with self.subTest(action=action.__name__, node_id=node_id):
                    with self.assertRaises(ValueError):
                        action(self.project, node_id)
                    self.assertEqual(self.files(), before)
        for query, options in (('', {}), (17, {}), ('paper', {'kind': 'APPROVED'}),
                               ('paper', {'limit': True}), ('paper', {'limit': 0}),
                               ('paper', {'limit': 201})):
            with self.subTest(query=query, options=options):
                with self.assertRaises(ValueError):
                    knowledge.search(self.project, query, **options)
                self.assertEqual(self.files(), before)

    def test_historical_reads_preserve_old_provenance_and_never_rewrite_history(self):
        first = self.register()
        self.register(statement='Explicit second interpretation, leaving the first version intact.')
        path = self.project / 'research/discovery/CLAIM_GRAPH.json'
        before = self.files()
        old = knowledge.get(self.project, 'PAPER-1', first['revision'])
        self.assertEqual(old['spec'], first['spec'])
        self.assertEqual(old['sources'], first['sources'])
        old['spec']['statement'] = 'Mutation of a caller-owned result'
        old['source_bindings'].clear()
        knowledge.status(self.project)
        knowledge.trace(self.project, 'PAPER-1')
        knowledge.impact(self.project, 'PAPER-1')
        again = knowledge.get(self.project, 'PAPER-1', first['revision'])
        self.assertEqual(again['spec'], first['spec'])
        self.assertEqual(again['source_bindings'], first['source_bindings'])
        self.assertEqual(self.files(), before)
        self.assertEqual(json.loads(path.read_text(encoding='utf8'))['memory']['nodes'][0]['history'][0]['spec'],
                         first['spec'])

    def test_corrupted_historical_spec_or_provenance_is_rejected_or_explicitly_marked_corrupt(self):
        self.register()
        self.register(statement='Second explicit source interpretation')
        graph_path = self.project / 'research/discovery/CLAIM_GRAPH.json'
        original = json.loads(graph_path.read_text(encoding='utf8'))
        cases = {
            'statement': lambda n: n['spec'].update(statement='Forged historical original statement'),
            'source_bindings': lambda n: n['source_bindings'].clear(),
            'dependency_pins': lambda n: n.pop('dependency_pins'),
            'provenance': lambda n: n.pop('provenance_sha256'),
        }
        for name, mutate in cases.items():
            with self.subTest(corruption=name):
                graph = copy.deepcopy(original)
                mutate(graph['memory']['nodes'][0]['history'][0])
                configuration.atomic_json(graph_path, graph)
                before = self.files()
                try:
                    historical = knowledge.get(self.project, 'PAPER-1', revision=1)
                except (ValueError, KeyError, TypeError, AttributeError):
                    pass
                else:
                    self.assertIn('CORRUPT', str(historical.get('validity')))
                self.assertEqual(self.files(), before)

    def test_malformed_stored_graph_schema_versions_fail_closed_without_writes(self):
        self.register()
        graph_path = self.project / 'research/discovery/CLAIM_GRAPH.json'
        original = json.loads(graph_path.read_text(encoding='utf8'))
        for scope in ('graph', 'memory'):
            for version in (True, 1.0, '1', None, 2):
                with self.subTest(scope=scope, schema_version=version):
                    graph = copy.deepcopy(original)
                    target = graph if scope == 'graph' else graph['memory']
                    target['schema_version'] = version
                    configuration.atomic_json(graph_path, graph)
                    before = self.files()
                    with self.assertRaises(ValueError):
                        knowledge.status(self.project)
                    self.assertEqual(self.files(), before)

    def test_missing_or_inconsistent_current_history_cannot_silently_discard_prior_versions(self):
        self.register()
        self.register(statement='Second explicit source interpretation')
        graph_path = self.project / 'research/discovery/CLAIM_GRAPH.json'
        original = json.loads(graph_path.read_text(encoding='utf8'))
        cases = {
            'delete_history': lambda n: n.pop('history'),
            'empty_history': lambda n: n.update(history=[]),
            'wrong_history_type': lambda n: n.update(history={}),
            'duplicate_revision': lambda n: n['history'].append(copy.deepcopy(n['history'][0])),
            'wrong_historical_id': lambda n: n['history'][0].update(id='DIFFERENT-NODE'),
            'wrong_historical_revision': lambda n: n['history'][0].update(revision=17),
        }
        for name, mutate in cases.items():
            with self.subTest(history=name):
                graph = copy.deepcopy(original)
                mutate(graph['memory']['nodes'][0])
                configuration.atomic_json(graph_path, graph)
                before = self.files()
                self.assert_rejected_or_pending('PAPER-1')
                self.assertEqual(self.files(), before)


class LegacyKnowledgeLinksTests(unittest.TestCase):
    def source(self, node_id='SOURCE', path='proofs/argument.md', digest='a' * 64):
        return {'id': node_id, 'kind': 'evidence', 'sources': [{'path': path, 'sha256': digest}],
                'dependencies': [], 'metadata': {'index_role': 'source_file', 'source_path': path}}

    def entry(self, node_id='CLAIM', kind='theorem', original_id='C-1', **row):
        return {'id': node_id, 'kind': kind, 'dependencies': [], 'metadata': {
            'index_role': 'registry_entry', 'original_id': original_id,
            'original_record': row, 'registry_field': 'claims', 'source_path': 'research/CLAIM_INDEX.json'}}

    def test_pure_linker_does_not_mutate_input_and_orders_sources_before_entries(self):
        records = [self.entry(evidence=['proofs/argument.md']), self.source()]
        original = copy.deepcopy(records)
        linked, errors = link_records(records)
        self.assertEqual(records, original)
        self.assertEqual(errors, [])
        self.assertEqual([n['id'] for n in linked], ['SOURCE', 'CLAIM'])
        self.assertEqual(linked[1]['dependencies'], ['SOURCE'])

    def test_evidence_ids_connect_to_legacy_evidence_and_obligations_remain_relationships(self):
        records = [self.entry(evidence_ids=['EV-1'], blocking_obligations=['O-1']),
                   self.entry('EVIDENCE', 'evidence', 'EV-1', path='proofs/argument.md'),
                   self.entry('OBLIGATION', 'obligation', 'O-1'), self.source()]
        linked, errors = link_records(records)
        self.assertEqual(errors, [])
        by_id = {n['id']: n for n in linked}
        self.assertEqual(by_id['CLAIM']['dependencies'], ['EVIDENCE'])
        self.assertEqual(by_id['EVIDENCE']['dependencies'], ['SOURCE'])
        self.assertNotIn('OBLIGATION', by_id['CLAIM']['dependencies'])
        self.assertEqual(by_id['CLAIM']['metadata']['related_nodes'], [
            {'target': 'OBLIGATION', 'relation': 'addresses'}])

    def test_missing_and_ambiguous_evidence_are_not_silently_selected(self):
        records = [self.entry(evidence=['proofs/missing.md'], evidence_ids=['EV-1']),
                   self.entry('EV-A', 'evidence', 'EV-1'), self.entry('EV-B', 'evidence', 'EV-1')]
        linked, errors = link_records(records)
        claim = next(n for n in linked if n['id'] == 'CLAIM')
        self.assertEqual(claim['dependencies'], [])
        self.assertEqual(claim['metadata']['missing_dependencies'], [
            'proofs/missing.md', 'evidence_id:EV-1'])
        self.assertTrue(any('Ambiguous' in e for e in errors))
        self.assertTrue(any('Missing' in e for e in errors))

    def test_declared_hash_mismatch_and_unsafe_paths_are_retained_as_missing_dependencies(self):
        records = [self.entry(path='proofs/argument.md', sha256='b' * 64,
                              evidence_paths=['proofs/../research/STATE.json']), self.source()]
        linked, errors = link_records(records)
        claim = next(n for n in linked if n['id'] == 'CLAIM')
        self.assertIn('digest:proofs/argument.md', claim['metadata']['missing_dependencies'])
        self.assertIn('unsafe:proofs/../research/STATE.json', claim['metadata']['missing_dependencies'])
        self.assertEqual(len(errors), 2)

    def test_cyclic_declared_evidence_is_recorded_without_creating_a_cycle(self):
        records = [self.entry('EV-A', 'evidence', 'A', evidence_ids=['B']),
                   self.entry('EV-B', 'evidence', 'B', evidence_ids=['A'])]
        linked, errors = link_records(records)
        self.assertTrue(any('Cyclic' in e for e in errors))
        by_id = {n['id']: n for n in linked}
        self.assertEqual(by_id['EV-A']['dependencies'], ['EV-B'])
        self.assertEqual(by_id['EV-B']['dependencies'], [])
        self.assertIn('cycle:evidence_id:A', by_id['EV-B']['metadata']['missing_dependencies'])

    def test_duplicate_automatic_node_ids_fail_closed_without_changing_input(self):
        records = [self.source(), self.source()]
        original = copy.deepcopy(records)
        with self.assertRaises(ValueError):
            link_records(records)
        self.assertEqual(records, original)


if __name__ == '__main__':
    unittest.main()
