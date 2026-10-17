"""N01/T01-T03: a missing or stale call ledger never forgets consumption."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

import configuration
from engine import discovery_scheduler as scheduler, verification_engine
from engine import discovery_authority as authority
from engine.common import ledger, ledger_path, save_ledger
import test_discovery as fixture


class DiscoveryAuthorityTests(unittest.TestCase):
    setUp=fixture.DiscoveryTests.setUp
    tearDown=fixture.DiscoveryTests.tearDown
    put=fixture.DiscoveryTests.put

    def start(self):
        configuration.atomic_json(self.root/'config/projects/example.json',{'discovery_policy':{'initial_round_budget':1}})
        scheduler.start(self.project,'P-1')
        return ledger_path(self.project).read_bytes()

    def test_t01_call_before_backup_cannot_forget_failed_consumption(self):
        backup=self.start(); scheduler.begin_call(self.project,'r1'); scheduler.finish_call(self.project,'r1',accepted=False)
        ledger_path(self.project).write_bytes(backup)
        with self.assertRaises(ValueError): scheduler.begin_call(self.project,'r2')

    def test_t02_missing_or_zero_ledger_does_not_reset_attempt_history(self):
        self.start(); path=ledger_path(self.project); original=path.read_bytes()
        for content in (None,b'{}',b'{"schema_version":1,"active_attempt":null,"attempts":[]}'):
            with self.subTest(content=content):
                if content is None: path.unlink(missing_ok=True)
                else: path.write_bytes(content)
                with self.assertRaises(ValueError): scheduler.start(self.project,'P-1')
                if path.exists(): self.assertEqual(path.read_bytes(),content)
                path.write_bytes(original)

    def test_t03_forgotten_unknown_check_witness_still_blocks_another_run(self):
        backup=self.start(); scheduler.begin_call(self.project,'r1')
        with mock.patch.object(verification_engine,'process_candidates',side_effect=OSError('unknown external check')):
            with self.assertRaises(OSError): scheduler.finish_call(self.project,'r1',accepted=True)
        ledger_path(self.project).write_bytes(backup)
        with self.assertRaises(ValueError): scheduler.begin_call(self.project,'r2')

    def test_completed_settlement_requires_original_started_pair_and_binding(self):
        self.start(); scheduler.begin_call(self.project,'r1'); scheduler.finish_call(self.project,'r1',accepted=False)
        started=self.root/'state/discovery/settlements/example/attempt-0001/r1.started.json'
        original=started.read_bytes(); started.unlink()
        with self.assertRaisesRegex(ValueError,'DISCOVERY_SETTLEMENT_|WITNESS_INVALID'): ledger(self.project)
        started.write_bytes(original); changed=json.loads(original); changed['attempt_sha256']='0'*64
        configuration.atomic_json(started,changed)
        with self.assertRaisesRegex(ValueError,'DISCOVERY_SETTLEMENT_|WITNESS_INVALID'): ledger(self.project)

    def project_files(self):
        return {p.relative_to(self.project).as_posix():p.read_bytes() for p in self.project.rglob('*') if p.is_file()}

    def forget_registration(self):
        authority.registry_path(self.project).unlink(); authority.registration_path(self.project).unlink()

    def test_reads_and_status_never_enroll_a_new_or_complete_legacy_ledger(self):
        before=self.project_files(); initial=sorted(str(p) for p in self.root.rglob('*'))
        self.assertEqual(ledger(self.project)['attempts'],[])
        self.assertEqual(authority.status(self.project)['status'],'NEW_UNENROLLED')
        self.assertEqual(initial,sorted(str(p) for p in self.root.rglob('*')))
        self.start(); original=ledger_path(self.project).read_bytes(); self.forget_registration()
        self.assertEqual(authority.status(self.project)['status'],'LEGACY_ENROLLMENT_REQUIRED')
        with self.assertRaisesRegex(ValueError,'ENROLLMENT_REQUIRED'): ledger(self.project)
        self.assertFalse(authority.registry_path(self.project).exists()); self.assertEqual(original,ledger_path(self.project).read_bytes())

    def test_explicit_legacy_enrollment_preserves_exact_consumption_and_bytes(self):
        self.start(); scheduler.begin_call(self.project,'r1'); scheduler.finish_call(self.project,'r1',accepted=False)
        original=ledger_path(self.project).read_bytes(); before=self.project_files(); self.forget_registration()
        with self.assertRaisesRegex(ValueError,'CAS'):
            authority.enroll(self.project,'Operator retains all legacy calls',expected_ledger_sha256='0'*64)
        digest=authority.status(self.project)['actual_ledger_sha256']
        result=authority.enroll(self.project,'Operator confirms full historical consumption',expected_ledger_sha256=digest)
        self.assertEqual(result['status'],'COMMITTED'); self.assertEqual(result['calls'],1)
        self.assertEqual(original,ledger_path(self.project).read_bytes()); self.assertEqual(before,self.project_files())
        with self.assertRaises(ValueError): scheduler.begin_call(self.project,'r2')
        with self.assertRaises(ValueError): authority.enroll(self.project,'Cannot reenroll existing authority',expected_ledger_sha256=digest)

    def test_legacy_witness_scan_rejects_missing_empty_and_pre_call_images(self):
        backup=self.start(); scheduler.begin_call(self.project,'r1'); scheduler.finish_call(self.project,'r1',accepted=False)
        self.forget_registration(); path=ledger_path(self.project)
        for content in (None,b'{"schema_version":1,"active_attempt":null,"attempts":[]}',backup):
            with self.subTest(content=content):
                if content is None: path.unlink(missing_ok=True)
                else: path.write_bytes(content)
                with self.assertRaisesRegex(ValueError,'FORGOTTEN'): ledger(self.project)
                self.assertEqual(authority.status(self.project)['status'],'FAILED')
                if content is not None:
                    with self.assertRaisesRegex(ValueError,'FORGOTTEN'):
                        authority.enroll(self.project,'Legacy cannot forget existing run witnesses',expected_ledger_sha256=authority._file_sha(path))

    def test_both_sides_of_registration_are_required(self):
        self.start(); original=ledger_path(self.project).read_bytes()
        for location in (authority.registry_path(self.project),authority.registration_path(self.project)):
            saved=location.read_bytes(); location.unlink()
            with self.assertRaisesRegex(ValueError,'WITNESS_MISSING'): ledger(self.project)
            with self.assertRaises(ValueError): scheduler.start(self.project,'P-1')
            self.assertEqual(original,ledger_path(self.project).read_bytes()); location.write_bytes(saved)

    def test_stale_in_memory_image_cannot_delete_calls_or_old_attempts(self):
        self.start(); before=copy.deepcopy(ledger(self.project)); scheduler.begin_call(self.project,'r1')
        current=ledger_path(self.project).read_bytes()
        with self.assertRaisesRegex(ValueError,'REGRESSION'): save_ledger(self.project,before)
        self.assertEqual(current,ledger_path(self.project).read_bytes())
        before['attempts']=[]; before['active_attempt']=None
        with self.assertRaisesRegex(ValueError,'REGRESSION'): save_ledger(self.project,before)

    def test_budget_may_be_tightened_while_consumed_calls_remain_unavailable(self):
        scheduler.start(self.project,'P-1'); scheduler.begin_call(self.project,'r1'); scheduler.finish_call(self.project,'r1',accepted=False)
        value=ledger(self.project); original=copy.deepcopy(value['attempts'][0]['calls'])
        value['attempts'][0]['budget']=1; save_ledger(self.project,value)
        self.assertEqual(ledger(self.project)['attempts'][0]['calls'],original)
        with self.assertRaisesRegex(ValueError,'BUDGET_EXHAUSTED'): scheduler.begin_call(self.project,'r2')

    def pending_call(self,stage):
        self.start(); original=configuration.atomic_json; location=ledger_path(self.project)
        def interrupt(path,value):
            if stage=='before' and path==location: raise OSError('before original call ledger replace')
            if stage=='after' and path==authority.registry_path(self.project) and value.get('pending') is None:
                raise OSError('after original call ledger replace')
            return original(path,value)
        with mock.patch('configuration.atomic_json',side_effect=interrupt):
            with self.assertRaises(OSError): scheduler.begin_call(self.project,'r1')
        return authority.status(self.project)['pending_afterimage_sha256']

    def test_pending_before_ledger_recovers_original_reservation_once_without_model(self):
        target=self.pending_call('before'); before=self.project_files()
        with self.assertRaisesRegex(ValueError,'RECOVERY_REQUIRED'): ledger(self.project)
        with mock.patch.object(verification_engine,'process_candidates',side_effect=AssertionError('No repeated checks')) as checks:
            result=authority.recover(self.project,'Finish exact original call afterimage',expected_afterimage_sha256=target)
            again=authority.recover(self.project,'Idempotent original authority recovery',expected_afterimage_sha256=target)
        checks.assert_not_called(); self.assertEqual(result['status'],'RECOVERED_LOCAL_AFTERIMAGE'); self.assertEqual(again['status'],'ALREADY_COMMITTED')
        self.assertEqual(len(ledger(self.project)['attempts'][0]['calls']),1); self.assertEqual(before,self.project_files())
        with self.assertRaisesRegex(ValueError,'SETTLEMENT_PENDING'): scheduler.begin_call(self.project,'r2')

    def test_pending_after_ledger_requires_explicit_same_afterimage_and_keeps_unknown(self):
        target=self.pending_call('after'); raw=ledger_path(self.project).read_bytes()
        with self.assertRaisesRegex(ValueError,'RECOVERY_REQUIRED'): scheduler.check(self.project)
        with self.assertRaisesRegex(ValueError,'CAS'):
            authority.recover(self.project,'Refuse another pending afterimage',expected_afterimage_sha256='0'*64)
        authority.recover(self.project,'Recover already written original afterimage',expected_afterimage_sha256=target)
        self.assertEqual(raw,ledger_path(self.project).read_bytes())
        with self.assertRaisesRegex(ValueError,'SETTLEMENT_PENDING'): scheduler.begin_call(self.project,'r2')

    def test_pending_third_ledger_version_is_never_overwritten(self):
        target=self.pending_call('before'); ledger_path(self.project).write_bytes(b'{}'); raw=ledger_path(self.project).read_bytes()
        with self.assertRaisesRegex(ValueError,'CONFLICT'):
            authority.recover(self.project,'Do not overwrite third party original ledger',expected_afterimage_sha256=target)
        self.assertEqual(raw,ledger_path(self.project).read_bytes())

    def test_first_attempt_pending_authority_must_complete_before_prepared_state_write(self):
        plan=scheduler.prepare_start(self.project,'P-1'); original=configuration.atomic_json; before=self.project_files()
        def interrupt(path,value):
            if path==authority.registry_path(self.project) and value.get('pending') is None: raise OSError('ledger saved but authority pending')
            return original(path,value)
        with mock.patch('configuration.atomic_json',side_effect=interrupt):
            with self.assertRaises(OSError): scheduler.commit_prepared(self.project,plan)
        with self.assertRaisesRegex(ValueError,'RECOVERY_REQUIRED'): scheduler.commit_prepared(self.project,plan,allow_partial=True)
        self.assertEqual(before,self.project_files())
        target=authority.status(self.project)['pending_afterimage_sha256']
        authority.recover(self.project,'Complete exact original first attempt authority',expected_afterimage_sha256=target)
        scheduler.commit_prepared(self.project,plan,allow_partial=True)
        self.assertEqual(len(ledger(self.project)['attempts']),1)
        self.assertEqual(configuration.load_json(self.project/'research/STATE.json'),plan['after_state'])

    def test_hard_exit_after_ledger_before_high_water_commit_keeps_reserved_unknown(self):
        self.start(); code=r'''import os,sys
from pathlib import Path
import configuration
from engine import discovery_scheduler as s
root,project=Path(sys.argv[1]),Path(sys.argv[2]); configuration.ROOT=root
target=root/'state/discovery/example.json'; original=configuration.atomic_json
def write(path,value):
    original(path,value)
    if Path(path)==target: os._exit(76)
configuration.atomic_json=write
s.begin_call(project,'r1')
'''
        child=subprocess.run([sys.executable,'-B','-c',code,str(self.root),str(self.project)],
            cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=30)
        self.assertEqual(child.returncode,76,child.stdout+child.stderr)
        with self.assertRaisesRegex(ValueError,'RECOVERY_REQUIRED'): scheduler.check(self.project)
        target=authority.status(self.project)['pending_afterimage_sha256']
        authority.recover(self.project,'Complete hard exit frozen call ledger',expected_afterimage_sha256=target)
        with self.assertRaisesRegex(ValueError,'SETTLEMENT_PENDING'): scheduler.begin_call(self.project,'r2')
        self.assertEqual(len(ledger(self.project)['attempts'][0]['calls']),1)
