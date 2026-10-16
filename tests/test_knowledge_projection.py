"""R06 derived cache invariants, using existing canonical claim importers."""
import copy
import json
import shutil
import unittest
from unittest import mock

import configuration
from engine import claim_graph, knowledge_graph, problem_compiler
import test_knowledge_graph as fixture


class KnowledgeProjectionTests(unittest.TestCase):
    setUp = fixture.KnowledgeGraphTests.setUp
    put = fixture.KnowledgeGraphTests.put
    files = fixture.KnowledgeGraphTests.files
    legacy_claim = fixture.KnowledgeGraphTests.legacy_claim
    record = fixture.KnowledgeGraphTests.record
    register = fixture.KnowledgeGraphTests.register

    def api(self):
        from knowledge import build as projection
        return projection

    def test_derive_is_readonly_and_preserves_canonical_status(self):
        self.legacy_claim(); before = self.files(self.root); original = claim_graph.status(self.project)
        with mock.patch.object(claim_graph, 'save', side_effect=AssertionError('No canonical writes')), \
             mock.patch.object(knowledge_graph, 'refresh', side_effect=AssertionError('No refresh')):
            graph = self.api().derive(self.root, self.project)
        node = next(n for n in graph['nodes'] if n['kind'] == 'CLAIM_REVISION')
        self.assertEqual(node['proof_status'], original['claims'][0]['proof_status'])
        self.assertEqual(node['novelty_status'], original['claims'][0]['novelty_status'])
        self.assertEqual(before, self.files(self.root)); self.assertEqual(original, claim_graph.status(self.project))

    def test_claim_obligation_problem_goal_chain_and_edge_provenance(self):
        self.legacy_claim(); graph = self.api().explain_claim(self.root, self.project, 'C-1')
        kinds = {n['id']: n['kind'] for n in graph['nodes']}
        pairs = {(kinds[e['from']], kinds[e['to']]) for e in graph['edges']}
        self.assertTrue({('CLAIM_REVISION','OBLIGATION'),('OBLIGATION','PROBLEM_VERSION'),
                         ('PROBLEM_VERSION','GOAL')} <= pairs)
        for edge in graph['edges']:
            self.assertTrue({'provenance_kind','source_path','source_sha256','scope','verified_status'} <= set(edge))

    def test_delete_cache_and_rebuild_same_digest_without_source_writes(self):
        self.legacy_claim(); before = self.files()
        one = self.api().build(self.root, self.project)
        path = self.api().cache_path(self.root, self.project); raw = path.read_bytes()
        self.assertEqual(one, self.api().build(self.root, self.project))
        path.unlink(); two = self.api().build(self.root, self.project)
        self.assertEqual(one['graph_sha256'], two['graph_sha256']); self.assertEqual(raw, path.read_bytes())
        self.assertEqual(before, self.files())

    def test_same_claim_name_in_two_projects_has_different_identity(self):
        self.legacy_claim(); other = self.root / 'projects/other'
        shutil.copytree(self.project, other)
        configuration.atomic_json(other / 'PROJECT.json', {'id':'other'})
        one = self.api().derive(self.root, self.project); two = self.api().derive(self.root, other)
        a = {n['id'] for n in one['nodes'] if n['kind'] == 'CLAIM_REVISION'}
        b = {n['id'] for n in two['nodes'] if n['kind'] == 'CLAIM_REVISION'}
        self.assertTrue(a.isdisjoint(b))

    def test_empty_project_has_explicit_coverage_gaps(self):
        graph = self.api().derive(self.root, self.project)
        self.assertIn('NO_CANONICAL_CLAIMS', graph['coverage_gaps'])
        self.assertFalse(any(n['kind']=='CLAIM_REVISION' for n in graph['nodes']))

    def test_canonical_upstream_invalidation_reasons_are_exact(self):
        self.legacy_claim(); self.legacy_claim('C-2', dependencies=['C-1'])
        claim_graph.invalidate(self.project, 'C-1', 'Operator withdrew the premise')
        graph = self.api().derive(self.root, self.project)
        states = {n['claim_id']:n for n in graph['nodes'] if n['kind']=='CLAIM_REVISION' and n.get('current')}
        for actual in claim_graph.status(self.project)['claims']:
            self.assertEqual(states[actual['id']]['invalidation_reasons'], actual['invalidation_reasons'])
            self.assertEqual(states[actual['id']]['proof_status'], actual['proof_status'])

    def test_source_change_keeps_pin_marks_edges_pending_and_preserves_cache_on_read(self):
        self.legacy_claim(); self.api().build(self.root, self.project)
        old = self.api().cache_path(self.root, self.project).read_bytes()
        self.put('proofs/derivation.md', 'Operator changed the original source.')
        graph = self.api().derive(self.root, self.project)
        self.assertTrue(any(e['verified_status']=='PENDING_REVALIDATION' for e in graph['edges']))
        self.assertEqual(self.api().status(self.root, self.project)['cache_status'], 'STALE')
        self.assertEqual(old, self.api().cache_path(self.root, self.project).read_bytes())

    def test_markdown_failure_is_unverified_without_invented_refutation(self):
        self.put('research/FAILED_PATHS.md', '# Same theorem\nFailed branch; unstructured narrative.\n')
        graph = self.api().derive(self.root, self.project)
        nodes = [n for n in graph['nodes'] if n['kind']=='FAILED_BRANCH']
        self.assertTrue(nodes); self.assertTrue(all(n['verified_status']=='UNVERIFIED_TEXT_REFERENCE' for n in nodes))
        self.assertFalse(any(e['relation']=='REFUTES' for e in graph['edges']))

    def test_duplicate_route_run_logs_deduplicate_without_budget_mutation(self):
        ledger = {'schema_version':1,'epochs':[], 'events':[{'type':'RESEARCH_ROUND','run_id':'r1'}]*3}
        path = self.root / 'state/routes/example.json'; configuration.atomic_json(path, ledger)
        before = path.read_bytes(); graph = self.api().derive(self.root, self.project)
        self.assertEqual(len([n for n in graph['nodes'] if n['kind']=='RESEARCH_RUN']),1)
        self.assertEqual(before, path.read_bytes())

    def test_exact_historical_dependency_pin_is_not_latest_revision(self):
        self.legacy_claim(); self.legacy_claim('C-2', dependencies=['C-1'])
        self.legacy_claim('C-1', statement='For every integer x, x*x is at least zero.')
        graph = self.api().derive(self.root, self.project)
        nodes = {n['id']:n for n in graph['nodes']}
        edges = [e for e in graph['edges'] if e['relation']=='REQUIRES' and nodes[e['from']].get('claim_id')=='C-2'
                 and nodes[e['to']]['kind']=='CLAIM_REVISION']
        self.assertEqual(len(edges),1); self.assertEqual(nodes[edges[0]['to']]['claim_revision'],1)
        self.assertNotEqual(nodes[edges[0]['to']]['proof_status'],'INDEPENDENTLY_REVIEWED')

    def test_fake_reviewed_memory_metadata_never_promotes_claim_or_source(self):
        self.legacy_claim(); self.register(self.record(metadata={'status':'REVIEWED','proof_status':'INDEPENDENTLY_REVIEWED'}))
        graph = self.api().derive(self.root, self.project)
        self.assertFalse(any(n.get('proof_status')=='INDEPENDENTLY_REVIEWED' for n in graph['nodes']))
        self.assertFalse(any(n['verified_status']=='REVIEWED' for n in graph['nodes']))

    def test_mid_build_source_change_keeps_original_cache(self):
        self.legacy_claim(); self.api().build(self.root, self.project)
        before = self.api().cache_path(self.root, self.project).read_bytes()
        original = self.api()._manifest; count = 0
        def changed(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2: self.put('proofs/derivation.md','Concurrent operator edit.')
            return original(*args, **kwargs)
        with mock.patch.object(self.api(), '_manifest', side_effect=changed):
            with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'): self.api().build(self.root, self.project)
        self.assertEqual(before, self.api().cache_path(self.root, self.project).read_bytes())

    def test_same_obligation_id_in_two_problem_versions_is_distinct(self):
        self.legacy_claim()
        spec = copy.deepcopy(problem_compiler.get_problem(self.project,'P-1')['spec'])
        spec['assumptions'].append('A new explicit second-version premise')
        problem_compiler.import_problem(self.project,spec,'Operator revised an assumption')
        graph = self.api().derive(self.root,self.project)
        obligations = [n for n in graph['nodes'] if n['kind']=='OBLIGATION' and n.get('obligation_id')=='O-1']
        self.assertEqual(len(obligations),2); self.assertNotEqual(obligations[0]['id'],obligations[1]['id'])

    def test_legacy_memory_pin_retains_historical_revision(self):
        self.register(self.record('PAPER-1'))
        self.register(self.record('THEOREM-1','theorem',dependencies=['PAPER-1']))
        self.register(self.record('PAPER-1',statement='Changed source description under original assumptions.'))
        graph = self.api().derive(self.root,self.project); nodes = {n['id']:n for n in graph['nodes']}
        edges = [e for e in graph['edges'] if e['provenance_kind']=='LEGACY_MEMORY_DEPENDENCY_PIN'
                 and nodes[e['from']]['source_id']=='memory/THEOREM-1']
        self.assertEqual(len(edges),1); self.assertEqual(nodes[edges[0]['to']]['revision'],1)
        self.assertEqual(nodes[edges[0]['to']]['validity'],'HISTORICAL_REVISION')

    def test_failed_call_has_only_explicit_parent_and_no_proof_authority(self):
        path = self.root / 'state/discovery/example.json'
        configuration.atomic_json(path,{'schema_version':1,'active_attempt':None,'attempts':[
            {'id':'attempt-1','problem_id':'P-absent','problem_version':1,'status':'CLOSED',
             'close_reason':'Stopped after an unsuccessful candidate','calls':[{'run_id':'failed-1','status':'FAILED'}]*2}]})
        graph = self.api().derive(self.root,self.project)
        branches = [n for n in graph['nodes'] if n['kind']=='FAILED_BRANCH']
        self.assertEqual(len(branches),1); self.assertIsNotNone(branches[0]['parent_id'])
        self.assertIn('rejected',branches[0]['failure_reason'])

    def test_corrupt_cache_is_reported_and_repaired_only_by_build(self):
        self.legacy_claim(); self.api().build(self.root,self.project)
        path = self.api().cache_path(self.root,self.project); expected = path.read_bytes()
        path.write_bytes(b'broken cache')
        self.assertEqual(self.api().status(self.root,self.project)['cache_status'],'CORRUPT')
        self.assertEqual(path.read_bytes(),b'broken cache')
        self.api().build(self.root,self.project); self.assertEqual(expected,path.read_bytes())

    def test_build_write_failure_keeps_old_cache(self):
        import supervision
        self.legacy_claim(); self.api().build(self.root,self.project)
        path = self.api().cache_path(self.root,self.project); before = path.read_bytes()
        self.put('proofs/derivation.md','New evidence awaiting review.')
        with mock.patch.object(supervision,'_write',side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError): self.api().build(self.root,self.project)
        self.assertEqual(before,path.read_bytes())

    def test_cli_dryrun_status_explain_are_readonly_and_build_is_scoped(self):
        import contextlib
        import io
        import research
        self.legacy_claim(); original = self.files(self.root)
        with mock.patch.object(research,'ROOT',self.root),contextlib.redirect_stdout(io.StringIO()):
            for args in (['build','--dry-run'],['status'],['explain','--claim','C-1']):
                self.assertEqual(research.main(['knowledge',args[0],'example',*args[1:]]),0)
        self.assertEqual(original,self.files(self.root))
        self.api().build(self.root,self.project)
        changed = {k for k in self.files(self.root) if k not in original}
        self.assertTrue(all(k.startswith(('state/knowledge/','locks/')) for k in changed))

    def test_build_respects_route_and_core_locks(self):
        from route_budget import file_lock
        for name in ('route-example.lock','example.lock'):
            with file_lock(self.root/'locks'/name):
                with self.assertRaises(RuntimeError): self.api().build(self.root,self.project)
        self.assertFalse(self.api().cache_path(self.root,self.project).exists())

    def test_nonobject_json_cache_is_corrupt_without_affecting_authority(self):
        self.legacy_claim(); self.api().build(self.root,self.project)
        for raw in (b'[]',b'null',b'"untrusted"'):
            self.api().cache_path(self.root,self.project).write_bytes(raw)
            self.assertEqual(self.api().status(self.root,self.project)['cache_status'],'CORRUPT')

    def test_changed_claim_pin_digest_is_not_resolved_to_wrong_record(self):
        self.legacy_claim(); self.legacy_claim('C-2',dependencies=['C-1'])
        path = self.project/'research/discovery/CLAIM_GRAPH.json'
        data = configuration.load_json(path); data['claims'][1]['dependency_pins']['C-1']['spec_sha256']='0'*64
        configuration.atomic_json(path,data)
        graph = self.api().derive(self.root,self.project)
        self.assertIn('CLAIM_PIN_DIGEST_MISMATCH:C-1:1',graph['coverage_gaps'])
        self.assertFalse(any(e['provenance_kind']=='CANONICAL_DEPENDENCY_PIN' for e in graph['edges']))

    def test_revisited_route_does_not_reassign_prior_run_epoch_or_anchor(self):
        path = self.root/'state/routes/example.json'
        configuration.atomic_json(path,{'schema_version':1,'events':[],'epochs':[
            {'epoch':1,'counted_run_ids':['r1'],'focus':{'anchor_id':'original-anchor'}},
            {'epoch':3,'counted_run_ids':['r1','r3'],'focus':{'anchor_id':'new-anchor'}}]})
        graph = self.api().derive(self.root,self.project)
        old = next(n for n in graph['nodes'] if n.get('run_id')=='r1')
        self.assertEqual(old['route_epoch'],1); self.assertEqual(old['anchor_id'],'original-anchor')

    def test_multilevel_historical_memory_pin_chain_is_complete(self):
        self.register(self.record('ROOT'))
        self.register(self.record('A',dependencies=['ROOT']))
        self.register(self.record('B',dependencies=['A']))
        self.register(self.record('A',statement='Changed description and removed the dependency.'))
        graph = self.api().derive(self.root,self.project); nodes = {n['id']:n for n in graph['nodes']}
        edges = [e for e in graph['edges'] if e['provenance_kind']=='HISTORICAL_MEMORY_DEPENDENCY_PIN']
        self.assertTrue(any(nodes[e['from']]['source_id']=='memory/A' and nodes[e['from']]['revision']==1
                            and nodes[e['to']]['source_id']=='memory/ROOT' for e in edges))

    def test_historical_goal_version_is_marked_stale_without_rebinding(self):
        self.legacy_claim(); old_goal = self.api().derive(self.root,self.project)['nodes']
        old_sha = next(n['goal_sha256'] for n in old_goal if n['kind']=='PROBLEM_VERSION')
        self.put('GOAL.md','Operator changed the frozen goal.')
        graph = self.api().derive(self.root,self.project)
        node = next(n for n in graph['nodes'] if n['kind']=='GOAL' and n['goal_sha256']==old_sha)
        self.assertEqual(node['pinned_sha256'],old_sha); self.assertEqual(node['validity'],'PENDING_REVALIDATION')

    def test_persisted_memory_keeps_original_goal_after_goal_change(self):
        item = self.register(self.record())
        self.put('GOAL.md','Operator changed the original frozen problem.')
        graph = self.api().derive(self.root,self.project)
        node = next(n for n in graph['nodes'] if n['source_id']=='memory/PAPER-1')
        self.assertEqual(node['goal_sha256'],item['goal_sha256'])
        self.assertEqual(node['validity'],'PENDING_REVALIDATION')

    def test_refutes_edge_requires_canonical_counterexample_receipt(self):
        from engine import falsification
        self.legacy_claim(machine_statement={'domain':'INTEGER','variables':['x'],
            'preconditions':[],'conclusion':'x < 0'})
        falsification.search(self.project,'C-1',-1,1)
        graph = self.api().derive(self.root,self.project)
        self.assertTrue(any(e['relation']=='REFUTES' and e['verified_status']=='MACHINE_STATEMENT_REFUTED'
                            for e in graph['edges']))
        self.assertFalse(any(n.get('proof_status')=='INDEPENDENTLY_REVIEWED' for n in graph['nodes']))

    def test_changed_novelty_receipt_cannot_inherit_proof_review_status(self):
        self.legacy_claim()
        for kind in ('proof','statement'):
            path = 'research/review-'+kind+'.md'
            self.put(path,'Independent operator attestation for this exact '+kind+' fixture.')
            claim_graph.review(self.project,'C-1',kind,path,'independent-operator','Exact bounded fixture review')
        self.put('research/review-novelty.md','Operator changed this novelty attestation.')
        # Deliberately damaged archived review: no novelty approval is forged.
        path = self.project/'research/discovery/CLAIM_GRAPH.json'
        data = configuration.load_json(path)
        data['claims'][0]['reviews']['novelty'] = {'claim_sha256':data['claims'][0]['spec_sha256'],
            'evidence':{'research/review-novelty.md':'0'*64}}
        configuration.atomic_json(path,data)
        actual = claim_graph.status(self.project)['claims'][0]
        self.assertEqual(actual['proof_status'],'INDEPENDENTLY_REVIEWED')
        self.assertEqual(actual['novelty_status'],'PENDING')
        graph = self.api().derive(self.root,self.project)
        edge = next(e for e in graph['edges'] if e.get('review_kind')=='novelty')
        self.assertEqual(edge['verified_status'],'PENDING_REVALIDATION')


if __name__ == '__main__': unittest.main()
