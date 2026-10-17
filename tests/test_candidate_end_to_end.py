"""R15 scoped evidence resolution and explicit recoverable old-engine switches."""
import copy
import json
import unittest
from unittest import mock
import configuration
import route_budget
import test_candidate_scheduler as fixture
from candidate_search import catalog, history, resolution, scheduler
from candidate_search.verifiers import interface
from engine import claim_graph, discovery_scheduler
from engine.common import ledger, object_hash, save_ledger
import runner_core


class CandidateEndToEndTests(unittest.TestCase):
    setUp=fixture.CandidateSchedulerTests.setUp
    tearDown=fixture.CandidateSchedulerTests.tearDown
    put=fixture.CandidateSchedulerTests.put
    claim=fixture.CandidateSchedulerTests.claim
    review_proof=fixture.CandidateSchedulerTests.review_proof
    files=fixture.CandidateSchedulerTests.files
    make=fixture.CandidateSchedulerTests.make
    candidate_spec=fixture.CandidateSchedulerTests.candidate_spec
    spec_problem=fixture.CandidateSchedulerTests.spec_problem
    add=fixture.CandidateSchedulerTests.add
    selection=fixture.CandidateSchedulerTests.selection
    register_route=fixture.CandidateSchedulerTests.register_route

    def card(self,status='CONDITIONAL',**updates):
        value={'schema_version':1,'requested_status':status,'scope':'Only the exact candidate revision and equality obligation.',
            'restart_conditions':'A genuinely changed hypothesis and fresh independent scope review.',
            'reason':'Offline branch resolution fixture','verification_request_id':None,
            'semantic_review_file':None,'source_dependencies':[],'reusable_lemmas':[]}
        value.update(updates); return value

    def seed(self):
        self.add(hypothesis='For all integer x, x*x == x.')
        self.add('C-0002',hypothesis='An alternative construction without the false equality requirement.')
        self.claim('CLAIM-A',statement='For all integer x, x*x == x.',
            machine_statement={'domain':'INTEGER','variables':['x'],'preconditions':[],'conclusion':'x*x == x'})

    def refutation(self):
        self.seed(); request=interface.prepare_request(self.project,'C-0001','CLAIM-A')
        interface.verify(self.project,request)
        report=resolution.semantic_review_template(self.project,'C-0001','CLAIM-A','REFUTED',
            scope=self.card()['scope'],verification_request_id=request['request_id'])
        report.update(reviewer='independent-operator',necessity_argument='This exact candidate requires the equality lemma for every integer; the frozen target does not require that equality.')
        self.put('research/branch_reviews/A.json',report)
        claim_graph.review(self.project,'CLAIM-A','statement','research/branch_reviews/A.json','independent-operator','Independently attest exact local scope')
        return self.card('REFUTED',verification_request_id=request['request_id'],semantic_review_file='research/branch_reviews/A.json')

    def test_unreviewed_refutation_request_remains_conditional(self):
        self.seed(); prepared=resolution.prepare_request(self.project,'C-0001','CLAIM-A',self.card('REFUTED'))
        report=resolution.resolve(self.project,prepared)
        self.assertEqual(report['status'],'CONDITIONAL'); self.assertFalse(report['scientific_acceptance'])

    def test_machine_certificate_alone_cannot_refute_candidate_or_family(self):
        self.seed(); request=interface.prepare_request(self.project,'C-0001','CLAIM-A'); interface.verify(self.project,request)
        card=self.card('REFUTED',verification_request_id=request['request_id'])
        result=resolution.resolve(self.project,resolution.prepare_request(self.project,'C-0001','CLAIM-A',card))
        self.assertEqual(result['status'],'CONDITIONAL')

    def test_exact_certificate_and_original_independent_review_refute_only_local_candidate(self):
        card=self.refutation(); before=(self.project/'research/discovery/CLAIM_GRAPH.json').read_bytes()
        result=resolution.resolve(self.project,resolution.prepare_request(self.project,'C-0001','CLAIM-A',card))
        self.assertEqual(result['status'],'REFUTED'); self.assertEqual(result['scope_type'],'EXACT_CANDIDATE_REVISION')
        self.assertFalse(result['parent_or_family_refuted']); self.assertEqual(catalog.show(self.project,'C-0002')['status'],'READY_FOR_ATTEMPT')
        self.assertEqual(before,(self.project/'research/discovery/CLAIM_GRAPH.json').read_bytes())

    def test_missing_original_coverage_source_is_conditional(self):
        self.seed(); card=self.card('COVERED')
        result=resolution.resolve(self.project,resolution.prepare_request(self.project,'C-0001','CLAIM-A',card))
        self.assertEqual(result['status'],'CONDITIONAL')

    def test_legacy_manual_refuted_status_is_not_scientific_evidence(self):
        self.seed(); catalog.transition(self.project,'C-0001','REFUTED','Old manual label',expected_revision=1,
            disposition={'scope':'Only toy candidate','restart_conditions':'New inputs','evidence_refs':[]})
        result=resolution.resolve(self.project,resolution.prepare_request(self.project,'C-0001','CLAIM-A',self.card('REFUTED')))
        self.assertEqual(result['status'],'CONDITIONAL')

    def test_retire_without_claim_retains_history_and_evidence(self):
        self.add(); proof=(self.project/'proofs/derivation.md').read_bytes()
        result=resolution.retire(self.project,'C-0001',expected_revision=1,reason='Cancel direction',
            scope='This candidate only',restart_conditions='Fresh independent review before any restart')
        self.assertEqual(result['status'],'RETIRED'); self.assertEqual(proof,(self.project/'proofs/derivation.md').read_bytes())
        self.assertEqual(len(history.projection_records(self.project)),1)

    def test_duplicate_resolution_is_idempotent(self):
        card=self.refutation(); request=resolution.prepare_request(self.project,'C-0001','CLAIM-A',card)
        first=resolution.resolve(self.project,request); second=resolution.resolve(self.project,request)
        self.assertEqual(first['resolution_id'],second['resolution_id'])
        self.assertEqual(len(history.projection_records(self.project)),1)

    def test_original_evidence_change_blocks_resolution_without_science_writes(self):
        card=self.refutation(); request=resolution.prepare_request(self.project,'C-0001','CLAIM-A',card)
        self.put('proofs/derivation.md','Changed after exact certificate')
        result=resolution.resolve(self.project,request)
        self.assertEqual(result['status'],'FAILED')

    def test_history_corruption_or_loss_is_not_silently_reenrolled(self):
        self.add(); resolution.retire(self.project,'C-0001',expected_revision=1,reason='Retire',scope='Exact revision',restart_conditions='New review')
        path=history.path(self.project); old=path.read_bytes(); path.unlink()
        with self.assertRaises(ValueError): history.projection_records(self.project)
        path.write_bytes(old); value=json.loads(old); value['events'].pop(); configuration.atomic_json(path,value)
        with self.assertRaises(ValueError): history.projection_records(self.project)

    def start_a(self):
        self.seed(); selected=self.selection(); attempt=discovery_scheduler.start(self.project,'P-1',version=1)
        scheduler.bind_attempt(self.project,selected['selection']['selection_id'],attempt['id'],reason='Before dispatch')
        return attempt

    def test_explicit_close_then_start_b_uses_original_engine_and_one_route_epoch(self):
        path,data=self.register_route(); data['epochs'][-1]['effective_rounds']=2; route_budget.save_ledger(path,data)
        attempt=self.start_a(); route_before=path.read_bytes()
        close=resolution.prepare_switch(self.project,'C-0001',phase='CLOSE',reason='Explicit close A',expected_revision=1,from_attempt_id=attempt['id'])
        self.assertEqual(resolution.apply_switch(self.project,close)['status'],'APPLIED')
        self.assertIsNone(discovery_scheduler.active(self.project))
        start=resolution.prepare_switch(self.project,'C-0002',phase='START',reason='Explicit start B',expected_revision=1)
        self.assertEqual(resolution.apply_switch(self.project,start)['status'],'APPLIED')
        self.assertEqual(len(ledger(self.project)['attempts']),2)
        self.assertEqual(discovery_scheduler.active(self.project)['id'],'attempt-0002')
        self.assertEqual(path.read_bytes(),route_before)

    def test_unknown_original_call_blocks_close_and_preserves_active_owner(self):
        attempt=self.start_a(); discovery_scheduler.begin_call(self.project,'unknown-run')
        with self.assertRaisesRegex(ValueError,'pending|UNKNOWN|RECOVERY'):
            resolution.prepare_switch(self.project,'C-0001',phase='CLOSE',reason='No unsafe close',expected_revision=1,from_attempt_id=attempt['id'])
        self.assertEqual(discovery_scheduler.active(self.project)['id'],attempt['id'])

    def test_stop_or_route_review_prevents_switch(self):
        self.start_a(); self.put('.control/STOP_REQUESTED','stop')
        with self.assertRaises(ValueError):
            resolution.prepare_switch(self.project,'C-0001',phase='CLOSE',reason='Blocked',expected_revision=1)

    def test_close_failure_keeps_old_owner_and_does_not_start_b(self):
        attempt=self.start_a(); request=resolution.prepare_switch(self.project,'C-0001',phase='CLOSE',reason='Close failure',expected_revision=1)
        with mock.patch('configuration.os.replace',side_effect=OSError('injected write failure')):
            with self.assertRaises(OSError): resolution.apply_switch(self.project,request)
        self.assertEqual(discovery_scheduler.active(self.project)['id'],attempt['id'])

    def test_forged_refutation_decision_with_recomputed_digest_is_rejected(self):
        self.seed(); request=resolution.prepare_request(self.project,'C-0001','CLAIM-A',self.card('REFUTED'))
        request['decision']='REFUTED'; request['gaps']=[]
        request['request_sha256']=object_hash({k:v for k,v in request.items() if k not in {'request_id','request_sha256'}})
        request['request_id']='BR-'+request['request_sha256']; before=catalog.path(self.project).read_bytes()
        result=resolution.resolve(self.project,request)
        self.assertEqual(result['status'],'FAILED'); self.assertEqual(before,catalog.path(self.project).read_bytes())
        self.assertEqual(history.projection_records(self.project),[])

    def partial_start(self):
        self.seed(); request=resolution.prepare_switch(self.project,'C-0002',phase='START',reason='Frozen B start',expected_revision=1)
        original=configuration.atomic_json
        def stop_state(path,value):
            if path==self.project/'research/STATE.json': raise OSError('injected after ledger before STATE')
            return original(path,value)
        with mock.patch('configuration.atomic_json',side_effect=stop_state):
            with self.assertRaises(OSError): resolution.apply_switch(self.project,request)
        return request

    def assert_dispatch_blocked(self):
        for call in (lambda:discovery_scheduler.check(self.project),lambda:discovery_scheduler.start(self.project,'P-1'),
                     lambda:discovery_scheduler.close(self.project,'No bypass')):
            with self.assertRaisesRegex(ValueError,'CANDIDATE_SWITCH_RECOVERY_REQUIRED'): call()
        with mock.patch('runner_core.subprocess.Popen') as spawn, mock.patch('theory_gate.require_system_ready'):
            with self.assertRaisesRegex(ValueError,'CANDIDATE_SWITCH_RECOVERY_REQUIRED'):
                runner_core.run_round(self.project,round_num=1,seconds=1,skip_fetch=True,offline=True)
            spawn.assert_not_called()

    def test_partial_start_old_dispatch_is_fenced_and_recovers_one_original_owner(self):
        request=self.partial_start(); self.assert_dispatch_blocked()
        result=resolution.recover_switch(self.project,request['request_id'])
        self.assertEqual(result['status'],'APPLIED'); self.assertEqual(len(ledger(self.project)['attempts']),1)
        self.assertEqual(discovery_scheduler.active(self.project)['id'],'attempt-0001')
        self.assertEqual(resolution.recover_switch(self.project,request['request_id']),result)
        self.assertEqual(len(ledger(self.project)['attempts']),1)

    def test_single_intent_loss_after_partial_start_keeps_old_and_direct_dispatch_blocked(self):
        request=self.partial_start(); resolution._paths(self.project,request['request_id'],'switches')['intent'].unlink()
        self.assert_dispatch_blocked()
        with self.assertRaises(ValueError): resolution.recover_switch(self.project,request['request_id'])
        self.assertEqual(len(ledger(self.project)['attempts']),1)

    def test_single_witness_loss_after_partial_start_does_not_reconstruct_inputs(self):
        request=self.partial_start(); resolution._paths(self.project,request['request_id'],'switches')['witness'].unlink()
        self.assert_dispatch_blocked()
        with self.assertRaisesRegex(ValueError,'witness'): resolution.recover_switch(self.project,request['request_id'])

    def test_partial_start_third_party_state_bytes_are_not_overwritten(self):
        request=self.partial_start(); path=self.project/'research/STATE.json'
        path.write_text(json.dumps(json.loads(path.read_text()),sort_keys=True),encoding='utf8'); old=path.read_bytes()
        with self.assertRaisesRegex(ValueError,'third-party|CONFLICT'): resolution.recover_switch(self.project,request['request_id'])
        self.assertEqual(old,path.read_bytes()); self.assertEqual(len(ledger(self.project)['attempts']),1)

    def test_switch_history_append_crash_only_rolls_forward_frozen_local_receipt(self):
        self.seed(); request=resolution.prepare_switch(self.project,'C-0002',phase='START',reason='Frozen history append',expected_revision=1)
        original=configuration.atomic_json
        def stop_history(path,value):
            if path==history.path(self.project): raise OSError('injected after history high-water witness')
            return original(path,value)
        with mock.patch('configuration.atomic_json',side_effect=stop_history):
            with self.assertRaises(OSError): resolution.apply_switch(self.project,request)
        self.assert_dispatch_blocked()
        result=resolution.recover_switch(self.project,request['request_id'])
        self.assertEqual(result['status'],'APPLIED'); self.assertEqual(len(ledger(self.project)['attempts']),1)
        self.assertEqual(len(history.view(self.project)['events']),1)

    def test_partial_close_blocks_old_dispatch_and_does_not_start_next_candidate(self):
        self.start_a(); request=resolution.prepare_switch(self.project,'C-0001',phase='CLOSE',reason='Explicit close',expected_revision=1)
        original=history.append
        with mock.patch.object(history,'append',side_effect=OSError('after close ledger before receipt')):
            with self.assertRaises(OSError): resolution.apply_switch(self.project,request)
        self.assertIsNone(discovery_scheduler.active(self.project)); self.assert_dispatch_blocked()
        result=resolution.recover_switch(self.project,request['request_id'])
        self.assertEqual(result['phase'],'CLOSE'); self.assertEqual(len(ledger(self.project)['attempts']),1)
        self.assertIsNone(discovery_scheduler.active(self.project))

    def test_prepared_start_rechecks_independent_dependency_review(self):
        self.claim('LEMMA-B'); self.review_proof('LEMMA-B'); item=claim_graph.get(self.project,'LEMMA-B')
        self.add('C-0002',dependency_claims=[{'id':item['id'],'revision':item['revision'],'spec_sha256':item['spec_sha256']}])
        request=resolution.prepare_switch(self.project,'C-0002',phase='START',reason='Reviewed dependency',expected_revision=1)
        self.put('research/statement-LEMMA-B.md','Changed original independent review')
        with self.assertRaisesRegex(ValueError,'dependency|readiness'): resolution.apply_switch(self.project,request)
        self.assertIsNone(discovery_scheduler.active(self.project)); self.assertEqual(ledger(self.project)['attempts'],[])

    def test_scope_review_revocation_persists_after_restoring_original_bytes(self):
        card=self.refutation(); path=self.project/card['semantic_review_file']; old=path.read_bytes()
        prepared=resolution.prepare_request(self.project,'C-0001','CLAIM-A',card)
        path.write_text('temporarily changed original independent evidence',encoding='utf8'); claim_graph.refresh(self.project); path.write_bytes(old)
        result=resolution.resolve(self.project,prepared); self.assertEqual(result['status'],'FAILED')
        self.assertEqual(resolution.prepare_request(self.project,'C-0001','CLAIM-A',card)['decision'],'CONDITIONAL')
        claim_graph.review(self.project,'CLAIM-A','statement',card['semantic_review_file'],'independent-operator','Fresh scope review after observed invalidation')
        self.assertEqual(resolution.prepare_request(self.project,'C-0001','CLAIM-A',card)['decision'],'REFUTED')

    def test_real_r07_pdf_theorem_and_original_coverage_mapping_can_cover_exact_candidate(self):
        self.add(hypothesis='For every integer x, x*x >= 0.'); self.claim('CLAIM-A')
        from scripts.r07_fixture import seed
        span=seed(self.project,claim_id='CLAIM-A')
        dependency={'span_id':span['id'],'source_file':span['source_file'],'version':span['version'],'sha256':span['sha256'],
            'location':{k:span['location'][k] for k in ('page_start','page_end','theorem','excerpt')},
            'required_assumptions':['Same integer invariant'],'used_assumptions':['Same integer invariant'],'proof_step':'O-1'}
        report=resolution.semantic_review_template(self.project,'C-0001','CLAIM-A','COVERED',scope=self.card()['scope'])
        report.update(reviewer='independent-operator',necessity_argument='The exact local candidate obligation follows by the original theorem under every preserved source premise; no family conclusion is made.')
        self.put('research/coverage-scope.json',report)
        claim_graph.review(self.project,'CLAIM-A','statement','research/coverage-scope.json','independent-operator','Exact independent coverage scope')
        card=self.card('COVERED',source_dependencies=[dependency],semantic_review_file='research/coverage-scope.json')
        omitted=copy.deepcopy(card); omitted['source_dependencies'][0]['used_assumptions']=[]
        self.assertEqual(resolution.prepare_request(self.project,'C-0001','CLAIM-A',omitted)['decision'],'CONDITIONAL')
        prepared=resolution.prepare_request(self.project,'C-0001','CLAIM-A',card)
        self.assertEqual(prepared['decision'],'COVERED',prepared['gaps'])
        self.assertEqual(resolution.resolve(self.project,prepared)['status'],'COVERED')

    def test_direct_dependency_lemma_requires_actual_consumer_pin_and_is_kept(self):
        self.seed(); self.claim('LEMMA'); self.review_proof('LEMMA'); lemma=claim_graph.get(self.project,'LEMMA')
        pin={'id':'LEMMA','revision':lemma['revision'],'spec_sha256':lemma['spec_sha256'],'scope':'DIRECT_DEPENDENCY',
             'consumer_claim':'CLAIM-A','dependency_argument':'The exact declared lemma supplies the local integer step.'}
        with self.assertRaisesRegex(ValueError,'DIRECT_DEPENDENCY'):
            resolution.prepare_request(self.project,'C-0001','CLAIM-A',self.card(reusable_lemmas=[pin]))
        self.claim('CONSUMER',deps=['LEMMA']); pin['consumer_claim']='CONSUMER'
        result=resolution.resolve(self.project,resolution.prepare_request(self.project,'C-0001','CLAIM-A',self.card(reusable_lemmas=[pin])))
        self.assertEqual(result['reusable_lemmas'][0]['proof_status'],'INDEPENDENTLY_REVIEWED')
        self.assertFalse(result['reusable_lemmas'][0]['positive_basis'])
        self.assertEqual(next(r for r in claim_graph.status(self.project)['claims'] if r['id']=='LEMMA')['proof_status'],'INDEPENDENTLY_REVIEWED')

    def test_close_cannot_substitute_another_candidate_on_same_fixed_problem(self):
        self.start_a()
        with self.assertRaisesRegex(ValueError,'bound owner'):
            resolution.prepare_switch(self.project,'C-0002',phase='CLOSE',reason='Wrong candidate same P',expected_revision=1,from_attempt_id='attempt-0001')

    def test_stale_checkpoint_cannot_be_closed_or_recovered_past_review(self):
        self.start_a(); data=ledger(self.project)
        from research_quality import hash_file
        data['attempts'][0]['checkpoint']={'evidence':{'proofs/derivation.md':hash_file(self.project/'proofs/derivation.md')}}
        save_ledger(self.project,data)
        request=resolution.prepare_switch(self.project,'C-0001',phase='CLOSE',reason='Checkpoint retained',expected_revision=1)
        with mock.patch('candidate_search.resolution.discovery.commit_prepared',side_effect=OSError('before old close')):
            with self.assertRaises(OSError): resolution.apply_switch(self.project,request)
        self.put('proofs/derivation.md','Changed accepted checkpoint evidence')
        with self.assertRaisesRegex(ValueError,'ATTEMPT_STALE'): resolution.recover_switch(self.project,request['request_id'])
        self.assertEqual(discovery_scheduler.active(self.project)['status'],'ACTIVE')

    def test_real_exhausted_attempt_can_close_without_resetting_route_consumption(self):
        configuration.atomic_json(self.root/'config/projects/example.json',{'discovery_policy':{'initial_round_budget':1}})
        path,data=self.register_route(); before=path.read_bytes(); self.start_a()
        discovery_scheduler.begin_call(self.project,'failed-consumed-call')
        discovery_scheduler.finish_call(self.project,'failed-consumed-call',accepted=False)
        self.assertEqual(discovery_scheduler.active(self.project)['status'],'BUDGET_EXHAUSTED')
        request=resolution.prepare_switch(self.project,'C-0001',phase='CLOSE',reason='Consumed attempt closed under unchanged route budget',expected_revision=1)
        result=resolution.apply_switch(self.project,request)
        self.assertEqual(result['status'],'APPLIED'); self.assertIsNone(discovery_scheduler.active(self.project))
        self.assertEqual(len(ledger(self.project)['attempts'][0]['calls']),1); self.assertEqual(path.read_bytes(),before)

    def test_rehashed_legacy_close_plan_cannot_bypass_state_cas(self):
        self.start_a(); request=resolution.prepare_switch(self.project,'C-0001',phase='CLOSE',reason='Freeze STATE',expected_revision=1)
        request['engine_plan']=discovery_scheduler.prepare_close(self.project,'Freeze STATE')
        request['request_sha256']=object_hash({k:v for k,v in request.items() if k not in {'request_id','request_sha256'}}); request['request_id']='SW-'+request['request_sha256']
        with self.assertRaisesRegex(ValueError,'STATE beforeimage'): resolution.apply_switch(self.project,request)

    def test_rehashed_switch_cannot_drop_scientific_pins_or_invent_consumption(self):
        self.seed(); request=resolution.prepare_switch(self.project,'C-0002',phase='START',reason='Frozen B',expected_revision=1)
        for field,value in [('evidence_bindings',{}),('route_effective_rounds',999)]:
            forged=copy.deepcopy(request); forged[field]=value
            forged['request_sha256']=object_hash({k:v for k,v in forged.items() if k not in {'request_id','request_sha256'}}); forged['request_id']='SW-'+forged['request_sha256']
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'frozen route'):
                resolution.apply_switch(self.project,forged)
        self.assertIsNone(discovery_scheduler.active(self.project))

    def test_restart_needs_exact_old_resolution_and_new_independent_scope(self):
        card=self.refutation(); resolved=resolution.resolve(self.project,resolution.prepare_request(self.project,'C-0001','CLAIM-A',card))
        changed=copy.deepcopy(catalog.show(self.project,'C-0001')['spec']); changed['hypothesis']='For all integer x, x*x is nonnegative; the false equality is no longer required.'
        catalog.propose(self.project,changed,'Genuinely changed hypothesis',revise=True,expected_revision=1)
        catalog.transition(self.project,'C-0001','READY_FOR_ATTEMPT','Original independent readiness',expected_revision=2)
        with self.assertRaisesRegex(ValueError,'independent'): resolution.prepare_switch(self.project,'C-0001',phase='START',reason='Needs restart scope',expected_revision=2)
        review=resolution.restart_review_template(self.project,'C-0001','CLAIM-A')
        self.assertEqual(review['previous_resolution_id'],resolved['resolution_id'])
        review.update(reviewer='independent-operator',why_old_evidence_not_applicable='The old witness refutes the discarded equality only; this revised hypothesis retains the original integer goal and requires a separate proof.')
        self.put('research/restart-scope.json',review)
        claim_graph.review(self.project,'CLAIM-A','statement','research/restart-scope.json','independent-operator','Independently attest changed hypothesis and exact old resolution')
        prepared=resolution.prepare_switch(self.project,'C-0001',phase='START',reason='Reviewed changed hypothesis',expected_revision=2)
        self.assertEqual(prepared['restart_review']['file'],'research/restart-scope.json')
        path=self.project/'research/restart-scope.json'; old=path.read_bytes(); path.write_text('changed review',encoding='utf8'); claim_graph.refresh(self.project); path.write_bytes(old)
        with self.assertRaisesRegex(ValueError,'restart|Restart'): resolution.apply_switch(self.project,prepared)
