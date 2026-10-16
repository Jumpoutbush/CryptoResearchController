"""R12 read-only budgets remain owned by the old route and attempt controllers."""
import copy
import unittest
import configuration
import route_budget
import test_candidate_scheduler as fixture
from candidate_search import scheduler
from engine import discovery_scheduler


class CandidateBudgetTests(unittest.TestCase):
    setUp=fixture.CandidateSchedulerTests.setUp
    tearDown=fixture.CandidateSchedulerTests.tearDown
    put=fixture.CandidateSchedulerTests.put
    make=fixture.CandidateSchedulerTests.make
    candidate_spec=fixture.CandidateSchedulerTests.candidate_spec
    spec_problem=fixture.CandidateSchedulerTests.spec_problem
    add=fixture.CandidateSchedulerTests.add
    register_route=fixture.CandidateSchedulerTests.register_route
    selection=fixture.CandidateSchedulerTests.selection

    def test_three_candidates_share_one_unchanged_route_budget(self):
        path,data=self.register_route(); data['epochs'][-1]['effective_rounds']=2
        route_budget.save_ledger(path,data); before=path.read_bytes()
        for i in range(1,4): self.add('C-000'+str(i))
        for i in range(1,4): self.selection('C-000'+str(i))
        plan=scheduler.plan(self.project)
        self.assertEqual(plan['route_budget']['effective_rounds'],2)
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(len(list((self.root/'state/routes').glob('*.json'))),1)

    def test_exhausted_budget_routes_to_existing_review_without_new_call(self):
        path,data=self.register_route(); epoch=data['epochs'][-1]
        policy=route_budget.policy_for(self.root,self.project)[0]
        epoch['effective_rounds']=route_budget.total_budget(epoch,policy)
        route_budget.save_ledger(path,data); self.add(); before=path.read_bytes()
        plan=scheduler.plan(self.project)
        self.assertEqual(plan['status'],'ROUTE_REVIEW_REQUIRED')
        self.assertEqual(plan['route_budget']['review_reason'],'budget_exhausted')
        self.assertEqual(self.selection(plan=plan)['status'],'ROUTE_REVIEW_REQUIRED')
        self.assertEqual(path.read_bytes(),before)

    def test_stop_flag_and_operator_pause_are_preserved(self):
        self.add(); self.put('.control/STOP_REQUESTED','operator stop')
        self.assertEqual(scheduler.plan(self.project)['status'],'STOPPED')
        (self.project/'.control/STOP_REQUESTED').unlink()
        state=copy.deepcopy(self.state); state['decision']='NEEDS_REVIEW'; self.put('research/STATE.json',state)
        self.assertEqual(scheduler.plan(self.project)['status'],'STOPPED')

    def test_pending_review_and_stagnation_do_not_synthesize_extension(self):
        path,data=self.register_route(); data['epochs'][-1].update(review_pending=True,review_reason='operator_pending')
        route_budget.save_ledger(path,data); self.add(); before=path.read_bytes()
        plan=scheduler.plan(self.project)
        self.assertEqual(plan['route_budget']['review_reason'],'operator_pending')
        self.assertFalse(plan['budget_extension_requested']); self.assertEqual(path.read_bytes(),before)

    def test_registered_budget_loss_stops_and_is_not_recreated(self):
        path,data=self.register_route(); self.add(); path.unlink()
        with self.assertRaises(ValueError): scheduler.plan(self.project)
        self.assertFalse(path.exists())

    def test_attempt_usage_and_failed_calls_come_from_original_ledger(self):
        self.add(); attempt=discovery_scheduler.start(self.project,'P-1',version=1)
        discovery_scheduler.begin_call(self.project,'offline-failure')
        discovery_scheduler.finish_call(self.project,'offline-failure',accepted=False)
        plan=scheduler.plan(self.project)
        self.assertEqual(plan['attempt_budget']['calls_consumed'],1)
        self.assertEqual(plan['attempt_budget']['failed_calls'],['offline-failure'])
        self.assertEqual(plan['route_budget']['effective_rounds'],0)
