"""Acceptance is a durable decision, never a stdout side effect (T03/T04)."""
import builtins
import copy
import json
import os
import subprocess
import sys
from pathlib import Path
import unittest
from unittest import mock

import route_budget
import runner
import runner_core
import test_runner as fixture
import test_discovery as discovery_fixture
from test_runner import put


class AcceptanceReviewTests(unittest.TestCase):
    setUp = fixture.RunnerTests.setUp
    tearDown = fixture.RunnerTests.tearDown
    state = staticmethod(fixture.RunnerTests.state)
    current = fixture.RunnerTests.current
    impact = fixture.RunnerTests.impact
    complete = fixture.RunnerTests.complete

    def prepare(self):
        policy, _, _ = route_budget.policy_for(self.root, self.project)
        path, ledger, epoch = route_budget.load_ledger(self.root, self.project, self.current())
        route_budget.save_ledger(path, ledger)
        return policy, path, ledger, epoch

    def test_stdout_failure_after_route_save_keeps_accepted_project_and_recovers(self):
        policy, path, ledger, epoch = self.prepare()
        real_print = builtins.print
        def fail_progress(*args, **kwargs):
            if args and args[0] == 'ROUTE_PROGRESS:':
                raise BrokenPipeError('Injected after route save')
            return real_print(*args, **kwargs)
        with mock.patch.object(runner, 'run_child', side_effect=lambda _: (self.complete() or 0)), \
             mock.patch.object(runner_core, 'git_checkpoint', return_value='TEST'), \
             mock.patch('builtins.print', side_effect=fail_progress):
            with self.assertRaises(BrokenPipeError):
                runner.advance_one(self.project, policy, path, ledger, epoch, ['fake'])
        self.assertEqual(self.current()['last_run'], 'round-1')
        self.assertTrue((self.project/'proofs/new.md').exists())
        saved = route_budget.read_json(path)
        self.assertEqual(saved['epochs'][-1]['counted_run_ids'], ['round-1'])
        with mock.patch.object(runner, 'run_child', side_effect=AssertionError('Must not redispatch')), \
             mock.patch.object(runner_core, 'git_checkpoint', return_value='TEST'):
            result = runner.advance_one(self.project, policy, path, saved, saved['epochs'][-1], ['fake'])
        self.assertEqual(result, (0, 'RECOVERED_ACCEPTED_ROUND'))
        self.assertEqual(route_budget.read_json(path)['epochs'][-1]['effective_rounds'], 1)

    def test_post_accept_failure_does_not_rollback_or_repeat_research(self):
        policy, path, ledger, epoch = self.prepare()
        from engine import discovery_scheduler
        with mock.patch.object(runner, 'run_child', side_effect=lambda _: (self.complete() or 0)), \
             mock.patch.object(discovery_scheduler, 'finalize_wrapper', side_effect=OSError('Before finalize')):
            with self.assertRaises(OSError):
                runner.advance_one(self.project, policy, path, ledger, epoch, ['fake'])
        self.assertEqual(self.current()['last_run'], 'round-1')
        saved = route_budget.read_json(path)
        with mock.patch.object(runner, 'run_child', side_effect=AssertionError('Must not redispatch')), \
             mock.patch.object(runner_core, 'git_checkpoint', return_value='TEST'):
            self.assertEqual(runner.advance_one(self.project, policy, path, saved, saved['epochs'][-1], ['fake']),
                             (0, 'RECOVERED_ACCEPTED_ROUND'))
        self.assertEqual(route_budget.read_json(path)['epochs'][-1]['counted_run_ids'], ['round-1'])

    def test_committed_journal_late_write_error_cannot_rollback(self):
        import research_acceptance
        policy, path, ledger, epoch = self.prepare()
        real_write = research_acceptance.atomic_json
        def late(path, obj):
            real_write(path, obj)
            if obj.get('phase') == 'COMMIT_DECIDED': raise OSError('After durable decision')
        with mock.patch.object(runner, 'run_child', side_effect=lambda _: (self.complete() or 0)), \
             mock.patch.object(research_acceptance, 'atomic_json', side_effect=late):
            with self.assertRaises(OSError):
                runner.advance_one(self.project, policy, path, ledger, epoch, ['fake'])
        self.assertEqual(self.current()['last_run'], 'round-1')
        saved = route_budget.read_json(path)
        with mock.patch.object(runner, 'run_child', side_effect=AssertionError('Must not redispatch')), \
             mock.patch.object(runner_core, 'git_checkpoint', return_value='TEST'):
            self.assertEqual(runner.advance_one(self.project, policy, path, saved, saved['epochs'][-1], ['fake']),
                             (0, 'RECOVERED_ACCEPTED_ROUND'))

    def test_recovery_preserves_intervening_operator_edit(self):
        policy, path, ledger, epoch = self.prepare()
        from engine import discovery_scheduler
        with mock.patch.object(runner, 'run_child', side_effect=lambda _: (self.complete() or 0)), \
             mock.patch.object(discovery_scheduler, 'finalize_wrapper', side_effect=OSError('Before finalize')):
            with self.assertRaises(OSError): runner.advance_one(self.project, policy, path, ledger, epoch, ['fake'])
        put(self.project/'proofs/new.md', 'Operator correction must never be overwritten')
        saved = route_budget.read_json(path)
        with mock.patch.object(runner, 'run_child', side_effect=AssertionError('Must not redispatch')):
            with self.assertRaisesRegex(ValueError, 'ACCEPTANCE.*CHANGED'):
                runner.advance_one(self.project, policy, path, saved, saved['epochs'][-1], ['fake'])
        self.assertEqual((self.project/'proofs/new.md').read_text(), 'Operator correction must never be overwritten')

    def test_knowledge_failure_does_not_queue_or_apply(self):
        policy, path, ledger, epoch = self.prepare()
        with mock.patch.object(runner, 'run_child', side_effect=lambda _: (self.complete() or 0)), \
             mock.patch.object(runner, 'refresh_knowledge', return_value={'status':'failed','error':'injected'}), \
             mock.patch.object(runner, 'queue_supervision_after_accept') as queue, \
             mock.patch.object(runner_core, 'git_checkpoint', return_value='TEST'):
            result=runner.advance_one(self.project, policy, path, ledger, epoch, ['fake'])
        self.assertEqual(result, (3, 'KNOWLEDGE_INDEX_FAILED'))
        queue.assert_not_called()
        self.assertEqual(self.current()['last_run'], 'round-1')

    def crashed_child(self, stage):
        source=Path(__file__).resolve().parents[1]
        driver='''import os,sys
from pathlib import Path
from unittest import mock
import configuration,runner,runner_core,route_budget,research_acceptance
sys.path.insert(0,str(Path(sys.argv[1])/'tests'))
from test_runner import RunnerTests
root=Path(sys.argv[2]); project=root/'projects/subject'
case=RunnerTests(); case.root=root; case.project=project
def child(command):
    counter=root/'provider-count.txt'
    counter.write_text(str(int(counter.read_text())+1) if counter.exists() else '1')
    case.complete()
    return 0
def fault(stage):
    if stage==sys.argv[3]: os._exit(77)
with mock.patch.object(configuration,'ROOT',root),mock.patch.object(runner,'HERE',root),mock.patch.object(runner,'CORE',root/'runner_core.py'),mock.patch.object(runner_core,'ROOT',root),mock.patch.object(runner,'run_child',side_effect=child),mock.patch.object(research_acceptance,'fault_hook',side_effect=fault):
    policy=route_budget.policy_for(root,project)[0]
    path,data,epoch=route_budget.load_ledger(root,project,case.current())
    runner.advance_one(project,policy,path,data,epoch,['fake'])
'''
        result=subprocess.run([sys.executable,'-B','-c',driver,str(source),str(self.root),stage],
                              cwd=source,capture_output=True,text=True,timeout=45)
        self.assertEqual(result.returncode,77,result.stdout+result.stderr)

    def test_real_hard_exit_after_decision_rolls_route_forward_without_model(self):
        self.prepare(); self.crashed_child('COMMIT_DECIDED')
        with mock.patch.object(runner,'run_child',side_effect=AssertionError('No research retry')), \
             mock.patch.object(runner_core,'git_checkpoint',return_value='TEST'):
            self.assertEqual(runner.main(['--project',str(self.project),'--no-fetch']),0)
        path=self.root/'state/routes/subject.json'
        self.assertEqual(route_budget.read_json(path)['epochs'][-1]['counted_run_ids'],['round-1'])
        self.assertEqual((self.root/'provider-count.txt').read_text(),'1')
        self.assertEqual(self.current()['last_run'],'round-1')

    def test_real_hard_exit_after_route_save_restores_only_postaccept_work(self):
        self.prepare(); self.crashed_child('ROUTE_SAVED')
        policy,path,data,epoch=self.prepare()
        with mock.patch.object(runner,'run_child',side_effect=AssertionError('No research retry')), \
             mock.patch.object(runner_core,'git_checkpoint',return_value='TEST'):
            self.assertEqual(runner.advance_one(self.project,policy,path,data,epoch,['fake']),
                             (0,'RECOVERED_ACCEPTED_ROUND'))
        self.assertEqual(route_budget.read_json(path)['epochs'][-1]['effective_rounds'],1)
        self.assertEqual((self.root/'provider-count.txt').read_text(),'1')

    def test_precommit_unknown_and_existing_core_lock_stop_before_writes(self):
        import research_acceptance
        self.prepare(); self.crashed_child('STARTED')
        before=research_acceptance.manifest(self.project)
        with mock.patch.object(runner,'run_child',side_effect=AssertionError('No research retry')):
            self.assertEqual(runner.main(['--project',str(self.project)]),3)
        self.assertEqual(before,research_acceptance.manifest(self.project))
        self.assertFalse((self.root/'provider-count.txt').exists())
        with route_budget.file_lock(self.root/'locks/subject.lock'), \
             mock.patch.object(research_acceptance,'manifest',side_effect=AssertionError('Never inspect an active core')):
            with self.assertRaisesRegex(RuntimeError,'Another route controller'):
                runner.recover_acceptance(self.project,route_budget.policy_for(self.root,self.project)[0])

    def test_operator_edit_after_all_steps_still_blocks_recovery(self):
        policy,path,data,epoch=self.prepare()
        with mock.patch.object(runner,'run_child',side_effect=lambda _: (self.complete() or 0)), \
             mock.patch.object(runner,'finish_status',side_effect=OSError('After queue, before status')):
            with self.assertRaises(OSError): runner.advance_one(self.project,policy,path,data,epoch,['fake'])
        put(self.project/'proofs/new.md','Late operator correction')
        with mock.patch.object(runner_core,'git_checkpoint') as checkpoint:
            with self.assertRaisesRegex(ValueError,'ACCEPTANCE_PROJECT_CHANGED'):
                runner.recover_acceptance(self.project,policy)
        checkpoint.assert_not_called()

    def test_output_validation_and_commit_hold_the_execution_lock(self):
        policy,path,data,epoch=self.prepare()
        completed=runner.core_completed
        def check_locked(*args):
            with self.assertRaises(RuntimeError):
                with route_budget.file_lock(self.root/'locks/subject.lock'): pass
            return completed(*args)
        with mock.patch.object(runner,'run_child',side_effect=lambda _: (self.complete() or 0)), \
             mock.patch.object(runner,'core_completed',side_effect=check_locked), \
             mock.patch.object(runner_core,'git_checkpoint',return_value='TEST'):
            self.assertEqual(runner.advance_one(self.project,policy,path,data,epoch,['fake'])[0],0)

    def test_direct_core_cannot_bypass_an_unresolved_wrapper(self):
        import research_acceptance
        policy,path,data,epoch=self.prepare()
        transaction=runner_core.ProjectTransaction(self.project).capture()
        research_acceptance.begin(self.root,self.project,transaction,path,data)
        before=research_acceptance.manifest(self.project)
        with mock.patch.object(runner_core,'codex_run',side_effect=AssertionError('No direct core model')):
            self.assertEqual(runner_core.main(['--project',str(self.project),'--skip-fetch','--max-seconds','30']),3)
        self.assertEqual(before,research_acceptance.manifest(self.project))

    def test_complete_archive_failure_replays_with_original_timestamp(self):
        import research_acceptance
        policy,path,data,epoch=self.prepare()
        actual=research_acceptance.atomic_json
        def fail_archive(path,obj):
            actual(path,obj)
            if path.parent.name=='subject' and obj.get('phase')=='COMPLETE':
                raise OSError('Archive was replaced before helper failed')
        with mock.patch.object(runner,'run_child',side_effect=lambda _: (self.complete() or 0)), \
             mock.patch.object(runner_core,'git_checkpoint',return_value='TEST'), \
             mock.patch.object(research_acceptance,'atomic_json',side_effect=fail_archive):
            with self.assertRaises(OSError): runner.advance_one(self.project,policy,path,data,epoch,['fake'])
        pending=research_acceptance.load(self.root,self.project)
        self.assertEqual(pending['phase'],'COMMIT_DECIDED')
        with mock.patch.object(runner,'run_child',side_effect=AssertionError('No retry')), \
             mock.patch.object(runner_core,'git_checkpoint',return_value='TEST'):
            self.assertEqual(runner.recover_acceptance(self.project,policy),(0,'RECOVERED_ACCEPTED_ROUND'))
        complete=research_acceptance.load(self.root,self.project)
        self.assertEqual(complete['finished_at'],pending['finished_at'])
        self.assertEqual(complete['phase'],'COMPLETE')


class ActiveAcceptanceReviewTests(unittest.TestCase):
    setUp=discovery_fixture.DiscoveryTests.setUp
    tearDown=discovery_fixture.DiscoveryTests.tearDown
    put=discovery_fixture.DiscoveryTests.put

    def test_hard_exit_before_discovery_recovers_original_pending_checkpoint_once(self):
        from engine import discovery_scheduler as scheduler
        from engine.common import ledger
        scheduler.start(self.project,'P-1')
        source=Path(__file__).resolve().parents[1]
        driver='''import os,sys
from pathlib import Path
from unittest import mock
import configuration,runner,runner_core,route_budget,research_acceptance
from engine import discovery_scheduler as scheduler
sys.path.insert(0,str(Path(sys.argv[1])/'tests'))
from test_discovery import DiscoveryTests
root=Path(sys.argv[2]); project=root/'projects/example'
case=DiscoveryTests(); case.root=root; case.project=project
def child(command):
    (root/'research-dispatch-count.txt').write_text('1')
    scheduler.begin_call(project,'r1')
    case.fake_codex(project,'','r1')
    case.put('research/ROUTE_SIGNAL.json',{'run_id':'r1','progress_type':'PROOF_STEP','reason':'A precise independent checkpoint fixture has been saved','evidence_paths':['proofs/derivation.md'],'route_blocked':False})
    scheduler.finish_call(project,'r1',accepted=True,checkpoint=case.checkpoint('r1'),pending_wrapper=True)
    return 0
def hook(stage):
    if stage=='BEFORE_DISCOVERY': os._exit(77)
with mock.patch.object(configuration,'ROOT',root),mock.patch.object(runner,'HERE',root),mock.patch.object(runner_core,'ROOT',root),mock.patch.object(runner,'run_child',side_effect=child),mock.patch.object(research_acceptance,'fault_hook',side_effect=hook):
    policy=route_budget.policy_for(root,project)[0]
    path,data,epoch=route_budget.load_ledger(root,project,route_budget.state_read(project))
    runner.advance_one(project,policy,path,data,epoch,['fake'])
'''
        result=subprocess.run([sys.executable,'-B','-c',driver,str(source),str(self.root)],
            cwd=source,capture_output=True,text=True,timeout=45)
        self.assertEqual(result.returncode,77,result.stdout+result.stderr)
        self.assertEqual(ledger(self.project)['attempts'][0]['calls'][0]['status'],'PENDING_WRAPPER')
        with mock.patch.object(runner,'run_child',side_effect=AssertionError('No model retry')), \
             mock.patch.object(runner_core,'git_checkpoint',return_value='TEST'):
            self.assertEqual(runner.main(['--project',str(self.project)]),0)
        attempt=ledger(self.project)['attempts'][0]
        self.assertEqual(len(attempt['calls']),1)
        self.assertEqual(attempt['calls'][0]['status'],'ACCEPTED')
        self.assertEqual(attempt['checkpoint']['run_id'],'r1')
        self.assertEqual(attempt['stagnation'],1)
        self.assertEqual((self.root/'research-dispatch-count.txt').read_text(),'1')
        self.assertEqual(len(list((self.root/'state/discovery/checkpoints').rglob('r1.json'))),1)
        scheduler.finalize_wrapper(self.project,True,'r1',expected_attempt_id=attempt['id'])
        self.assertEqual(ledger(self.project)['attempts'][0],attempt)


if __name__ == '__main__': unittest.main()
