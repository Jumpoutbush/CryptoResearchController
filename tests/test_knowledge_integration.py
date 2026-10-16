"""Offline research/supervision retrieval and accepted-round indexing boundaries."""
import copy
import json
import unittest
from unittest import mock

import route_budget
import runner
import runner_core
import supervision
import test_discovery as discovery_fixtures
import test_supervision as supervision_fixtures
import test_supervision_runner as runner_fixtures
from engine import claim_graph, discovery_scheduler, knowledge_graph


class KnowledgePromptIntegrationTests(unittest.TestCase):
    setUp = supervision_fixtures.SupervisionTests.setUp
    put = supervision_fixtures.SupervisionTests.put
    read = supervision_fixtures.SupervisionTests.read
    digest = staticmethod(supervision_fixtures.SupervisionTests.digest)
    enable = supervision_fixtures.SupervisionTests.enable
    proposal = supervision_fixtures.SupervisionTests.proposal

    def test_new_knowledge_and_source_invalidation_reach_research_and_supervision(self):
        self.put('literature/context-source.txt', 'The source states an exact precondition for a candidate lemma.')
        knowledge_graph.import_record(self.project, {
            'schema_version': 1, 'id': 'K-context', 'kind': 'theorem',
            'title': 'Exact precondition fixture',
            'statement': 'MEMORY-PRIMARY-LEMMA requires its original exact precondition.',
            'sources': [{'path': 'literature/context-source.txt', 'locator': 'lines:1'}],
        }, 'Register an isolated context fixture')
        first = runner_core.build_prompt(self.project, self.read('research/STATE.json'), 'first', 'critical')
        self.assertIn('MEMORY-PRIMARY-LEMMA', first)
        self.put('literature/context-source.txt', 'A corrected source withdraws the original precondition.')
        second = runner_core.build_prompt(self.project, self.read('research/STATE.json'), 'second', 'critical')
        self.assertIn('memory:K-context', second)
        self.assertIn('SOURCE_CHANGED:literature/context-source.txt', second)
        self.assertIn('PENDING_REVALIDATION', second)
        self.enable()
        observed = {}

        def execute(controller, project, review_dir, prompt, policy):
            observed['request'] = json.loads((review_dir / 'input.json').read_text(encoding='utf-8-sig'))
            observed['prompt'] = prompt
            return self.proposal(controller, project, review_dir, prompt, policy)

        # Only inspect the synthetic legacy request/transaction; no real backend
        # is enabled and this guard mock is not an isolation certification.
        with mock.patch.object(supervision, '_require_legacy_backend'), \
             mock.patch.object(supervision, '_execute', side_effect=execute) as child:
            result = supervision.maybe_supervise(self.root, self.project, self.ledger, force=True)
        self.assertTrue(result['proceed'], result)
        child.assert_called_once()
        self.assertIn('knowledge_context', observed['request'])
        self.assertIn('memory:K-context', observed['request']['knowledge_context'])
        self.assertIn('SOURCE_CHANGED:literature/context-source.txt', observed['request']['knowledge_context'])
        self.assertIn('MEMORY-PRIMARY-LEMMA', observed['prompt'])


class KnowledgeRunnerIntegrationTests(unittest.TestCase):
    setUp = runner_fixtures.SupervisionRunnerTests.setUp
    current = runner_fixtures.SupervisionRunnerTests.current
    impact = runner_fixtures.SupervisionRunnerTests.impact
    complete = runner_fixtures.SupervisionRunnerTests.complete
    advance = runner_fixtures.SupervisionRunnerTests.advance

    def test_accepted_round_indexes_after_discovery_finalize_before_supervision(self):
        order = []
        original_refresh = knowledge_graph.refresh

        def finalize(project, accepted, run_id=None):
            self.assertTrue(accepted)
            self.assertEqual(run_id, 'accepted-1')
            order.append('discovery-finalize')

        def refresh(project):
            order.append('knowledge-index')
            self.assertEqual(self.current()['last_run'], 'accepted-1')
            self.assertEqual(self.epoch['effective_rounds'], 1)
            before = {p.relative_to(self.project).as_posix(): p.read_bytes()
                      for p in self.project.rglob('*')
                      if p.is_file() and not p.relative_to(self.project).as_posix().startswith('research/discovery/')}
            result = original_refresh(project)
            after = {rel: (self.project / rel).read_bytes() for rel in before}
            self.assertEqual(before, after)
            return result

        def supervise(controller, project, ledger, *, budget_reason=None):
            if not order:
                order.append('preflight-supervision')
            else:
                order.append('postacceptance-supervision')
                graph = claim_graph.load(project)
                self.assertTrue(graph.get('memory', {}).get('nodes'))
                self.assertTrue(any('proofs/new.md' in n['source_bindings'] for n in graph['memory']['nodes']))
            return {'status': 'not_due', 'proceed': True}

        def child(command):
            order.append('research')
            return self.complete()

        with mock.patch.object(supervision, 'maybe_supervise', side_effect=supervise), \
             mock.patch.object(runner, 'run_child', side_effect=child), \
             mock.patch.object(discovery_scheduler, 'finalize_wrapper', side_effect=finalize), \
             mock.patch.object(knowledge_graph, 'refresh', side_effect=refresh):
            self.assertEqual(self.advance(), (0, 'COUNTED_RESEARCH_ROUND'))
        self.assertEqual(order, ['preflight-supervision', 'research', 'discovery-finalize',
                                 'knowledge-index', 'postacceptance-supervision'])
        self.assertEqual(self.current()['last_run'], 'accepted-1')
        self.assertEqual(route_budget.read_json(self.path)['epochs'][-1]['effective_rounds'], 1)
        status = route_budget.read_json(self.root / 'logs/subject/latest-status.json')
        self.assertTrue(status['wrapper_accepted'])
        self.assertEqual(status['knowledge_index']['status'], 'refreshed')

    def test_index_failure_keeps_accepted_science_and_budget_and_blocks_post_supervision(self):
        with mock.patch.object(supervision, 'maybe_supervise',
                               return_value={'status': 'not_due', 'proceed': True}) as reviewed, \
             mock.patch.object(runner, 'run_child', side_effect=lambda command: self.complete()), \
             mock.patch.object(knowledge_graph, 'refresh', side_effect=OSError('offline index storage failure')):
            self.assertEqual(self.advance(), (3, 'KNOWLEDGE_INDEX_FAILED'))
        reviewed.assert_called_once()
        self.assertEqual(self.current()['last_run'], 'accepted-1')
        self.assertTrue((self.project / 'proofs/new.md').is_file())
        self.assertEqual(self.epoch['effective_rounds'], 1)
        self.assertEqual(route_budget.read_json(self.path)['epochs'][-1]['effective_rounds'], 1)
        self.assertFalse((self.root / 'state/failed_runs').exists())
        status = route_budget.read_json(self.root / 'logs/subject/latest-status.json')
        self.assertTrue(status['wrapper_accepted'])
        self.assertEqual(status['route_outcome'], 'COUNTED_RESEARCH_ROUND')
        self.assertEqual(status['knowledge_index']['status'], 'failed')
        self.assertEqual(status['knowledge_index']['error'], 'offline index storage failure')

    def test_rejected_round_does_not_index_unaccepted_research(self):
        with mock.patch.object(supervision, 'maybe_supervise',
                               return_value={'status': 'not_due', 'proceed': True}), \
             mock.patch.object(runner, 'run_child', return_value=5), \
             mock.patch.object(knowledge_graph, 'refresh') as indexed:
            self.assertEqual(self.advance(), (5, 'NATIVE_CORE_FAILED exit_code=5'))
        indexed.assert_not_called()
        self.assertEqual(self.epoch['effective_rounds'], 0)
        self.assertIsNone(self.current()['last_run'])


class CompiledObligationProjectionTests(unittest.TestCase):
    setUp = discovery_fixtures.DiscoveryTests.setUp
    tearDown = discovery_fixtures.DiscoveryTests.tearDown
    put = discovery_fixtures.DiscoveryTests.put
    claim = discovery_fixtures.DiscoveryTests.claim

    def test_compiled_obligation_projects_into_trace_without_closing_its_proof_gate(self):
        self.claim()
        graph_before = claim_graph.load(self.project)
        traced = knowledge_graph.trace(self.project, 'claim:C-1')
        expected = 'obligation:P-1@1:O-1'
        obligations = [n for n in traced['nodes'] if n['key'] == expected]
        self.assertEqual(len(obligations), 1)
        self.assertEqual(claim_graph.status(self.project)['claims'][0]['proof_status'], 'CANDIDATE')
        self.assertFalse(claim_graph.status(self.project)['claims'][0]['accepted_contribution'])
        self.assertEqual(claim_graph.load(self.project), graph_before)


class HistoricalTraceIntegrationTests(unittest.TestCase):
    setUp = discovery_fixtures.DiscoveryTests.setUp
    tearDown = discovery_fixtures.DiscoveryTests.tearDown
    put = discovery_fixtures.DiscoveryTests.put
    claim = discovery_fixtures.DiscoveryTests.claim
    review_proof = discovery_fixtures.DiscoveryTests.review_proof
    novelty_review = discovery_fixtures.DiscoveryTests.novelty_review

    def memory_chain(self):
        self.put('literature/parent.txt', 'OLD-TERM: the original exact precondition.')
        parent = {'schema_version': 1, 'id': 'K-parent', 'kind': 'paper',
                  'title': 'An evolving primary source fixture',
                  'statement': 'OLD-TERM is the recorded original premise.',
                  'sources': [{'path': 'literature/parent.txt', 'locator': 'lines:1'}]}
        knowledge_graph.import_record(self.project, parent, 'Record the original source premise')
        self.put('proofs/middle-source.md', 'A candidate middle lemma with an explicit upstream premise.')
        knowledge_graph.import_record(self.project, {
            'schema_version': 1, 'id': 'K-middle', 'kind': 'theorem',
            'title': 'Dependent middle lemma fixture',
            'statement': 'The candidate middle lemma depends on the recorded primary premise.',
            'sources': [{'path': 'proofs/middle-source.md', 'locator': 'lines:1'}],
            'dependencies': ['K-parent'],
        }, 'Record a candidate lemma and its pinned premise')
        return parent

    def revise_parent(self, spec):
        self.put('literature/parent.txt', 'NEW-TERM: a corrected and different exact precondition.')
        updated = copy.deepcopy(spec)
        updated['statement'] = 'NEW-TERM replaces the former recorded premise.'
        knowledge_graph.import_record(self.project, updated, 'Correct the primary premise with an explicit revision')

    def test_historical_search_and_frozen_trace_keep_retired_terms_and_exact_old_excerpt(self):
        parent = self.memory_chain()
        self.revise_parent(parent)
        retired = knowledge_graph.search(self.project, 'OLD-TERM')
        historical = [n for n in retired['matches'] if n['key'] == 'memory:K-parent@r1']
        self.assertEqual(len(historical), 1)
        self.assertTrue(historical[0]['historical'])
        self.assertEqual(historical[0]['verification_status'], 'UNVERIFIED_SOURCE')
        before = copy.deepcopy(claim_graph.load(self.project))
        traced = knowledge_graph.trace(self.project, 'memory:K-middle')
        live = {n['key']: n for n in traced['nodes']}
        frozen = {n['key']: n for n in traced['frozen_nodes']}
        self.assertEqual(live['memory:K-parent']['revision'], 2)
        self.assertEqual(live['memory:K-middle']['validity'], 'PENDING_REVALIDATION')
        self.assertIn('DEPENDENCY_REVISED:K-parent', live['memory:K-middle']['invalidation_reasons'])
        self.assertEqual(frozen['memory:K-parent@r1']['statement'], parent['statement'])
        self.assertIn('OLD-TERM', frozen['memory:K-parent@r1']['sources'][0]['excerpt'])
        self.assertNotIn('memory:K-parent@r2', frozen)
        self.assertEqual(traced['unresolved_pins'], [])
        self.assertEqual(claim_graph.load(self.project), before)

    def test_actual_claim_chain_traces_old_knowledge_pins_while_scientific_gate_remains_revoked(self):
        parent = self.memory_chain()
        self.claim(knowledge_dependencies=['K-middle']); self.review_proof()
        self.claim('C-2', ['C-1']); self.review_proof('C-2'); self.novelty_review('C-2')
        self.assertTrue(claim_graph.require_theory_claim(self.project, 'C-2')['accepted_contribution'])
        original_claims = copy.deepcopy(claim_graph.load(self.project)['claims'])
        self.revise_parent(parent)
        self.assertEqual(claim_graph.load(self.project)['claims'], original_claims)
        before = copy.deepcopy(claim_graph.load(self.project))
        traced = knowledge_graph.trace(self.project, 'claim:C-2')
        self.assertEqual({n['key'] for n in traced['frozen_nodes']}, {
            'claim:C-2@r1', 'claim:C-1@r1', 'memory:K-middle@r1', 'memory:K-parent@r1'})
        self.assertTrue(all(n['verification_status'] == 'UNVERIFIED_SOURCE' for n in traced['frozen_nodes']))
        self.assertEqual(traced['unresolved_pins'], [])
        self.assertTrue(all(c['proof_status'] == 'PENDING_REVALIDATION'
                            for c in claim_graph.status(self.project)['claims']))
        with self.assertRaises(ValueError): claim_graph.require_theory_claim(self.project, 'C-2')
        self.assertEqual(claim_graph.load(self.project), before)


if __name__ == '__main__': unittest.main()
