"""R14 protocol review findings never attest security or mutate research authority."""
import copy
import unittest
from unittest import mock
import configuration
import test_candidate_contract as fixture
from candidate_search import security_model, security_review
from engine import claim_graph, problem_compiler
from engine.common import object_hash


class SecurityReviewTests(unittest.TestCase):
    tearDown=fixture.CandidateContractTests.tearDown
    put=fixture.CandidateContractTests.put
    claim=fixture.CandidateContractTests.claim
    files=fixture.CandidateContractTests.files
    candidate_spec=fixture.CandidateContractTests.candidate_spec
    make=fixture.CandidateContractTests.make
    spec_problem=fixture.CandidateContractTests.spec_problem
    add=fixture.CandidateContractTests.add

    def setUp(self):
        fixture.CandidateContractTests.setUp(self)
        self.model={'corruption_timing':'STATIC','corruption_threshold':1,'leakage_function':'L-main','party_count':3}
        self.model['ideal_interface_sha256']=object_hash(security_model.ideal_interface_binding(self.card()))
        self.spec['security_model']=self.model
        problem_compiler.import_problem(self.project,self.spec,'Register exact synthetic protocol model')
        self.add(problem_version=2,security_model=self.model)
        self.claim('CLAIM-1',problem_version=2)

    def card(self):
        value=security_model.template(); value['proof_paths']=['proofs/derivation.md']
        value['security_game'].update(definition='A frozen synthetic game, not a security theorem.',rounds=1,public_outputs=['output'])
        value['parties']=['client','server','auditor']
        value['corruption_model'].update(timing='STATIC',claimed_timing='STATIC',threshold=1,claimed_threshold=1,
                                         corrupted_parties=['server'],dropout_model='NONE')
        value['leakage_function'].update(name='L-main',real_observable=['output'],ideal_leakage=['output'],cross_round_linkage='NONE')
        value['setup_assumptions']=copy.deepcopy(self.spec['assumptions'])
        value['abort_behavior']={k:False for k in value['abort_behavior']}
        value['simulator_interface'].update(ideal_inputs=['output'],required_inputs=['output'],
                                            output_dependencies={'output':['output']})
        value['reduction_loss'].update(parameters=['n'],bit_widths={'n':32},rounds=1,
            failure_events=['abort'],loss_bound='Declared symbolic loss, requiring independent review')
        value['composition_scope'].update(sessions=1,rounds=1,cross_round_collusion='NONE',
                                           end_to_end_reduction='An explicit pending proof obligation')
        for row in value['baseline_comparison']:
            row.update(assumptions='Exact setup still needs source comparison',functionality='Frozen output',
                       cost='UNASSESSED',difference='No independent novelty assertion')
        return value

    def prepare(self,card=None):
        return security_model.prepare_request(self.project,'C-0001','CLAIM-1',card or self.card())

    def review(self,card=None):
        return security_review.review(self.project,self.prepare(card))

    def codes(self,report): return {f['code'] for f in report['findings']}

    def trace(self,kind,steps):
        return {'id':'A-1','kind':kind,'game':'GAME-main','proof_step':'hybrid-1','affected_obligations':['O-1'],
                'execution':steps,'scope':'Fixed synthetic inputs only','restart_conditions':'A revised independently checked model'}

    def step(self,**updates):
        value={'round':1,'corrupted_parties':['server'],'public_inputs':{'query':'q'},
               'secret_assignment':{'secret':0},'ideal_leakage':{'output':'same'},'public_output':{'output':'same'}}
        value.update(updates); return value

    def test_complete_card_is_only_finding_and_does_not_modify_scientific_authority(self):
        before=self.files()
        with mock.patch('subprocess.Popen',side_effect=AssertionError('No review/Lean/executable dispatch')):
            report=self.review()
        self.assertEqual(report['finding_level'],'REVIEW_FINDING')
        self.assertFalse(report['claim_status_changed']); self.assertFalse(report['scientific_acceptance'])
        after=self.files()
        protected=lambda files:{k:v for k,v in files.items() if not k.startswith(('state/candidates/','locks/'))}
        self.assertEqual(protected(before),protected(after))

    def test_missing_adversary_model_stays_needs_input(self):
        card=self.card(); card['corruption_model']['timing']=None
        report=self.review(card)
        self.assertEqual(report['decision'],'NEEDS_INPUT'); self.assertFalse(report['threat_model_complete'])

    def test_static_security_cannot_be_promoted_to_adaptive(self):
        card=self.card(); card['corruption_model']['claimed_timing']='ADAPTIVE'
        self.assertIn('MODEL_SCOPE_MISMATCH',self.codes(self.review(card)))

    def test_corruption_above_frozen_threshold_is_out_of_scope_not_a_break(self):
        card=self.card(); card['corruption_model']['claimed_threshold']=2
        card['attack_traces']=[self.trace('CORRUPTION_THRESHOLD',[self.step(corrupted_parties=['server','auditor'])])]
        report=self.review(card)
        self.assertIn('MODEL_SCOPE_MISMATCH',self.codes(report))
        self.assertEqual(report['attack_plans'][0]['status'],'OUT_OF_SCOPE')
        self.assertFalse(report['attack_plans'][0]['counterexample_to_frozen_goal'])

    def test_selective_rejection_reports_same_ideal_view_and_different_visible_bit(self):
        card=self.card(); card['abort_behavior'].update(public_reject_bit=True,ideal_reject_bit=False)
        card['leakage_function']['real_observable'].append('reject_bit')
        card['attack_traces']=[self.trace('SELECTIVE_REJECTION',[
            self.step(public_output={'output':'same','reject_bit':False}),
            self.step(secret_assignment={'secret':1},public_output={'output':'same','reject_bit':True})])]
        report=self.review(card)
        self.assertIn('REJECTION_BIT_OMITTED_FROM_IDEAL_LEAKAGE',self.codes(report))
        self.assertEqual(report['attack_plans'][0]['status'],'FINITE_TRACE_DIFFERENCE_REQUIRES_REVIEW')

    def test_simulator_cannot_assume_secret_or_unauthorized_programming(self):
        card=self.card(); card['simulator_interface']['required_inputs'].append('secret_key')
        card['simulator_interface']['required_programming']=['random_oracle']
        card['simulator_interface']['output_dependencies']['output']=['secret_key']
        report=self.review(card)
        self.assertIn('SIMULATOR_INPUT_UNAVAILABLE',self.codes(report))
        self.assertIn('UNAUTHORIZED_SIMULATOR_PROGRAMMING',self.codes(report))

    def test_cross_round_collusion_undefined_stays_needs_input(self):
        card=self.card(); card['composition_scope'].update(rounds=2,cross_round_collusion=None)
        report=self.review(card)
        self.assertEqual(report['decision'],'NEEDS_INPUT'); self.assertIn('CROSS_ROUND_COLLUSION_UNDEFINED',self.codes(report))

    def test_no_cost_breakdown_is_unassessed_even_with_cheap_claim(self):
        card=self.card(); card['baseline_comparison'][0]['cost']='O(1) claimed without breakdown'
        report=self.review(card)
        self.assertEqual(report['cost_assessment']['status'],'UNASSESSED')

    def test_missing_source_version_and_location_are_unverified(self):
        card=self.card(); card['dependencies']=[{'span_id':None,'source_file':None,'version':None,'sha256':None,
            'location':None,'required_assumptions':['authenticated setup'],'used_assumptions':[], 'proof_step':'hybrid-1'}]
        report=self.review(card)
        self.assertEqual(report['decision'],'NEEDS_SOURCE'); self.assertEqual(report['source_checks'][0]['status'],'UNVERIFIED')

    def test_deleted_theorem_premises_are_reported_not_silently_relaxed(self):
        card=self.card(); card['setup_assumptions']=[]
        self.assertIn('FROZEN_PREMISES_OMITTED',self.codes(self.review(card)))

    def test_component_security_is_not_end_to_end_reduction(self):
        card=self.card(); card['composition_scope'].update(component_theorems=['Component-A'],end_to_end_reduction=None)
        self.assertIn('END_TO_END_REDUCTION_MISSING',self.codes(self.review(card)))

    def test_three_framework_comparisons_and_potential_coverage_are_explicit(self):
        card=self.card(); card['baseline_comparison'][0]['relation']='DIRECT_COMPOSITION'
        report=self.review(card)
        self.assertEqual(len(report['framework_comparison']),3)
        self.assertIn('POTENTIALLY_COVERED',self.codes(report))
        self.assertFalse(report['candidate_status_changed'])

    def test_prohibited_authority_fields_and_executable_trace_rejected(self):
        for key,value in [('accepted_contribution',True),('G8','PASS'),('reviewer_attestation','independent')]:
            card=self.card(); card[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError): self.prepare(card)
        card=self.card(); card['attack_traces']=[{'program':'arbitrary.py'}]
        with self.assertRaises(ValueError): self.prepare(card)
        card=self.card(); trace=self.trace('CORRUPTION_THRESHOLD',[self.step()]); trace['affected_obligations']=[]
        card['attack_traces']=[trace]
        with self.assertRaises(ValueError): self.prepare(card)

    def test_same_request_is_idempotent_and_readers_have_no_writes(self):
        request=self.prepare(); report=security_review.review(self.project,request)
        with mock.patch('candidate_search.security_review._analyze',side_effect=AssertionError('No duplicate review')):
            self.assertEqual(report,security_review.review(self.project,request))
        before=self.files(); security_review.show(self.project,request['request_id']); security_review.recheck(self.project,request['request_id'])
        self.assertEqual(before,self.files())

    def test_source_change_invalidates_old_report(self):
        request=self.prepare(); security_review.review(self.project,request)
        self.put('proofs/derivation.md','Changed proof under review')
        self.assertEqual(security_review.recheck(self.project,request['request_id'])['decision'],'FAILED')

    def test_interrupted_review_has_unknown_outcome_without_automatic_retry(self):
        request=self.prepare()
        with mock.patch('candidate_search.security_review._analyze',side_effect=KeyboardInterrupt('interrupted review')):
            with self.assertRaises(KeyboardInterrupt): security_review.review(self.project,request)
        with mock.patch('candidate_search.security_review._analyze',side_effect=AssertionError('No retry')):
            report=security_review.review(self.project,request)
        self.assertEqual(report['decision'],'FAILED'); self.assertIn('UNKNOWN_LOCAL_SECURITY_REVIEW_OUTCOME',str(report))

    def test_card_cannot_self_authorize_unavailable_secret_or_programming(self):
        card=self.card(); card['simulator_interface']['ideal_inputs'].append('secret_key')
        card['simulator_interface']['required_inputs'].append('secret_key')
        card['simulator_interface']['authorized_programming'].append('random_oracle')
        card['simulator_interface']['required_programming'].append('random_oracle')
        report=self.review(card)
        self.assertEqual(report['decision'],'NEEDS_INPUT'); self.assertFalse(report['threat_model_complete'])
        self.assertIn('MODEL_SCOPE_MISMATCH',self.codes(report))

    def test_static_trace_cannot_rotate_corrupted_party_set(self):
        card=self.card(); card['attack_traces']=[self.trace('CORRUPTION_THRESHOLD',[
            self.step(corrupted_parties=['server']),self.step(corrupted_parties=['auditor'])])]
        self.assertEqual(self.review(card)['attack_plans'][0]['status'],'OUT_OF_SCOPE')

    def test_incomplete_reduction_bound_names_exact_missing_fields(self):
        card=self.card(); card['reduction_loss']['failure_events']=[]
        report=self.review(card); finding=next(f for f in report['findings'] if f['code']=='REDUCTION_BOUND_INCOMPLETE')
        self.assertIn('failure_events',finding['detail'])

    def test_new_independent_review_and_review_evidence_change_stale_report(self):
        request=self.prepare(); security_review.review(self.project,request)
        self.put('research/operator-proof.md','An operator-attested proof review fixture')
        claim_graph.review(self.project,'CLAIM-1','proof','research/operator-proof.md','independent-reviewer','Explicit audit fixture')
        self.assertEqual(security_review.recheck(self.project,request['request_id'])['decision'],'FAILED')
        fresh=self.prepare(); security_review.review(self.project,fresh)
        self.put('research/operator-proof.md','Changed original independent review')
        self.assertEqual(security_review.recheck(self.project,fresh['request_id'])['decision'],'FAILED')

    def test_actual_r07_pdf_source_span_is_located_and_premises_preserved(self):
        from scripts.r07_fixture import seed
        span=seed(self.project,claim_id='CLAIM-1'); card=self.card()
        card['dependencies']=[{'span_id':span['id'],'source_file':span['source_file'],'version':span['version'],
            'sha256':span['sha256'],'location':{k:span['location'][k] for k in ('page_start','page_end','theorem','excerpt')},
            'required_assumptions':['An omitted explicit source premise'],'used_assumptions':[], 'proof_step':'hybrid-1'}]
        report=self.review(card)
        self.assertEqual(report['source_checks'][0]['status'],'SOURCE_LOCATION_ONLY')
        self.assertIn('THEOREM_PREMISES_OMITTED',self.codes(report))
        self.assertIn('POTENTIALLY_COVERED',self.codes(report))
        self.assertFalse(report['candidate_status_changed'])
