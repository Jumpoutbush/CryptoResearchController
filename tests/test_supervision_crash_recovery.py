"""R02 addendum: local crash boundaries, no provider or guide executor."""
import copy
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest import mock

import configuration
import supervision
import supervision_calls as calls
import supervision_ledger as queue
import supervision_scheduler as scheduler
import test_supervision_triggers as fixture

ROOT = Path(__file__).resolve().parents[1]


class CrashRecoveryTests(unittest.TestCase):
    setUp = fixture.SupervisionTriggerTests.setUp
    put = fixture.SupervisionTriggerTests.put
    save_ledger = fixture.SupervisionTriggerTests.save_ledger
    files = fixture.SupervisionTriggerTests.files
    enable = fixture.SupervisionTriggerTests.enable
    rounds = fixture.SupervisionTriggerTests.rounds
    record = fixture.SupervisionTriggerTests.record

    def claim(self):
        self.enable(); event = self.record(3)['event_id']
        claim = scheduler.claim_event(self.root, self.project, event)
        self.assertTrue(claim['claimed'])
        return event, claim['claim_token']

    def dispatch(self, event, token):
        return calls.mark_dispatched(self.root, self.project, event, token,
            argv=['offline-fake', 'exec', '--sandbox', 'read-only'])

    def complete(self, event, token):
        return calls.save_completion(self.root, self.project, event, token, state='PROPOSED',
            elapsed_seconds=4, raw_output='{"action":"KEEP_GUIDE"}', log='Untrusted fake provider result.')

    def test_reservation_freezes_owner_input_generation_and_model_route(self):
        event, token = self.claim()
        saved = supervision._load(self.root, self.project)['event_reservations'][event]
        self.assertEqual(saved['call_generation'], 1)
        self.assertEqual(saved['owner_pid'], os.getpid())
        self.assertEqual(saved['owner_instance'], token)
        self.assertEqual(saved['input_snapshot_sha256'], queue.read_event(self.root, self.project, event)['snapshot']['input_snapshot_sha256'])
        policy = configuration.load_json(self.root / 'config/supervision_policy.json')
        policy['model'] = 'different-operator-setting'; configuration.atomic_json(self.root / 'config/supervision_policy.json', policy)
        self.assertEqual(self.dispatch(event, token)['model_route'], saved['model_route'])

    def unknown_after_process_exit(self, received):
        event, token = self.claim()
        ready, provider = self.root / 'dispatch-ready.json', self.root / 'fake-provider-received'
        worker = self.root / 'dispatch-worker.py'
        worker.write_text('import sys,json\nfrom pathlib import Path\n'
            + 'sys.path.insert(0,' + repr(str(ROOT)) + ')\nimport configuration,supervision_calls as c\n'
            + 'configuration.ROOT=Path(sys.argv[1])\n'
            + 'r=c.mark_dispatched(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3],sys.argv[4],argv=["offline-fake"])\n'
            + 'if sys.argv[7]=="yes" and r["dispatch_allowed"]: Path(sys.argv[6]).write_text("received")\n'
            + 'configuration.atomic_json(Path(sys.argv[5]),r)\nsys.stdin.read()\n', encoding='utf8')
        process = subprocess.Popen([sys.executable, '-B', str(worker), str(self.root), str(self.project), event, token,
            str(ready), str(provider), 'yes' if received else 'no'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: (process.kill(), process.communicate(timeout=10)) if process.poll() is None else process.communicate(timeout=10))
        deadline = time.monotonic() + 15
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline: time.sleep(.01)
        self.assertTrue(ready.exists(), 'Fake dispatch child did not reach the fence')
        self.assertTrue(json.loads(ready.read_text())['dispatch_allowed'])
        process.terminate(); process.communicate(timeout=10)
        self.assertEqual(provider.exists(), received)
        item = scheduler.pending(self.root, self.project)['events'][0]
        self.assertEqual(item['state'], 'RUNNING')  # R01 state unchanged.
        self.assertEqual(item['call_phase'], 'UNKNOWN_EXTERNAL_OUTCOME')
        self.assertTrue(item['operator_audit_required'])
        self.assertFalse(self.dispatch(event, token)['dispatch_allowed'])
        self.assertEqual(scheduler.claim_event(self.root, self.project, event)['reason'], 'UNKNOWN_EXTERNAL_OUTCOME')
        with self.assertRaisesRegex(ValueError, 'UNKNOWN_EXTERNAL_OUTCOME'):
            calls.recover_completion(self.root, self.project, event, token)
        self.assertEqual(supervision._load(self.root, self.project)['attempts_used'], 1)

    def test_dispatched_child_dies_before_fake_provider_received_request(self): self.unknown_after_process_exit(False)
    def test_dispatched_child_dies_after_fake_provider_received_request(self): self.unknown_after_process_exit(True)

    def test_completion_receipt_before_parent_state_is_replayed_once_without_guide_writes(self):
        event, token = self.claim(); self.dispatch(event, token)
        project_before = {p.relative_to(self.project).as_posix(): p.read_bytes() for p in self.project.rglob('*') if p.is_file()}
        save = supervision._save
        def fail_settlement(controller, project, data):
            if data['event_reservations'][event]['state'] != 'RUNNING': raise OSError('After durable external receipt, before cost settlement')
            return save(controller, project, data)
        with mock.patch.object(supervision, '_save', side_effect=fail_settlement):
            with self.assertRaises(OSError): self.complete(event, token)
        self.assertEqual(supervision._load(self.root, self.project)['seconds_used'], 600)
        self.assertEqual(scheduler.pending(self.root, self.project)['events'][0]['call_phase'], 'CALL_COMPLETED')
        self.assertEqual(scheduler.claim_event(self.root, self.project, event)['reason'], 'COMPLETION_REPLAY_REQUIRED')
        for _ in range(3): calls.recover_completion(self.root, self.project, event, token)
        saved = supervision._load(self.root, self.project)
        self.assertEqual((saved['attempts_used'], saved['seconds_used']), (1, 4))
        self.assertEqual(saved['event_reservations'][event]['state'], 'PROPOSED')
        self.assertFalse(self.dispatch(event, token)['dispatch_allowed'])
        self.assertEqual(project_before, {p.relative_to(self.project).as_posix(): p.read_bytes() for p in self.project.rglob('*') if p.is_file()})
        self.assertFalse((self.project / 'supervision/ACTIVE_GUIDE.md').exists())

    def test_completion_artifact_before_journal_ack_recovers_without_second_call(self):
        event, token = self.claim(); self.dispatch(event, token)
        append = queue.append
        def fail_ack(controller, project, kind, key, **details):
            if kind == 'CALL_COMPLETED': raise OSError('After receipt, before operation ack')
            return append(controller, project, kind, key, **details)
        with mock.patch.object(queue, 'append', side_effect=fail_ack):
            with self.assertRaises(OSError): self.complete(event, token)
        calls.recover_completion(self.root, self.project, event, token)
        self.assertEqual(supervision._load(self.root, self.project)['attempts_used'], 1)
        self.assertEqual(supervision._load(self.root, self.project)['seconds_used'], 4)

    def test_completion_corruption_or_loss_blocks_replay_and_redispatch(self):
        event, token = self.claim(); self.dispatch(event, token); self.complete(event, token)
        path = queue._event_path(self.root, self.project, event, 'completions')
        original = path.read_bytes(); path.write_text('{broken', encoding='utf8')
        with self.assertRaises(ValueError): calls.recover_completion(self.root, self.project, event, token)
        path.unlink()
        with self.assertRaises(ValueError): self.dispatch(event, token)
        path.write_bytes(original)
        calls.recover_completion(self.root, self.project, event, token)
        self.assertEqual(supervision._load(self.root, self.project)['seconds_used'], 4)

    def test_orphan_completion_must_keep_bounded_untrusted_raw_output_and_log(self):
        event, token = self.claim(); self.dispatch(event, token)
        append = queue.append
        def fail_ack(controller, project, kind, key, **details):
            if kind == 'CALL_COMPLETED': raise OSError('Persisted receipt not yet acknowledged')
            return append(controller, project, kind, key, **details)
        with mock.patch.object(queue, 'append', side_effect=fail_ack):
            with self.assertRaises(OSError): self.complete(event, token)
        path = queue._event_path(self.root, self.project, event, 'completions')
        original = path.read_bytes()
        for mutate in (lambda p: p.pop('raw_output'), lambda p: p.pop('log'),
                       lambda p: p.update(trust='VERIFIED'), lambda p: p.update(schema_version=999),
                       lambda p: p.update(elapsed_seconds=True), lambda p: p.update(state='APPLIED'),
                       lambda p: p.update(raw_output='X' * 300000)):
            data = json.loads(original); data.pop('payload_sha256'); mutate(data)
            data['payload_sha256'] = queue.canonical_hash(data)
            path.write_text(json.dumps(data), encoding='utf8')
            with self.assertRaises(ValueError): calls.recover_completion(self.root, self.project, event, token)
            self.assertEqual(supervision._load(self.root, self.project)['seconds_used'], 600)
        path.write_bytes(original)
        calls.recover_completion(self.root, self.project, event, token)
        self.assertEqual(supervision._load(self.root, self.project)['seconds_used'], 4)

    def test_frozen_package_loss_logs_only_path_hash_and_preserves_existing_reservation(self):
        event, token = self.claim()
        path = queue._event_path(self.root, self.project, event)
        original = path.read_bytes(); path.unlink()
        with self.assertRaises(ValueError): scheduler.claim_event(self.root, self.project, event)
        blocked = queue.operations(self.root, self.project)[-1]
        self.assertEqual(blocked['type'], 'BLOCKED_MISSING_FROZEN_INPUT')
        self.assertIn(event + '.json', blocked['details']['path'])
        self.assertEqual(len(blocked['details']['expected_sha256']), 64)
        self.assertNotIn('content', blocked['details'])
        self.assertEqual(supervision._load(self.root, self.project)['seconds_used'], 600)
        path.write_bytes(original)
        self.assertFalse(scheduler.claim_event(self.root, self.project, event)['claimed'])

    def test_frozen_goal_body_loss_never_rebuilds_from_a_new_live_goal(self):
        self.enable(); event = self.record(3)['event_id']
        path = queue._event_path(self.root, self.project, event)
        data = json.loads(path.read_text(encoding='utf8'))
        expected = data['event']['focus']['goal_sha256']
        data['snapshot']['sources'] = [s for s in data['snapshot']['sources'] if s['path'] != 'GOAL.md']
        path.write_text(json.dumps(data), encoding='utf8')
        self.put('GOAL.md', 'A later unrelated goal must not replace the frozen original.')
        with self.assertRaises(ValueError): scheduler.claim_event(self.root, self.project, event)
        blocked = queue.operations(self.root, self.project)[-1]
        self.assertEqual(blocked['details']['path'], 'GOAL.md')
        self.assertEqual(blocked['details']['expected_sha256'], expected)
        self.assertIsNone(supervision._load(self.root, self.project))

    def test_required_source_truncation_blocks_cost_reservation_without_changing_R01(self):
        self.enable(); self.state['notes'] = 'Large state content.\n' * 16000
        event = self.record(3)['event_id']
        with self.assertRaises(ValueError): scheduler.claim_event(self.root, self.project, event)
        self.assertIsNone(supervision._load(self.root, self.project))

    def test_dispatched_call_cannot_refund_without_original_completion_receipt(self):
        event, token = self.claim(); self.dispatch(event, token)
        with self.assertRaisesRegex(ValueError, 'UNKNOWN_EXTERNAL_OUTCOME'):
            scheduler.finish_claim(self.root, self.project, event, token, state='FAILED', elapsed_seconds=0)
        self.assertEqual(supervision._load(self.root, self.project)['seconds_used'], 600)

    def test_ledger_rollback_before_dispatch_cannot_override_durable_dispatch_witness(self):
        event, token = self.claim()
        before = copy.deepcopy(supervision._load(self.root, self.project))
        self.assertTrue(self.dispatch(event, token)['dispatch_allowed'])
        supervision._save(self.root, self.project, before)
        with self.assertRaises(ValueError): self.dispatch(event, token)
        self.assertEqual(len([op for op in queue.operations(self.root, self.project) if op['type'] == 'CALL_DISPATCHED']), 1)

    def test_two_native_processes_grant_only_one_dispatch_permission(self):
        event, token = self.claim()
        worker = self.root / 'dispatch-once.py'
        worker.write_text('import sys,json\nfrom pathlib import Path\n'
            + 'sys.path.insert(0,' + repr(str(ROOT)) + ')\nimport configuration,supervision_calls as c\n'
            + 'configuration.ROOT=Path(sys.argv[1])\ntry:\n'
            + ' r=c.mark_dispatched(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3],sys.argv[4],argv=["offline-fake"])\n'
            + 'except RuntimeError:\n r={"dispatch_allowed":False,"reason":"LOCKED"}\nprint(json.dumps(r))\n', encoding='utf8')
        cmd = [sys.executable, '-B', str(worker), str(self.root), str(self.project), event, token]
        processes = [subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        replies = [p.communicate(timeout=30) for p in processes]
        for p, reply in zip(processes, replies): self.assertEqual(p.returncode, 0, reply)
        self.assertEqual(sum(json.loads(out)['dispatch_allowed'] for out, err in replies), 1)
        self.assertEqual(supervision._load(self.root, self.project)['attempts_used'], 1)

    def test_dispatch_ack_failure_never_grants_permission_again_or_logs_cli_secrets(self):
        event, token = self.claim(); append = queue.append
        def fail_ack(controller, project, kind, key, **details):
            if kind == 'CALL_DISPATCHED': raise OSError('After dispatch fence, before ack')
            return append(controller, project, kind, key, **details)
        with mock.patch.object(queue, 'append', side_effect=fail_ack):
            with self.assertRaises(OSError):
                calls.mark_dispatched(self.root, self.project, event, token, argv=['offline-fake', 'token=TEST-DO-NOT-PERSIST'])
        self.assertFalse(self.dispatch(event, token)['dispatch_allowed'])
        for p in (self.root / 'state/supervision').rglob('*.json*'):
            self.assertNotIn('TEST-DO-NOT-PERSIST', p.read_text(encoding='utf8'))

    def test_disabling_either_existing_switch_blocks_already_claimed_dispatch(self):
        event, token = self.claim()
        for filename in ('supervision_defaults.json', 'supervision_policy.json'):
            path = self.root / 'config' / filename
            policy = configuration.load_json(path); policy['enabled'] = False
            configuration.atomic_json(path, policy)
            self.assertFalse(self.dispatch(event, token)['dispatch_allowed'])
            policy['enabled'] = True; configuration.atomic_json(path, policy)
        self.assertEqual(supervision._load(self.root, self.project)['attempts_used'], 1)
        self.assertNotIn('dispatch', supervision._load(self.root, self.project)['event_reservations'][event])

    def test_required_selected_idea_truncation_records_exact_frozen_path_and_hash(self):
        from research_focus import make_focus
        self.enable()
        path = self.put('ideas/revisions/idea-0001-v1.md', 'Pinned original idea.\n' * 10000)
        digest = supervision._hash(path.read_bytes())
        self.put('ideas/INDEX.json', {'ideas': [{'id': 'IDEA-0001', 'revisions': [
            {'version': 1, 'file': 'ideas/revisions/idea-0001-v1.md', 'sha256': digest}]}]})
        self.state['selected_idea'] = {'id': 'IDEA-0001', 'version': 1}
        self.ledger['epochs'][0]['focus'] = make_focus(self.project, self.state)
        event = self.record(3)['event_id']
        with self.assertRaises(ValueError): scheduler.claim_event(self.root, self.project, event)
        blocked = queue.operations(self.root, self.project)[-1]
        self.assertEqual(blocked['details']['path'], 'ideas/revisions/idea-0001-v1.md')
        self.assertEqual(blocked['details']['expected_sha256'], digest)
        self.assertIsNone(supervision._load(self.root, self.project))

    @unittest.skipUnless(os.name == 'nt', 'Native Windows replacement sharing rules')
    def test_native_windows_open_ledger_prevents_replace_then_recovers_single_reservation(self):
        self.enable(); event = self.record(3)['event_id']
        supervision.configure(self.root, self.project, {'enabled': True})
        path = supervision._home(self.root, self.project) / 'ledger.json'
        original = path.read_bytes()
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
        kernel.CreateFileW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.CreateFileW(str(path), 0x80000000, 3, None, 3, 0x80, None)  # No FILE_SHARE_DELETE.
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            with self.assertRaises(PermissionError): scheduler.claim_event(self.root, self.project, event)
            self.assertEqual(path.read_bytes(), original)
        finally: kernel.CloseHandle(handle)
        self.assertTrue(scheduler.claim_event(self.root, self.project, event)['claimed'])
        self.assertEqual(supervision._load(self.root, self.project)['attempts_used'], 1)


if __name__ == '__main__': unittest.main()
