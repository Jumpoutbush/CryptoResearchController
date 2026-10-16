"""Projection history preserves the original authority and survives cache crashes."""
import copy
import os
import unittest
from unittest import mock
import configuration
from engine import claim_graph
from knowledge import build as projection
import test_knowledge_graph as fixture


class KnowledgeInvalidationTests(unittest.TestCase):
    setUp=fixture.KnowledgeGraphTests.setUp
    put=fixture.KnowledgeGraphTests.put
    files=fixture.KnowledgeGraphTests.files
    legacy_claim=fixture.KnowledgeGraphTests.legacy_claim

    def chain(self):
        for cid,deps in [('A',[]),('B',['A']),('C',['B'])]:
            self.legacy_claim(cid,dependencies=deps)
            self.put('proofs/review-'+cid+'.md','Offline operator review fixture; not a scientific result.')
            claim_graph.review(self.project,cid,'proof_and_statement','proofs/review-'+cid+'.md',
                'independent-fixture-reviewer','Review this exact synthetic revision')
        self.assertTrue(all(n['proof_status']=='INDEPENDENTLY_REVIEWED' for n in claim_graph.status(self.project)['claims']))

    def revise(self):
        self.legacy_claim('A',statement='For every integer x, its exact square x*x is nonnegative.')
        claim_graph.refresh(self.project)

    def events(self):
        from knowledge import events
        return events

    def test_three_level_revision_matches_canonical_and_explains_old_and_new_pins(self):
        self.chain(); projection.build(self.root,self.project); self.revise()
        before=self.files(); result=projection.explain_claim(self.root,self.project,'C')
        self.assertEqual(before,self.files())
        states={n['id']:n for n in claim_graph.status(self.project)['claims']}
        self.assertEqual(result['claim']['invalidation_reasons'],states['C']['invalidation_reasons'])
        paths=result['lineage']['cause_paths']
        self.assertTrue(any([s['claim_id'] for s in p]==['C','B','A'] for p in paths))
        b=next(s for p in paths for s in p if s['claim_id']=='B' and s.get('dependency_id')=='A')
        self.assertEqual(b['pinned']['revision'],1); self.assertEqual(b['observed']['revision'],2)

    def test_repeat_build_and_mtime_do_not_append_events(self):
        self.chain(); first=projection.build(self.root,self.project)
        path=self.events().path(self.root,self.project); raw=path.read_bytes()
        os.utime(self.project/'proofs/derivation.md',None)
        self.assertEqual(first,projection.build(self.root,self.project)); self.assertEqual(raw,path.read_bytes())

    def test_invalidation_once_and_readonly_diff_has_precise_reason(self):
        self.chain(); a=projection.build(self.root,self.project); self.revise(); b=projection.build(self.root,self.project)
        saved=self.events().load(self.root,self.project); raw=self.events().path(self.root,self.project).read_bytes()
        projection.build(self.root,self.project)
        self.assertEqual(raw,self.events().path(self.root,self.project).read_bytes())
        self.assertEqual(len([e for e in saved['events'] if e['type']=='GRAPH_INVALIDATED']),1)
        before=self.files(self.root)
        diff=self.events().diff(self.root,self.project,a['graph_sha256'],b['graph_sha256'])
        self.assertEqual(diff['status'],'OK'); self.assertIn('C',[c['claim_id'] for c in diff['affected_claims']])
        self.assertEqual(before,self.files(self.root))

    def test_restoring_file_does_not_restore_formally_revised_downstream_reviews(self):
        self.chain(); original=(self.project/'proofs/derivation.md').read_bytes(); self.revise()
        (self.project/'proofs/derivation.md').write_bytes(original)
        projection.build(self.root,self.project)
        self.assertEqual(claim_graph.get(self.project,'A')['reviews'],{})
        for cid in ('B','C'):
            self.assertEqual(projection.explain_claim(self.root,self.project,cid)['claim']['proof_status'],'PENDING_REVALIDATION')

    def test_explicit_revocation_cannot_be_cleared_by_cache_rebuild(self):
        self.chain(); claim_graph.invalidate(self.project,'A','Original operator withdrew the premise')
        a=projection.build(self.root,self.project); projection.cache_path(self.root,self.project).unlink()
        b=projection.build(self.root,self.project); self.assertEqual(a,b)
        self.assertEqual(projection.explain_claim(self.root,self.project,'C')['claim']['proof_status'],'PENDING_REVALIDATION')

    def test_old_review_cannot_be_reused_for_new_revision(self):
        self.chain(); self.revise(); graph=claim_graph.load(self.project)
        graph['claims'][0]['reviews']=copy.deepcopy(graph['claims'][0]['history'][0]['reviews'])
        claim_graph.save(self.project,graph)  # adversarial temporary fixture only
        self.assertNotEqual(projection.explain_claim(self.root,self.project,'A')['claim']['proof_status'],'INDEPENDENTLY_REVIEWED')

    def test_corrupt_history_errors_and_explicit_cache_only_rebuild_preserves_it(self):
        self.chain(); projection.build(self.root,self.project); p=self.events().path(self.root,self.project)
        p.write_bytes(b'broken log'); before=p.read_bytes(); projection.cache_path(self.root,self.project).unlink()
        with self.assertRaisesRegex(ValueError,'HISTORY_INTEGRITY'): projection.build(self.root,self.project)
        result=projection.build(self.root,self.project,cache_only=True)
        self.assertEqual(result['history']['status'],'CORRUPT'); self.assertEqual(before,p.read_bytes())
        self.assertTrue(projection.cache_path(self.root,self.project).is_file())

    def test_chain_tamper_duplicate_and_out_of_order_fail_closed(self):
        self.chain(); projection.build(self.root,self.project); self.revise(); projection.build(self.root,self.project)
        p=self.events().path(self.root,self.project); original=configuration.load_json(p)
        for mode in ('duplicate','previous','sequence','snapshot'):
            obj=copy.deepcopy(original)
            if mode=='duplicate': obj['events'].append(obj['events'][0])
            elif mode=='previous': obj['events'][-1]['previous_sha256']='0'*64
            elif mode=='sequence': obj['events'][-1]['sequence']=1
            else: obj['snapshots'][next(iter(obj['snapshots']))]['nodes']=[]
            configuration.atomic_json(p,obj); raw=p.read_bytes()
            with self.subTest(mode=mode),self.assertRaisesRegex(ValueError,'HISTORY_INTEGRITY'):
                self.events().load(self.root,self.project)
            self.assertEqual(raw,p.read_bytes())

    def test_history_unavailable_is_explicit(self):
        self.chain(); a=projection.build(self.root,self.project)
        result=self.events().diff(self.root,self.project,'0'*64,a['graph_sha256'])
        self.assertEqual(result['status'],'HISTORY_UNAVAILABLE')

    def test_crash_after_history_before_cache_replays_without_duplicate(self):
        import supervision
        self.chain(); projection.build(self.root,self.project); self.revise()
        original=supervision._write; cache=projection.cache_path(self.root,self.project); old=cache.read_bytes()
        def crash(path,raw):
            if path==cache: raise OSError('Interrupted after history commit')
            return original(path,raw)
        with mock.patch.object(supervision,'_write',side_effect=crash),self.assertRaises(OSError):
            projection.build(self.root,self.project)
        self.assertEqual(old,cache.read_bytes()); history=self.events().path(self.root,self.project).read_bytes()
        projection.build(self.root,self.project); self.assertEqual(history,self.events().path(self.root,self.project).read_bytes())
        self.assertNotEqual(old,cache.read_bytes())

    def test_rename_same_content_is_not_another_invalidation_or_discovery(self):
        self.chain(); projection.build(self.root,self.project)
        self.put('literature/renamed.txt','same content'); a=projection.build(self.root,self.project)
        (self.project/'literature/renamed.txt').rename(self.project/'literature/another-name.txt')
        b=projection.build(self.root,self.project)
        diff=self.events().diff(self.root,self.project,a['graph_sha256'],b['graph_sha256'])
        self.assertTrue(any(c['kind']=='PATH_RELOCATED' for c in diff['source_changes']))
        self.assertFalse(diff['scientific_discovery'])

    def test_readonly_live_explain_reports_corruption_without_using_old_approval(self):
        self.chain(); projection.build(self.root,self.project); self.revise()
        p=self.events().path(self.root,self.project); p.write_bytes(b'[]'); before=self.files(self.root)
        result=projection.explain_claim(self.root,self.project,'C')
        self.assertEqual(result['history']['status'],'CORRUPT'); self.assertEqual(result['claim']['proof_status'],'PENDING_REVALIDATION')
        self.assertEqual(before,self.files(self.root))

    def test_unrelated_review_does_not_duplicate_existing_invalidation(self):
        self.chain(); projection.build(self.root,self.project); self.revise(); projection.build(self.root,self.project)
        count=len([e for e in self.events().load(self.root,self.project)['events'] if e['type']=='GRAPH_INVALIDATED'])
        self.legacy_claim('D'); projection.build(self.root,self.project)
        self.assertEqual(count,len([e for e in self.events().load(self.root,self.project)['events'] if e['type']=='GRAPH_INVALIDATED']))

    def test_current_authority_can_recover_after_real_rebind_and_fresh_reviews(self):
        self.chain(); self.revise()
        for cid,deps in [('A',[]),('B',['A']),('C',['B'])]:
            if cid!='A': self.legacy_claim(cid,dependencies=deps)
            claim_graph.review(self.project,cid,'proof_and_statement','proofs/review-'+cid+'.md',
                'independent-fixture-reviewer','Review the new exact synthetic revision')
        result=projection.explain_claim(self.root,self.project,'C')
        self.assertEqual(result['claim']['proof_status'],'INDEPENDENTLY_REVIEWED')
        self.assertEqual(claim_graph.get(self.project,'C')['revision'],2)

    def test_source_change_path_reports_expected_and_observed_digests(self):
        self.chain(); self.put('proofs/derivation.md','Replacement original source')
        result=projection.explain_claim(self.root,self.project,'C')
        leaves=[s for p in result['lineage']['cause_paths'] for s in p if s['reason']=='EVIDENCE_CHANGED']
        self.assertTrue(leaves)
        self.assertTrue(any(e['pinned_sha256']!=e['current_sha256'] for s in leaves for e in s['evidence']))

    def test_cache_corruption_repaired_without_rewriting_history(self):
        self.chain(); projection.build(self.root,self.project)
        p=self.events().path(self.root,self.project); before=p.read_bytes()
        projection.cache_path(self.root,self.project).write_bytes(b'broken')
        projection.build(self.root,self.project); self.assertEqual(before,p.read_bytes())

    def test_diff_invalid_digest_rejected_before_path_access(self):
        self.chain()
        with self.assertRaises(ValueError): self.events().diff(self.root,self.project,'../outside','0'*64)
        self.assertFalse(self.events().path(self.root,self.project).exists())

    def test_deeply_nested_history_reports_corruption_without_recursion_crash(self):
        self.chain(); projection.build(self.root,self.project); p=self.events().path(self.root,self.project)
        p.write_text('['*20000+'0'+']'*20000,encoding='utf8')
        self.assertEqual(self.events().summary(self.root,self.project)['status'],'CORRUPT')

    def test_event_limit_refuses_before_any_history_or_cache_write(self):
        self.chain(); projection.build(self.root,self.project); before=self.files(self.root); self.revise()
        history=self.events().path(self.root,self.project).read_bytes(); cache=projection.cache_path(self.root,self.project).read_bytes()
        with mock.patch.object(self.events(),'MAX_EVENTS',1),self.assertRaisesRegex(ValueError,'HISTORY_LIMIT'):
            projection.build(self.root,self.project)
        self.assertEqual(history,self.events().path(self.root,self.project).read_bytes())
        self.assertEqual(cache,projection.cache_path(self.root,self.project).read_bytes())

    def test_novelty_source_loss_is_not_confused_with_proof_approval(self):
        import test_discovery
        self.chain(); test_discovery.DiscoveryTests.novelty_review(self,'A')
        projection.build(self.root,self.project); self.put('literature/primary.txt','Changed original paper premise')
        projection.build(self.root,self.project)
        event=self.events().load(self.root,self.project)['events'][-1]
        self.assertEqual(event['type'],'GRAPH_INVALIDATED')
        self.assertIn('NOVELTY',next(c for c in event['affected_claims'] if c['claim_id']=='A')['lost_scopes'])
        result=projection.explain_claim(self.root,self.project,'A')
        self.assertEqual(result['claim']['proof_status'],'INDEPENDENTLY_REVIEWED')
        self.assertFalse(result['claim']['accepted_contribution'])
        self.assertTrue(any(e['review_kind']=='novelty' and not e['binding_matches']
            for p in result['lineage']['cause_paths'] for step in p for e in step.get('evidence',[])))

    def test_memory_upstream_loss_has_original_path_and_reason(self):
        from engine import knowledge_graph
        knowledge_graph.import_record(self.project,fixture.KnowledgeGraphTests.record(self), 'Offline source fixture')
        self.legacy_claim('A',knowledge_dependencies=['PAPER-1'])
        self.put('literature/paper.txt','Changed source premise')
        result=projection.explain_claim(self.root,self.project,'A')
        self.assertTrue(any(step.get('memory_id')=='PAPER-1' and step['reason']=='SOURCE_CHANGED:literature/paper.txt'
            for p in result['lineage']['cause_paths'] for step in p))

    def test_unrecorded_snapshot_cannot_appear_in_historical_diff(self):
        self.chain(); projection.build(self.root,self.project); self.revise()
        other=projection.derive(self.root,self.project); p=self.events().path(self.root,self.project)
        data=configuration.load_json(p); data['snapshots'][other['graph_sha256']]=other; configuration.atomic_json(p,data)
        with self.assertRaisesRegex(ValueError,'HISTORY_INTEGRITY'): self.events().load(self.root,self.project)

    def test_exact_counterexample_preserves_original_scope_and_assumptions(self):
        from engine import falsification
        self.legacy_claim('A',machine_statement={'domain':'INTEGER','variables':['x'],
            'preconditions':['x >= 0'],'conclusion':'x*x < 0'})
        receipt=falsification.search(self.project,'A',0,1)
        result=projection.explain_claim(self.root,self.project,'A')
        node=next(n for n in result['nodes'] if n.get('record_kind')=='counterexample_receipt')
        self.assertEqual(node['applicability']['scope'],'MACHINE_STATEMENT_ONLY')
        self.assertEqual(node['applicability']['witness'],receipt['witness'])
        self.assertEqual(node['applicability']['machine_statement_sha256'],receipt['machine_statement_sha256'])
        self.assertEqual(node['applicability']['assumptions'],claim_graph.get(self.project,'A')['spec']['assumptions'])
        self.assertTrue(any(e['relation']=='REFUTES' for e in result['edges']))

    def test_pruned_snapshot_unavailable_and_same_content_recovered_without_new_event(self):
        self.chain(); a=projection.build(self.root,self.project); p=self.events().path(self.root,self.project)
        data=configuration.load_json(p); old=copy.deepcopy(data['events']); data['snapshots'].clear()
        configuration.atomic_json(p,data)
        self.assertEqual(self.events().diff(self.root,self.project,a['graph_sha256'],a['graph_sha256'])['status'],'HISTORY_UNAVAILABLE')
        projection.build(self.root,self.project)
        self.assertEqual(old,self.events().load(self.root,self.project)['events'])


if __name__=='__main__': unittest.main()
