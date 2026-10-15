"""Decision evidence, idea integration and theory-first regression tests."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
import configuration
import research
import research_quality as quality
import theory_gate
import runner
import runner_core
import route_budget

SOURCE=Path(__file__).resolve().parents[1]

class QualityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        shutil.copytree(SOURCE/'config',self.root/'config')
        self.project=self.root/'projects/example';self.project.mkdir(parents=True)
        self.put('GOAL.md','A fixed cryptographic goal with a precise output interface.')
        self.put('PROJECT.json',{'id':'example','checks':[]})
        self.put('AGENTS.md','Keep the goal fixed.')
        self.put('RESEARCH_PROFILE.json',{'profiles':[],'read_order':[]})
        self.put('literature/queries.json',{'queries':['cryptography']})
        self.state={'phase':'FALSIFICATION','decision':'CONTINUE','research_route':'C/MAIN',
                    'priority_problem':'Decisive theoretical obstruction','next_task':'Prove the exact invariant or find a minimal counterexample.',
                    'last_run':None,'open_obligations':[],'verified_results':[],'publication_status':'NOT_ESTABLISHED'}
        self.put('research/STATE.json',self.state)
        self.put('proofs/claim.md','Infrastructure test witness; not a real mathematical proof.')
        self.put('literature/source.txt','Mock primary source used only to verify hash binding.')
        self.patches=[mock.patch.object(configuration,'ROOT',self.root),mock.patch.object(research,'ROOT',self.root)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def put(self,rel,obj):
        p=self.project/rel;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(obj,ensure_ascii=False,indent=2) if isinstance(obj,(dict,list)) else obj,encoding='utf8')
        return p
    def receipt(self,**updates):
        obj={'schema_version':1,'run_id':'r1','work_kind':'PROOF','core_problem':'A fixed core problem',
             'theoretical_obligation':'Prove a quantified condition','nontriviality_argument':'The existing result lacks this interface',
             'contribution_type':'NONE','result_status':'OPEN','evidence_paths':['proofs/claim.md']}
        obj.update(updates);self.put('research/ROUND_REVIEW.json',obj);return obj
    def review(self,**updates):
        obj={'schema_version':1,'claim_id':'C-1','paper':{'title':'Mock paper','version':'1',
              'source_file':'literature/source.txt','sha256':quality.hash_file(self.project/'literature/source.txt')},
             'fulltext_status':'TECHNICALLY_CHECKED','author_claim':'Author claims a result',
             'technical_statement':'The exact theorem under its assumptions','source_location':'Theorem 1, page 2',
             'comparison':[{'dimension':d,'idea':'Fixed property','paper':'Same property','relation':'MATCH',
                            'source_location':'Page 2','argument':'Explicit correspondence of conditions'} for d in sorted(quality.DIMENSIONS)],
             'construction_mapping':'Exact input and output mapping','reduction_argument':'Explicit derivation supplied separately',
             'limitations':'Only the fixed claim is considered','coverage_verdict':'COVERS','derivation_paths':['proofs/claim.md']}
        obj.update(updates);self.put('literature/technical_reviews/check.json',obj);return obj
    def verdict(self,**updates):
        obj={'outcome':'PIVOT_PROVISIONAL','failure_class':'LITERATURE_COVERAGE','failed_claim':'C-1',
             'failure_scope':'CORE_ROUTE','scope_argument':'Only the recorded route is affected',
             'dependency_argument':'This claim is necessary for the core route','evidence_paths':['proofs/claim.md'],
             'technical_review':'literature/technical_reviews/check.json'}
        obj.update(updates);return obj
    def test_author_claim_alone_does_not_kill_idea(self):
        self.put('literature/technical_reviews/check.json',{'author_claim':'Our work subsumes everything'})
        with self.assertRaises(ValueError):quality.validate_route_decision(self.project,self.verdict())
    def test_partial_overlap_can_be_recorded_but_cannot_pivot(self):
        self.review(coverage_verdict='PARTIAL_OVERLAP')
        self.assertEqual(quality.validate_technical_review(self.project,'literature/technical_reviews/check.json')['coverage_verdict'],'PARTIAL_OVERLAP')
        with self.assertRaises(ValueError):quality.validate_route_decision(self.project,self.verdict())
    def test_full_technical_comparison_and_derivation_allow_scoped_review(self):
        self.review();quality.validate_route_decision(self.project,self.verdict())
    def test_claim_mismatch_rejects_coverage(self):
        self.review()
        with self.assertRaises(ValueError):quality.validate_route_decision(self.project,self.verdict(failed_claim='C-2'))
    def test_stronger_idea_conditions_cannot_be_called_fully_covered(self):
        obj=self.review();obj['comparison'][0]['relation']='IDEA_STRONGER';self.review(**obj)
        with self.assertRaises(ValueError):quality.validate_route_decision(self.project,self.verdict())
    def test_changed_primary_source_invalidates_comparison(self):
        self.review();self.put('literature/source.txt','Different source revision')
        with self.assertRaises(ValueError):quality.validate_route_decision(self.project,self.verdict())
    def test_partial_claim_cannot_reject_whole_route(self):
        self.review()
        with self.assertRaises(ValueError):quality.validate_route_decision(self.project,self.verdict(failure_scope='SUBCLAIM_ONLY'))
    def test_budget_exhaustion_cannot_scientifically_reject_route(self):
        with self.assertRaises(ValueError):quality.validate_route_decision(self.project,self.verdict(failure_class='BUDGET_EXHAUSTED'))
    def test_engineering_candidate_is_not_a_theoretical_pivot(self):
        with self.assertRaises(ValueError):quality.validate_candidate(self.project,{'theoretical_contribution':{'type':'BENCHMARK'}})
    def test_missing_receipt_rejected(self):
        with self.assertRaises(OSError):quality.validate_round(self.project,'r1')
    def test_stale_receipt_rejected(self):
        self.receipt()
        with self.assertRaises(ValueError):quality.validate_round(self.project,'r2')
    def test_unchanged_evidence_not_counted_as_new(self):
        self.receipt()
        before={'proofs/claim.md':quality.hash_file(self.project/'proofs/claim.md')}
        with self.assertRaises(ValueError):quality.validate_round(self.project,'r1',before)
    def test_support_work_cannot_claim_new_primitive(self):
        self.receipt(work_kind='ENGINEERING_SUPPORT',contribution_type='CRYPTOGRAPHIC_PRIMITIVE',result_status='SUPPORT_ONLY',supports_claim='C-1',blocking_obligation='Verify input fixture')
        with self.assertRaises(ValueError):quality.validate_round(self.project,'r1')
    def test_no_progress_is_valid_and_honest_without_fake_evidence(self):
        self.receipt(result_status='NO_PROGRESS',evidence_paths=[])
        self.assertEqual(quality.validate_round(self.project,'r1',{})['result_status'],'NO_PROGRESS')
    def test_two_support_rounds_trigger_quality_review(self):
        policy,_,_=route_budget.policy_for(self.root,self.project)
        _,ledger,epoch=route_budget.load_ledger(self.root,self.project,self.state)
        for i in range(2):
            rid='support-'+str(i)
            self.receipt(run_id=rid,work_kind='ENGINEERING_SUPPORT',result_status='SUPPORT_ONLY',supports_claim='C-1',blocking_obligation='Check the exact fixture')
            self.put('research/ROUTE_SIGNAL.json',{'run_id':rid,'progress_type':'REPRODUCIBLE_TEST','reason':'Concrete support evidence has been saved for the bound theoretical obligation.','evidence_paths':['proofs/claim.md'],'route_blocked':False})
            runner.record_round(self.project,ledger,epoch,policy,{'last_run':rid},{})
        self.assertEqual(epoch['review_reason'],'support_work_without_theoretical_progress')
    def test_attach_keeps_main_task_and_pins_version(self):
        self.assertEqual(research.main(['ideas','add','example','--title','Extra lemma','--text','Original attached idea']),0)
        self.assertEqual(research.main(['ideas','attach','example','--id','IDEA-0001']),0)
        state=configuration.load_json(self.project/'research/STATE.json')
        for k in self.state:self.assertEqual(state[k],self.state[k])
        self.assertEqual(state['supporting_ideas'],[{'id':'IDEA-0001','version':1}])
        research.main(['ideas','update','example','--id','IDEA-0001','--text','Updated idea body','--reason','More precise statement'])
        context=runner_core.project_input_context(self.project)
        self.assertIn('Original attached idea',context);self.assertNotIn('Updated idea body',context)
        research.main(['ideas','attach','example','--id','IDEA-0001'])
        self.assertIn('Updated idea body',runner_core.project_input_context(self.project))
        research.main(['ideas','detach','example','--id','IDEA-0001'])
        self.assertEqual(configuration.load_json(self.project/'research/STATE.json')['supporting_ideas'],[])
    def test_project_stage_prompt_is_actually_loaded(self):
        self.put('prompts/stages/FALSIFICATION.md','PROJECT_SPECIFIC_STAGE_MARKER')
        result=runner_core.stage_instructions(self.project,'FALSIFICATION')
        self.assertIn('PROJECT_SPECIFIC_STAGE_MARKER',result)
        self.assertIn('决定性证伪',result)
    def approve(self):
        for name in ('contribution','correctness','novelty'):self.put('research/'+name+'.md','Operator review evidence for '+name)
        return research.main(['theory','approve','example','--claim','C-1','--contribution','research/contribution.md',
            '--correctness','research/correctness.md','--novelty','research/novelty.md','--reviewer','Test operator','--reason','Reviewed the bound theoretical claim'])
    def baseline(self):
        return {p.relative_to(self.project).as_posix():quality.hash_file(p) for p in self.project.rglob('*') if p.is_file()}
    def test_system_code_before_theory_is_rejected(self):
        before=self.baseline();self.put('src/server.py','print("full system")')
        with self.assertRaises(ValueError):theory_gate.validate_code_changes(self.project,before)
    def test_math_code_requires_specific_plan_and_is_bounded(self):
        before=self.baseline();self.put('proofs/checks/small.py','assert 1+1==2\n')
        with self.assertRaises(OSError):theory_gate.validate_code_changes(self.project,before)
        self.put('research/MATH_CHECK_PLAN.json',{'question':'Check a decisive exact equality','why_code_is_necessary':'Enumerate tiny finite cases',
            'success_criterion':'All cases satisfy the invariant','failure_criterion':'An explicit counterexample',
            'files':['proofs/checks/small.py'],'max_seconds':10})
        self.assertEqual(theory_gate.validate_code_changes(self.project,before),['proofs/checks/small.py'])
        self.put('proofs/checks/small.py','pass\n'*161)
        with self.assertRaises(ValueError):theory_gate.validate_code_changes(self.project,before)
    def test_theory_approval_binds_evidence_and_becomes_stale(self):
        self.assertEqual(self.approve(),0);self.assertEqual(theory_gate.check_readiness(self.project)['claim_id'],'C-1')
        self.put('research/correctness.md','Modified proof requires review')
        with self.assertRaises(ValueError):theory_gate.check_readiness(self.project)
    def test_new_idea_attachment_invalidates_theory_approval(self):
        self.approve();state=copy.deepcopy(self.state);state['supporting_ideas']=[{'id':'IDEA-7','version':1}]
        self.put('research/STATE.json',state)
        with self.assertRaises(ValueError):theory_gate.check_readiness(self.project)
    def test_system_phase_blocked_before_model_request(self):
        state=copy.deepcopy(self.state);state['phase']='IMPLEMENTATION';self.put('research/STATE.json',state)
        policy,_,_=route_budget.policy_for(self.root,self.project)
        path,ledger,epoch=route_budget.load_ledger(self.root,self.project,state)
        with mock.patch.object(runner,'run_child') as child:
            with self.assertRaises(ValueError):runner.advance_one(self.project,policy,path,ledger,epoch,['python','core'])
            child.assert_not_called()
    def test_system_work_requires_correct_approved_claim(self):
        self.approve();self.receipt(work_kind='SYSTEM_TEST',result_status='SUPPORT_ONLY',supports_claim='C-2',blocking_obligation='Approved component testing')
        with self.assertRaises(ValueError):quality.validate_round(self.project,'r1')
    def test_explicit_stage_change_needs_theory_first(self):
        self.assertEqual(research.main(['ready','example','--phase','IMPLEMENTATION']),2)
        self.approve()
        self.assertEqual(research.main(['ready','example','--phase','IMPLEMENTATION']),0)

if __name__=='__main__':unittest.main()
