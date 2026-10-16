"""R10 explicit public capsules; no source-project scientific traversal."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock
import configuration
from engine import claim_graph,problem_compiler
from research_quality import hash_file
import test_knowledge_graph as fixture


class CrossProjectTests(unittest.TestCase):
    put=fixture.KnowledgeGraphTests.put
    files=fixture.KnowledgeGraphTests.files
    legacy_claim=fixture.KnowledgeGraphTests.legacy_claim

    def setUp(self):
        fixture.KnowledgeGraphTests.setUp(self)
        self.legacy_claim()
        self.put('proofs/review.md','Independent toy statement and proof review, not new research.')
        for kind in ('proof','statement'):
            claim_graph.review(self.project,'C-1',kind,'proofs/review.md','independent-operator','Attest this exact toy fixture only')
        self.origin=self.project; self.target=self.root/'projects/other'; self.target.mkdir()
        for name,value in {'PROJECT.json':{'id':'other','checks':[]},'GOAL.md':'Different destination goal.',
            'AGENTS.md':'Preserve destination security model.','research/STATE.json':{'research_route':'MAIN','next_task':'Exact target task'}}.items():
            path=self.target/name; path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(value) if isinstance(value,dict) else value,encoding='utf8')
        spec=copy.deepcopy(problem_compiler.get_problem(self.origin,'P-1',1)['spec'])
        problem_compiler.import_problem(self.target,spec,'Register independent destination toy problem')
        self.put('knowledge/shared/sources/paper.txt','Explicitly public toy paper source, not a private PDF.')
        self.put('knowledge/shared/drafts/summary.txt','Same toy equation under explicitly stated parameters.')
        self.write_model(self.origin,'STATIC','q=7'); self.write_model(self.target,'ADAPTIVE','q=17')
        self.policy={'schema_version':1,'enabled':True,'projects':{'example':{'enabled':True,'imports':[],'exports':[]},
            'other':{'enabled':True,'imports':[],'exports':[]}}}
        self.capsule_path=self.origin/'knowledge/shared/references/EQ.json'

    def write_model(self,project,adversary,parameters):
        problem=problem_compiler.get_problem(project,'P-1',1)
        model={'model':'Toy ring equation','domain':problem['spec']['domain'],'quantifiers':problem['spec']['quantifiers'],
            'assumptions':problem['spec']['assumptions'],'parameters':parameters,'adversary':adversary,'leakage':'No secret leakage'}
        configuration.atomic_json(project/'knowledge/shared/MODEL.json',{'schema_version':1,'goal_sha256':hash_file(project/'GOAL.md'),
            'problem_id':'P-1','problem_version':1,'problem_sha256':problem['spec_sha256'],'model':model})

    def preview(self,**updates):
        from knowledge.federation import preview
        args=dict(claim_id='C-1',reference_id='EQ',revision=1,model_path='knowledge/shared/MODEL.json',
            summary_path='knowledge/shared/drafts/summary.txt',public_sources=['knowledge/shared/sources/paper.txt'],
            license_id='CC-BY-4.0',approved_by='operator',reason='Explicitly approved public toy summary')
        return preview(self.root,self.origin,**{**args,**updates})

    def authorize(self):
        self.capsule=self.preview(); configuration.atomic_json(self.capsule_path,self.capsule)
        digest=hash_file(self.capsule_path)
        self.policy['projects']['example']['exports']=[{'id':'EQ','path':'knowledge/shared/references/EQ.json',
            'sha256':digest,'destinations':['other']}]
        self.policy['projects']['other']['imports']=[{'origin_project':'example','id':'EQ','sha256':digest}]
        self.policy['projects']['other']['model_sha256']=hash_file(self.target/'knowledge/shared/MODEL.json')
        self.save_policy()

    def save_policy(self): configuration.atomic_json(self.root/'config/sharing_policy.json',self.policy)

    def search(self,**args):
        from knowledge.federation import search
        return search(self.root,self.target,**args)

    def test_default_disabled_never_reads_origin_or_enumerates_projects(self):
        from knowledge import federation
        self.policy['enabled']=False; self.save_policy()
        original=Path.open
        def opening(path,*args,**kwargs):
            if path.is_relative_to(self.origin): raise AssertionError('Foreign project read while disabled')
            return original(path,*args,**kwargs)
        with mock.patch.object(Path,'open',new=opening),mock.patch('research.projects',side_effect=AssertionError('No enumeration')):
            result=self.search()
        self.assertEqual(result['status'],'DISABLED'); self.assertEqual(result['references'],[])

    def test_bilateral_pins_required_before_export_body_is_read(self):
        self.authorize(); self.policy['projects']['example']['exports'][0]['destinations']=[]; self.save_policy()
        original=Path.open
        def opening(path,*args,**kwargs):
            if path==self.capsule_path: raise AssertionError('Unauthorized capsule body read')
            return original(path,*args,**kwargs)
        with mock.patch.object(Path,'open',new=opening): result=self.search()
        self.assertEqual(result['references'],[]); self.assertTrue(result['diagnostics'])

    def test_enabled_consumer_reads_only_explicit_public_files(self):
        self.authorize(); self.put('inputs/private.pdf','PRIVATE PDF SENTINEL'); self.put('proofs/private.py','PRIVATE CODE')
        self.put('reports/private.log','PRIVATE LOG'); self.put('inputs/secrets.json',{'secret':'PRIVATE KEY'})
        allowed={'PROJECT.json','knowledge/shared/references/EQ.json','knowledge/shared/sources/paper.txt'}
        original=Path.open; reads=[]
        def opening(path,*args,**kwargs):
            if path.is_relative_to(self.origin):
                relative=path.relative_to(self.origin).as_posix(); reads.append(relative)
                if relative not in allowed: raise AssertionError('Private origin read: '+relative)
            return original(path,*args,**kwargs)
        with mock.patch.object(Path,'open',new=opening),mock.patch('knowledge.build.derive',side_effect=AssertionError('No foreign derive')):
            result=self.search()
        self.assertTrue(reads); self.assertEqual(len(result['references']),1)
        self.assertNotIn('PRIVATE',json.dumps(result))

    def test_always_reference_only_and_adaptive_model_cannot_inherit_static_result(self):
        self.authorize(); result=self.search(); ref=result['references'][0]
        self.assertEqual(ref['status'],'REFERENCE_ONLY'); self.assertFalse(ref['positive_basis'])
        self.assertIn('ADVERSARY_MISMATCH',ref['reuse_review']['reasons'])
        self.assertIn('PARAMETERS_MISMATCH',ref['reuse_review']['reasons'])
        self.assertEqual(len(ref['reuse_review']['mapping']),7)

    def test_matching_textual_models_still_require_independent_destination_review(self):
        self.authorize(); self.write_model(self.target,'STATIC','q=7')
        self.policy['projects']['other']['model_sha256']=hash_file(self.target/'knowledge/shared/MODEL.json'); self.save_policy()
        ref=self.search()['references'][0]
        self.assertEqual(ref['reuse_review']['status'],'EXACT_TEXT_MAPPING_REVIEW_PENDING')
        self.assertFalse(ref['positive_basis']); self.assertTrue(ref['requires_revalidation'])

    def test_public_source_change_expires_reference_without_scientific_writes(self):
        self.authorize(); before=self.files(self.root)
        self.put('knowledge/shared/sources/paper.txt','Changed explicitly shared original source')
        expected=self.files(self.root); result=self.search()
        self.assertEqual(result['references'],[]); self.assertIn('PUBLIC_SOURCE_CHANGED',json.dumps(result['diagnostics']))
        self.assertEqual(expected,self.files(self.root)); self.assertNotEqual(before,expected)

    def test_revocation_cannot_fall_back_to_cached_summary(self):
        self.authorize(); self.assertTrue(self.search()['references'])
        configuration.atomic_json(self.root/'state/knowledge/other/federation.json',{'references':[self.capsule]})
        self.policy['projects']['example']['enabled']=False; self.save_policy()
        result=self.search(); self.assertEqual(result['references'],[]); self.assertFalse(result['cache_used'])
        self.assertNotIn(self.capsule['summary'],json.dumps(result))

    def test_missing_import_does_not_read_other_project(self):
        self.authorize(); self.policy['projects']['other']['imports']=[]; self.save_policy()
        with mock.patch('configuration.project_id',wraps=configuration.project_id) as identify:
            result=self.search()
        self.assertEqual(result['references'],[])
        self.assertFalse(any(call.args[0]==self.origin for call in identify.call_args_list))

    def test_target_and_export_sha_disagreement_is_not_auto_rebound(self):
        self.authorize(); self.policy['projects']['other']['imports'][0]['sha256']='0'*64; self.save_policy()
        result=self.search(); self.assertEqual(result['references'],[])
        self.assertIn('IMPORT_EXPORT_PIN_MISMATCH',json.dumps(result['diagnostics']))

    def test_capsule_bytes_changed_after_approval_are_rejected(self):
        self.authorize(); self.capsule['summary']='Unapproved replacement'; configuration.atomic_json(self.capsule_path,self.capsule)
        self.assertIn('EXPORT_SHA_CHANGED',json.dumps(self.search()['diagnostics']))

    def test_foreign_identity_and_unknown_fields_are_rejected(self):
        self.authorize()
        for key,value in [('origin_project','elsewhere'),('private_pdf','inputs/private.pdf')]:
            capsule=copy.deepcopy(self.capsule); capsule[key]=value; configuration.atomic_json(self.capsule_path,capsule)
            digest=hash_file(self.capsule_path)
            self.policy['projects']['example']['exports'][0]['sha256']=digest
            self.policy['projects']['other']['imports'][0]['sha256']=digest; self.save_policy()
            with self.subTest(key=key): self.assertEqual(self.search()['references'],[])

    def test_paths_cannot_export_pdf_code_logs_credentials_or_traverse(self):
        self.authorize()
        for path in ('../private.json','C:/secret.json','//server/secret.json','inputs/private.pdf',
            'knowledge/shared/references/secret.py','knowledge/shared/references/.env.json'):
            self.policy['projects']['example']['exports'][0]['path']=path; self.save_policy()
            with self.subTest(path=path),self.assertRaises(ValueError): self.search()

    def test_private_upstream_is_explicitly_not_checked(self):
        self.authorize(); result=self.search()['references'][0]
        self.assertEqual(result['freshness_scope'],'EXPLICIT_PUBLIC_SOURCES_ONLY')
        self.assertEqual(result['private_upstream_status'],'NOT_READ_OR_REVALIDATED')

    def test_unknown_policy_keys_and_nonboolean_enable_rejected(self):
        for change in ({'allow_private':True},{'enabled':'yes'}):
            value={**self.policy,**change}; configuration.atomic_json(self.root/'config/sharing_policy.json',value)
            with self.subTest(change=change),self.assertRaises(ValueError): self.search()

    def test_no_network_no_writes_deterministic_results(self):
        self.authorize(); before=self.files(self.root)
        with mock.patch('urllib.request.urlopen',side_effect=AssertionError('No network')):
            first=self.search(query='equation'); second=self.search(query='equation')
        self.assertEqual(first,second); self.assertEqual(before,self.files(self.root))

    def test_permission_change_during_read_aborts_without_result(self):
        self.authorize(); from knowledge import federation
        original=federation._read
        def read(path,*args,**kwargs):
            raw=original(path,*args,**kwargs)
            if path==self.capsule_path:
                self.policy['enabled']=False; self.save_policy()
            return raw
        with mock.patch.object(federation,'_read',side_effect=read),self.assertRaisesRegex(ValueError,'SHARING_INPUT_CHANGED'):
            self.search()

    def test_target_model_is_bound_to_frozen_goal_and_problem(self):
        self.authorize(); descriptor=configuration.load_json(self.target/'knowledge/shared/MODEL.json')
        descriptor['goal_sha256']='0'*64; configuration.atomic_json(self.target/'knowledge/shared/MODEL.json',descriptor)
        self.policy['projects']['other']['model_sha256']=hash_file(self.target/'knowledge/shared/MODEL.json'); self.save_policy()
        with self.assertRaisesRegex(ValueError,'TARGET_MODEL_BINDING'): self.search()

    def test_preview_does_not_write_and_refuses_bad_dependency_bindings(self):
        self.authorize(); before=self.files(self.root); self.preview(); self.assertEqual(before,self.files(self.root))
        self.legacy_claim('B',['C-1']); path=self.origin/'research/discovery/CLAIM_GRAPH.json'; data=configuration.load_json(path)
        data['claims'][1]['dependency_pins']={}; configuration.atomic_json(path,data)
        with self.assertRaisesRegex(ValueError,'CLAIM_DEPENDENCY_BINDING_INVALID'): self.preview()

    def test_disabled_policy_does_not_even_inspect_foreign_link_metadata(self):
        self.authorize(); self.policy['enabled']=False; self.save_policy()
        import runner_core
        original=runner_core.project_link
        def link(path):
            if Path(path).is_relative_to(self.origin): raise AssertionError('Foreign metadata inspection while disabled')
            return original(path)
        with mock.patch.object(runner_core,'project_link',side_effect=link): self.assertEqual(self.search()['status'],'DISABLED')

    def test_paper_identity_can_be_shared_without_fabricating_a_claim(self):
        self.authorize(); from knowledge.schema import identity
        capsule=copy.deepcopy(self.capsule); capsule['kind']='PAPER_IDENTITY'
        capsule['origin']={key:None for key in capsule['origin']}
        capsule['origin'].update(node_id=identity('example','SOURCE_VERSION','EQ',1),obligation_ids=[])
        capsule['verification_status_at_export']='UNVERIFIED_PAPER_IDENTITY'
        configuration.atomic_json(self.capsule_path,capsule); digest=hash_file(self.capsule_path)
        self.policy['projects']['example']['exports'][0]['sha256']=digest
        self.policy['projects']['other']['imports'][0]['sha256']=digest; self.save_policy()
        ref=self.search()['references'][0]; self.assertIsNone(ref['origin']['claim_id']); self.assertFalse(ref['positive_basis'])

    def test_target_adversary_change_requires_operator_repin(self):
        self.authorize(); self.write_model(self.target,'STATIC','q=7')
        with self.assertRaisesRegex(ValueError,'TARGET_MODEL_PIN_CHANGED'): self.search()

    def test_stronger_claim_assumptions_cannot_disappear_from_source_export(self):
        self.authorize(); self.legacy_claim(assumptions=['x is an integer','Additional strong fixture assumption'])
        for kind in ('proof','statement'):
            claim_graph.review(self.origin,'C-1',kind,'proofs/review.md','independent-operator','Review the new stronger toy claim')
        with self.assertRaisesRegex(ValueError,'TARGET_MODEL_BINDING'): self.preview()
        path=self.origin/'knowledge/shared/MODEL.json'; value=configuration.load_json(path)
        value['model']['assumptions'].append('Additional strong fixture assumption'); configuration.atomic_json(path,value)
        self.assertIn('Additional strong fixture assumption',self.preview()['model']['assumptions'])

    def test_repinning_model_does_not_rebind_problem_to_changed_goal(self):
        self.authorize(); (self.target/'GOAL.md').write_text('Operator changed the target goal',encoding='utf8')
        self.write_model(self.target,'ADAPTIVE','q=17')
        self.policy['projects']['other']['model_sha256']=hash_file(self.target/'knowledge/shared/MODEL.json'); self.save_policy()
        with self.assertRaisesRegex(ValueError,'TARGET_MODEL_PROBLEM_STALE'): self.search()


if __name__=='__main__': unittest.main()
