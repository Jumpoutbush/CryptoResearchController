"""R12 deterministic advice and pre-dispatch ownership, using offline fixtures."""
import copy
import json
import unittest
from unittest import mock

import configuration
import route_budget
import research_acceptance
import test_candidate_contract as fixture
from candidate_search import catalog, scheduler
from engine import claim_graph, discovery_scheduler, problem_compiler
from engine.common import ledger, save_ledger


class CandidateSchedulerTests(unittest.TestCase):
    setUp = fixture.CandidateContractTests.setUp
    tearDown = fixture.CandidateContractTests.tearDown
    put = fixture.CandidateContractTests.put
    claim = fixture.CandidateContractTests.claim
    review_proof = fixture.CandidateContractTests.review_proof
    files = fixture.CandidateContractTests.files
    make = fixture.CandidateContractTests.make
    candidate_spec = fixture.CandidateContractTests.candidate_spec
    spec_problem = fixture.CandidateContractTests.spec_problem
    register_route = fixture.CandidateContractTests.register_route

    def add(self, cid='C-0001', *, ready=True, **updates):
        item=fixture.CandidateContractTests.add(self,cid,**updates)
        if ready:
            catalog.transition(self.project,cid,'READY_FOR_ATTEMPT','Reviewed offline fixed contract',expected_revision=1)
        return item

    def selection(self, cid='C-0001', plan=None):
        plan = plan or scheduler.plan(self.project)
        snapshot = plan['snapshot']
        return scheduler.select(self.project, cid, expected_revision=1, reason='Explicit offline advice',
            expected_goal_anchor_id=snapshot['goal_anchor_id'], expected_route_epoch=snapshot['route_epoch'],
            expected_last_processed_run=snapshot['last_processed_run'],
            expected_snapshot_sha256=plan['snapshot_sha256'])

    def machine_candidate(self, cid='C-0001'):
        self.claim('LEMMA-1', machine_statement={'domain':'INTEGER','variables':['x'],
            'preconditions':[], 'conclusion':'x*x >= 0'})
        claim = claim_graph.get(self.project, 'LEMMA-1')
        return self.add(cid, ready=False, dependency_claims=[{'id':claim['id'], 'revision':claim['revision'],
                                               'spec_sha256':claim['spec_sha256']}])

    def bind(self, selected):
        attempt = discovery_scheduler.start(self.project, 'P-1', version=1)
        scheduler.bind_attempt(self.project, selected['selection']['selection_id'], attempt['id'], reason='Before any calls')
        return attempt

    def test_plan_readonly_deterministic_and_declarations_unknown(self):
        self.add(); before = self.files()
        first = scheduler.plan(self.project); self.assertEqual(first, scheduler.plan(self.project))
        self.assertEqual(before, self.files())
        self.assertEqual(first['rankings'][0]['dimensions']['decisive_falsification']['status'], 'UNKNOWN')
        self.assertEqual(first['rankings'][0]['dimensions']['prior_coverage']['status'], 'UNKNOWN')
        self.assertFalse(first['execution_allowed'])

    def test_decisive_machine_predicate_beats_unverified_cheap_claim(self):
        self.add('C-0001', estimated_context_bytes=1)
        self.machine_candidate('C-0002')
        plan = scheduler.plan(self.project)
        self.assertEqual(plan['next_candidate'], 'C-0002')
        dimension = plan['rankings'][0]['dimensions']['decisive_falsification']
        self.assertEqual(dimension['status'], 'COMPUTABLE_PREDICATE_PENDING')
        self.assertTrue(dimension['facts'])
        self.assertFalse(dimension['positive_basis'])

    def test_select_is_advice_only_without_import_attempt_or_budget(self):
        self.add(); before = self.files(); selected = self.selection()
        self.assertEqual(selected['status'], 'PENDING_OPERATOR_REVIEW')
        self.assertFalse(selected['execution_allowed'])
        after = self.files()
        self.assertEqual({k:v for k,v in before.items() if not k.startswith('locks/')}, {k:v for k,v in after.items() if not k.startswith((
            'state/candidates/', 'state/candidate_selection_registry/', 'locks/'))} | {
            k:v for k,v in after.items() if k in before and k.startswith('state/candidates/')})
        self.assertIsNone(discovery_scheduler.active(self.project))

    def test_duplicate_selection_is_idempotent(self):
        self.add(); plan=scheduler.plan(self.project); first = self.selection(plan=plan)
        before = scheduler.status(self.project); second = self.selection(plan=plan)
        self.assertEqual(first['selection']['selection_id'],second['selection']['selection_id'])
        self.assertTrue(second['idempotent']); self.assertEqual(before,scheduler.status(self.project))

    def test_old_plan_cannot_select_another_candidate_after_history_advanced(self):
        self.add(); self.add('C-0002'); plan=scheduler.plan(self.project)
        self.selection(plan=plan)
        with self.assertRaisesRegex(ValueError,'STALE'): self.selection('C-0002',plan=plan)

    def test_unknown_cost_never_gains_a_lower_cost_score(self):
        self.add('C-0001',estimated_context_bytes=1)
        self.claim('LEMMA-1'); self.review_proof('LEMMA-1')
        item=claim_graph.get(self.project,'LEMMA-1')
        self.add('C-0002',estimated_context_bytes=100000,dependency_claims=[
            {'id':item['id'],'revision':item['revision'],'spec_sha256':item['spec_sha256']}])
        for rank in scheduler.plan(self.project)['rankings']:
            self.assertFalse(rank['dimensions']['cost']['used_for_ranking'])
            self.assertEqual(rank['priority_vector'][-1],0)

    def test_unaccounted_state_run_blocks_before_original_model_retry(self):
        self.register_route(); self.add(); state=copy.deepcopy(self.state); state['last_run']='unaccounted'
        self.put('research/STATE.json',state)
        plan=scheduler.plan(self.project)
        self.assertEqual(plan['status'],'RECOVERY_REQUIRED')
        self.assertIn('UNACCOUNTED_ORIGINAL_RUN',str(plan['blocking_reasons']))

    def test_active_attempt_always_defers_without_switching(self):
        self.add(); attempt = discovery_scheduler.start(self.project, 'P-1', version=1)
        before = ledger(self.project)
        plan = scheduler.plan(self.project)
        self.assertEqual(plan['status'], 'DEFERRED_UNTIL_ATTEMPT_CLOSE')
        result = self.selection(plan=plan)
        self.assertEqual(result['status'], 'DEFERRED_UNTIL_ATTEMPT_CLOSE')
        self.assertEqual(before, ledger(self.project)); self.assertEqual(result['active_attempt_id'], attempt['id'])

    def test_all_compare_and_swap_inputs_are_enforced(self):
        self.add(); plan = scheduler.plan(self.project)
        for field, wrong in [('goal_anchor_id','0'*64), ('route_epoch',999), ('last_processed_run','different')]:
            changed = copy.deepcopy(plan); changed['snapshot'][field] = wrong
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'STALE'):
                self.selection(plan=changed)
        with self.assertRaisesRegex(ValueError, 'STALE'):
            scheduler.select(self.project, 'C-0001', expected_revision=2, reason='Wrong revision',
                expected_goal_anchor_id=plan['snapshot']['goal_anchor_id'], expected_route_epoch=1,
                expected_last_processed_run=None, expected_snapshot_sha256=plan['snapshot_sha256'])

    def test_catalog_revision_after_plan_invalidates_snapshot(self):
        self.add(); plan = scheduler.plan(self.project); self.add('C-0002')
        with self.assertRaisesRegex(ValueError, 'STALE'): self.selection(plan=plan)

    def test_closed_attempt_with_unknown_call_still_blocks(self):
        self.add(); attempt = discovery_scheduler.start(self.project, 'P-1', version=1)
        discovery_scheduler.begin_call(self.project, 'unknown-run')
        data = ledger(self.project); data['active_attempt'] = None; data['attempts'][0]['status'] = 'CLOSED'
        save_ledger(self.project, data)
        plan = scheduler.plan(self.project)
        self.assertEqual(plan['status'], 'RECOVERY_REQUIRED')
        self.assertIn('unknown-run', str(plan['blocking_reasons']))

    def test_pending_wrapper_acceptance_stops_without_retry(self):
        self.add()
        with mock.patch('research_acceptance.load', return_value={'phase':'COMMIT_DECIDED'}):
            plan = scheduler.plan(self.project)
        self.assertEqual(plan['status'], 'RECOVERY_REQUIRED')
        self.assertFalse(plan['automatic_retry_allowed'])

    def test_selection_history_missing_or_corrupt_stops(self):
        self.add(); self.selection(); path = scheduler.history_path(self.project); before = path.read_bytes()
        path.unlink()
        with self.assertRaises(ValueError): scheduler.status(self.project)
        path.write_bytes(before); value = json.loads(before); value['events'].pop()
        configuration.atomic_json(path,value)
        with self.assertRaises(ValueError): scheduler.status(self.project)

    def test_pre_dispatch_binding_freezes_owner_without_changing_attempt(self):
        self.add(); selected = self.selection(); attempt = discovery_scheduler.start(self.project,'P-1',version=1)
        before = ledger(self.project)
        result = scheduler.bind_attempt(self.project,selected['selection']['selection_id'],attempt['id'],reason='Freeze owner')
        self.assertEqual(result['binding']['attempt_id'], attempt['id']); self.assertEqual(before,ledger(self.project))

    def test_retroactive_binding_after_call_is_forbidden(self):
        self.add(); selected = self.selection(); attempt = discovery_scheduler.start(self.project,'P-1',version=1)
        discovery_scheduler.begin_call(self.project,'already-dispatched')
        with self.assertRaisesRegex(ValueError,'dispatch|calls'):
            scheduler.bind_attempt(self.project,selected['selection']['selection_id'],attempt['id'],reason='Too late')

    def test_mapping_requires_pre_dispatch_binding(self):
        self.add(); selected = self.selection()
        with self.assertRaisesRegex(ValueError,'binding'):
            scheduler.record_run_mapping(self.project,selected['selection']['selection_id'],'unknown',
                expected_attempt_id='attempt-0001',reason='No binding')

    def test_failed_call_maps_once_and_never_charges_route(self):
        self.add(); selected = self.selection(); attempt = self.bind(selected)
        discovery_scheduler.begin_call(self.project,'failed-offline-run')
        discovery_scheduler.finish_call(self.project,'failed-offline-run',accepted=False)
        before = ledger(self.project)
        first = scheduler.record_run_mapping(self.project,selected['selection']['selection_id'],'failed-offline-run',
            expected_attempt_id=attempt['id'],reason='Map actual failed local fixture')
        second = scheduler.record_run_mapping(self.project,selected['selection']['selection_id'],'failed-offline-run',
            expected_attempt_id=attempt['id'],reason='Idempotent repeat')
        self.assertEqual(first['mapping'],second['mapping']); self.assertTrue(second['idempotent'])
        self.assertEqual(first['mapping']['call_status'],'FAILED'); self.assertEqual(before,ledger(self.project))

    def test_reserved_result_unknown_cannot_be_mapped_or_retried(self):
        self.add(); selected = self.selection(); attempt = self.bind(selected)
        discovery_scheduler.begin_call(self.project,'pending-offline-run')
        before = ledger(self.project)
        with self.assertRaisesRegex(ValueError,'UNKNOWN|pending'):
            scheduler.record_run_mapping(self.project,selected['selection']['selection_id'],'pending-offline-run',
                expected_attempt_id=attempt['id'],reason='Unknown external outcome')
        self.assertEqual(before,ledger(self.project))

    def test_binding_to_wrong_problem_or_candidate_revision_is_rejected(self):
        self.add(); selected = self.selection()
        spec = copy.deepcopy(self.spec); spec['id']='P-2'; problem_compiler.import_problem(self.project,spec,'Another fixed problem')
        attempt = discovery_scheduler.start(self.project,'P-2',version=1)
        with self.assertRaisesRegex(ValueError,'problem'):
            scheduler.bind_attempt(self.project,selected['selection']['selection_id'],attempt['id'],reason='Wrong problem')

    def test_independent_lock_owner_prevents_second_writer(self):
        self.add(); key=configuration.project_id(self.project)
        with route_budget.file_lock(self.root/'locks'/('route-'+key+'.lock')):
            with self.assertRaises(RuntimeError): self.selection()

    def test_interrupted_history_write_recovers_only_original_local_operation(self):
        self.add(); plan=scheduler.plan(self.project); original=configuration.atomic_json
        def fail_history(path,value):
            if str(path)==str(scheduler.history_path(self.project)): raise OSError('injected before history replace')
            return original(path,value)
        with mock.patch('configuration.atomic_json',side_effect=fail_history):
            with self.assertRaises(OSError): self.selection(plan=plan)
        with self.assertRaisesRegex(ValueError,'RECOVERY_REQUIRED'): scheduler.status(self.project)
        with self.assertRaisesRegex(ValueError,'RECOVERY_REQUIRED'):
            scheduler.select(self.project,'C-0001',expected_revision=1,reason='Changed operation reason',
                expected_goal_anchor_id=plan['snapshot']['goal_anchor_id'],expected_route_epoch=1,
                expected_last_processed_run=None,expected_snapshot_sha256=plan['snapshot_sha256'])
        recovered=self.selection(plan=plan)
        self.assertTrue(recovered['idempotent']); self.assertEqual(scheduler.status(self.project)['history_event_count'],1)

    def test_interrupted_final_witness_write_does_not_duplicate_selection(self):
        self.add(); plan=scheduler.plan(self.project); original=configuration.atomic_json; writes=[]
        def fail_commit(path,value):
            if str(path)==str(scheduler.registry_path(self.project)):
                writes.append(path)
                if len(writes)==2: raise OSError('injected after durable history')
            return original(path,value)
        with mock.patch('configuration.atomic_json',side_effect=fail_commit):
            with self.assertRaises(OSError): self.selection(plan=plan)
        restored=self.selection(plan=plan)
        self.assertTrue(restored['idempotent']); self.assertEqual(scheduler.status(self.project)['history_event_count'],1)

    def test_missing_selection_witness_cannot_be_silently_reenrolled(self):
        self.add(); self.selection(); scheduler.registry_path(self.project).unlink()
        with self.assertRaisesRegex(ValueError,'registry is missing'): scheduler.status(self.project)

    def test_paused_zero_call_attempt_cannot_be_bound(self):
        self.add(); selected=self.selection(); attempt=discovery_scheduler.start(self.project,'P-1',version=1)
        data=ledger(self.project); data['attempts'][0]['status']='PAUSED_STAGNATION'; save_ledger(self.project,data)
        with self.assertRaisesRegex(ValueError,'preflight'):
            scheduler.bind_attempt(self.project,selected['selection']['selection_id'],attempt['id'],reason='Paused owner')

    def test_tampered_terminal_call_or_deleted_settlement_cannot_be_mapped(self):
        self.add(); selected=self.selection(); attempt=self.bind(selected)
        discovery_scheduler.begin_call(self.project,'failed-receipt')
        discovery_scheduler.finish_call(self.project,'failed-receipt',accepted=False)
        receipt=discovery_scheduler._settlement_path(self.project,attempt['id'],'failed-receipt'); receipt.unlink()
        with self.assertRaises(ValueError):
            scheduler.record_run_mapping(self.project,selected['selection']['selection_id'],'failed-receipt',
                expected_attempt_id=attempt['id'],reason='Missing original receipt')

    def accepted_fixture(self):
        self.register_route(); self.add(); selected=self.selection(); attempt=self.bind(selected); rid='accepted-offline-run'
        discovery_scheduler.begin_call(self.project,rid)
        discovery_scheduler.finish_call(self.project,rid,accepted=True)
        state=copy.deepcopy(self.state); state['last_run']=rid; self.put('research/STATE.json',state)
        path,data,epoch=route_budget.load_ledger(self.root,self.project,state)
        epoch['effective_rounds']+=1; epoch['counted_run_ids'].append(rid); epoch['last_processed_run']=rid
        data['events'].append({'type':'RESEARCH_ROUND','run_id':rid,'route':epoch['route'],
            'anchor_id':selected['selection']['snapshot']['goal_anchor_id']})
        route_budget.save_ledger(path,data)
        # Isolated seeded original wrapper authority; no research/model execution.
        journal={'schema_version':1,'project_id':'example','phase':'COMPLETE','transaction_id':'f'*32,
            'route_path':'state/routes/example.json','run_id':rid,'discovery_owner_attempt_id':attempt['id'],
            'route_after':copy.deepcopy(data)}
        return selected,attempt,rid,journal

    def test_accepted_mapping_requires_original_complete_acceptance(self):
        selected,attempt,rid,journal=self.accepted_fixture()
        with self.assertRaisesRegex(ValueError,'COMPLETE acceptance receipt is missing'):
            scheduler.record_run_mapping(self.project,selected['selection']['selection_id'],rid,
                expected_attempt_id=attempt['id'],reason='No complete acceptance')
        research_acceptance.write(self.root,self.project,journal)
        result=scheduler.record_run_mapping(self.project,selected['selection']['selection_id'],rid,
            expected_attempt_id=attempt['id'],reason='Map original seeded completed receipt')
        self.assertEqual(result['mapping']['call_status'],'ACCEPTED')
        self.assertFalse(result['mapping']['scientific_acceptance'])

    def test_needs_input_and_uninitialized_state_stop_advice(self):
        self.add(); state=copy.deepcopy(self.state); state['initialization_required']=True
        self.put('research/STATE.json',state)
        self.assertEqual(scheduler.plan(self.project)['status'],'STOPPED')

    def test_five_proposals_have_only_three_evidence_ordered_frontier_slots(self):
        for number in range(1,6): self.add('C-000'+str(number),ready=False)
        plan=scheduler.plan(self.project)
        self.assertEqual(plan['frontier_limit'],3)
        self.assertEqual([r['candidate_id'] for r in plan['rankings']],['C-0001','C-0002','C-0003'])
        self.assertEqual([r['candidate_id'] for r in plan['deferred_candidates']],['C-0004','C-0005'])
        self.assertTrue(all(r['reason']=='OUTSIDE_BOUNDED_SCHEDULING_FRONTIER' for r in plan['deferred_candidates']))
        with self.assertRaisesRegex(ValueError,'OUTSIDE_SCHEDULING_FRONTIER'):
            self.selection('C-0004',plan=plan)

    def test_three_admitted_candidates_cannot_be_evicted_by_decisive_new_proposal(self):
        for number in range(1,4): self.add('C-000'+str(number))
        self.machine_candidate('C-0004')
        plan=scheduler.plan(self.project)
        self.assertEqual({r['candidate_id'] for r in plan['rankings']},{'C-0001','C-0002','C-0003'})
        self.assertEqual(plan['deferred_candidates'][0]['candidate_id'],'C-0004')
        with self.assertRaisesRegex(ValueError,'OUTSIDE_SCHEDULING_FRONTIER'):
            self.selection('C-0004',plan=plan)
