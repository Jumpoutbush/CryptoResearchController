"""R10 knowledge loop: explicit sharing, namespace preservation and cache recovery."""
import copy
import json
from pathlib import Path
import unittest
from unittest import mock
import configuration
from research_quality import hash_file
from engine import claim_graph
import test_cross_project_isolation as fixture


class KnowledgeEndToEndTests(unittest.TestCase):
    setUp=fixture.CrossProjectTests.setUp
    put=fixture.CrossProjectTests.put
    files=fixture.CrossProjectTests.files
    legacy_claim=fixture.CrossProjectTests.legacy_claim
    write_model=fixture.CrossProjectTests.write_model
    preview=fixture.CrossProjectTests.preview
    authorize=fixture.CrossProjectTests.authorize
    save_policy=fixture.CrossProjectTests.save_policy
    search=fixture.CrossProjectTests.search

    def test_T09_namespaced_equations_keep_different_parameter_and_adversary_contexts(self):
        self.authorize(); from knowledge.schema import identity
        third=self.root/'projects/third'; (third/'knowledge/shared/references').mkdir(parents=True)
        configuration.atomic_json(third/'PROJECT.json',{'id':'third','checks':[]})
        (third/'knowledge/shared/sources').mkdir()
        (third/'knowledge/shared/sources/paper.txt').write_bytes((self.origin/'knowledge/shared/sources/paper.txt').read_bytes())
        capsule=copy.deepcopy(self.capsule); capsule['origin_project']='third'
        capsule['origin']['node_id']=identity('third','CLAIM_REVISION','C-1',1)
        capsule['model'].update(parameters='q=17',adversary='ADAPTIVE')
        file=third/'knowledge/shared/references/EQ.json'; configuration.atomic_json(file,capsule); digest=hash_file(file)
        self.policy['projects']['third']={'enabled':True,'imports':[],'exports':[{'id':'EQ','path':'knowledge/shared/references/EQ.json',
            'sha256':digest,'destinations':['other']}]}
        self.policy['projects']['other']['imports'].append({'origin_project':'third','id':'EQ','sha256':digest}); self.save_policy()
        before=self.files(self.root); result=self.search()
        self.assertEqual(len(result['references']),2); self.assertTrue(result['conflicts'])
        self.assertEqual(len({r['reference_id'] for r in result['references']}),2)
        self.assertTrue(all(r['status']=='REFERENCE_ONLY' and not r['positive_basis'] for r in result['references']))
        self.assertEqual(before,self.files(self.root))

    def test_T07_T08_cache_rebuild_and_stale_public_chain_preserve_authority(self):
        self.authorize(); from knowledge import build as projection
        from knowledge.context_builder import build as context
        before_status=claim_graph.status(self.origin)
        first=projection.build(self.root,self.origin); cache=projection.cache_path(self.root,self.origin)
        raw=cache.read_bytes(); history=cache.with_name('history.json').read_bytes(); cache.unlink()
        second=projection.build(self.root,self.origin)
        self.assertEqual(first['graph_sha256'],second['graph_sha256']); self.assertEqual(raw,cache.read_bytes())
        self.assertEqual(history,cache.with_name('history.json').read_bytes())
        result=self.search()['references'][0]
        self.assertEqual(result['origin']['claim_revision'],1); self.assertEqual(result['origin']['obligation_ids'],['O-1'])
        self.assertEqual(result['source_hashes'][0]['sha256'],hash_file(self.origin/'knowledge/shared/sources/paper.txt'))
        compact=context(self.root,self.origin,claim_id='C-1',task='Original exact obligation',max_bytes=4096)
        self.assertLessEqual(compact['context_bytes'],4096)
        self.put('knowledge/shared/sources/paper.txt','Updated authorized public paper version')
        self.assertFalse(self.search()['references']); self.assertEqual(before_status,claim_graph.status(self.origin))
        self.put('proofs/derivation.md','Changed original private derivation')
        stale=context(self.root,self.origin,claim_id='C-1')
        self.assertFalse(any(n['positive_basis'] for n in stale['selected']))
        self.assertEqual(claim_graph.status(self.origin)['claims'][0]['proof_status'],'PENDING_REVALIDATION')

    def test_sharing_is_not_automatically_injected_or_counted_as_scientific_acceptance(self):
        self.authorize(); import runner_core
        state=configuration.load_json(self.origin/'research/STATE.json'); before=self.files(self.root)
        with mock.patch.object(runner_core,'ROOT',self.root): a=runner_core.build_prompt(self.origin,state,'r1','critical')
        self.policy['enabled']=False; self.save_policy()
        with mock.patch.object(runner_core,'ROOT',self.root): b=runner_core.build_prompt(self.origin,state,'r1','critical')
        self.assertEqual(a,b); self.assertNotIn('Same toy equation under explicitly stated parameters.',a)
        # Explicit policy edit is the sole disk change, not scientific state or budget.
        after=self.files(self.root); changed=[p for p in before if before[p]!=after[p]]
        self.assertEqual(changed,['config/sharing_policy.json'])

    def test_controlled_link_and_oversized_export_fail_without_source_fallback(self):
        self.authorize(); import runner_core
        original=runner_core.project_link
        with mock.patch.object(runner_core,'project_link',side_effect=lambda p: True if Path(p)==self.capsule_path.parent else original(p)):
            self.assertFalse(self.search()['references'])
        self.capsule_path.write_bytes(b'x'*65537)
        self.assertFalse(self.search()['references'])


if __name__=='__main__': unittest.main()
