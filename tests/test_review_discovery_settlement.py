"""F03: owned discovery settlement never repeats a possibly completed check."""
import copy
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

import configuration
from engine import discovery_scheduler as scheduler, verification_engine
from engine.common import ledger, ledger_path, save_ledger
import test_discovery as fixtures


CHILD = r'''
import os, sys
from pathlib import Path
import configuration
from engine import discovery_scheduler as s, verification_engine as v
root, project, stage = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
configuration.ROOT = root
counter = root / 'offline-check-count.txt'
def checks(*args):
    with counter.open('a', encoding='utf8') as out:
        out.write('one\n'); out.flush(); os.fsync(out.fileno())
    if stage == 'unknown': os._exit(78)
    if stage == 'project-ready':
        from engine import claim_graph
        data = claim_graph.load(project)
        data['events'].append({'type': 'OFFLINE_CHECK_SENTINEL', 'run_id': 'r1'})
        claim_graph.save(project, data)
    return []
v.process_candidates = checks
original_save = s.save_ledger
def save(project, data):
    if stage in {'ready', 'project-ready'} and any(c['status'] == 'ACCEPTED' for a in data['attempts'] for c in a['calls']):
        os._exit(77)
    return original_save(project, data)
s.save_ledger = save
original_atomic = configuration.atomic_json
def atomic(path, data):
    original_atomic(path, data)
    if stage == 'receipt' and isinstance(data, dict) and data.get('phase') == 'SETTLEMENT_READY':
        os._exit(79)
configuration.atomic_json = atomic
s.finish_call(project, 'r1', accepted=True)
raise RuntimeError('The intended kill point was not reached')
'''


class ReviewDiscoverySettlementTests(unittest.TestCase):
    setUp = fixtures.DiscoveryTests.setUp
    tearDown = fixtures.DiscoveryTests.tearDown
    put = fixtures.DiscoveryTests.put
    checkpoint = fixtures.DiscoveryTests.checkpoint

    def pending(self):
        scheduler.start(self.project, 'P-1')
        scheduler.begin_call(self.project, 'r1')
        checkpoint = self.checkpoint('r1')
        scheduler.finish_call(self.project, 'r1', accepted=True, checkpoint=checkpoint, pending_wrapper=True)
        return checkpoint

    def call(self):
        return ledger(self.project)['attempts'][0]['calls'][0]

    def kill(self, stage, expected, *, prepare=True):
        if prepare: self.pending()
        result = subprocess.run([sys.executable, '-B', '-c', CHILD, str(self.root), str(self.project), stage],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)

    def test_every_unfinished_phase_stops_a_new_call_and_preserves_reservation(self):
        self.pending()
        base = ledger(self.project)
        for phase in ('RESERVED', 'PENDING_WRAPPER', 'SETTLING', 'SETTLEMENT_READY'):
            with self.subTest(phase=phase):
                data = copy.deepcopy(base)
                data['attempts'][0]['calls'][0]['status'] = phase
                save_ledger(self.project, data)
                before = ledger_path(self.project).read_bytes()
                with self.assertRaisesRegex(ValueError, 'DISCOVERY_.*|UNKNOWN_LOCAL_CHECK_OUTCOME'):
                    scheduler.begin_call(self.project, 'r2')
                self.assertEqual(before, ledger_path(self.project).read_bytes())

    def test_terminal_call_cannot_be_downgraded_by_native_pending_wrapper(self):
        checkpoint = self.pending()
        scheduler.finish_call(self.project, 'r1', accepted=False)
        before = ledger_path(self.project).read_bytes()
        scheduler.finish_call(self.project, 'r1', accepted=True, checkpoint=checkpoint, pending_wrapper=True)
        self.assertEqual(before, ledger_path(self.project).read_bytes())
        self.assertEqual(self.call()['status'], 'FAILED')

    def test_finalization_is_once_per_original_run_not_active_attempt(self):
        self.pending()
        scheduler.close(self.project, 'Close the synthetic pending attempt for recovery testing')
        with mock.patch.object(verification_engine, 'process_candidates', return_value=[]) as checks:
            scheduler.finalize_wrapper(self.project, True, 'r1')
            scheduler.finalize_wrapper(self.project, True, 'r1')
        self.assertEqual(checks.call_count, 1)
        data = ledger(self.project)
        self.assertIsNone(data['active_attempt'])
        self.assertEqual(data['attempts'][0]['status'], 'CLOSED')
        self.assertEqual(data['attempts'][0]['stagnation'], 1)
        self.assertEqual(self.call()['status'], 'ACCEPTED')

    def test_real_exit_after_check_before_attempt_save_recovers_without_rechecking(self):
        self.kill('ready', 77)
        self.assertEqual(self.call()['status'], 'SETTLEMENT_READY')
        with mock.patch.object(verification_engine, 'process_candidates', side_effect=AssertionError('Must not repeat checks')) as checks:
            scheduler.finalize_wrapper(self.project, True, 'r1')
            before = ledger_path(self.project).read_bytes()
            scheduler.finalize_wrapper(self.project, True, 'r1')
        checks.assert_not_called()
        self.assertEqual(before, ledger_path(self.project).read_bytes())
        self.assertEqual(self.call()['status'], 'ACCEPTED')
        self.assertEqual(ledger(self.project)['attempts'][0]['stagnation'], 1)
        self.assertEqual((self.root / 'offline-check-count.txt').read_text().splitlines(), ['one'])
        self.assertEqual(len(list((self.root / 'state/discovery/checkpoints').rglob('r1.json'))), 1)

    def test_real_exit_after_receipt_before_ready_marker_recovers_without_rechecking(self):
        self.kill('receipt', 79)
        self.assertEqual(self.call()['status'], 'SETTLING')
        with mock.patch.object(verification_engine, 'process_candidates', side_effect=AssertionError('Must not repeat checks')) as checks:
            scheduler.finalize_wrapper(self.project, True, 'r1')
        checks.assert_not_called()
        self.assertEqual(self.call()['status'], 'ACCEPTED')
        self.assertEqual((self.root / 'offline-check-count.txt').read_text().splitlines(), ['one'])

    def test_completed_check_manifest_proves_canonical_edit_and_rejects_third_hash(self):
        from research_acceptance import manifest
        self.pending()
        before = manifest(self.project)
        self.kill('project-ready', 77, prepare=False)
        receipt = scheduler.settlement_observation(self.project, 'attempt-0001', 'r1')
        self.assertEqual(receipt['project_before_checks'], before)
        self.assertEqual(receipt['project_after_checks'], manifest(self.project))
        self.assertNotEqual(receipt['project_before_checks'], receipt['project_after_checks'])
        self.assertIn('research/discovery/CLAIM_GRAPH.json', receipt['project_after_checks'])
        self.put('proofs/derivation.md', 'A third external edit must not be accepted as the check output')
        with mock.patch.object(verification_engine, 'process_candidates') as checks:
            with self.assertRaisesRegex(ValueError, 'DISCOVERY_SETTLEMENT_PROJECT_CHANGED'):
                scheduler.finalize_wrapper(self.project, True, 'r1', expected_attempt_id='attempt-0001')
        checks.assert_not_called()
        self.assertEqual(self.call()['status'], 'SETTLEMENT_READY')

    def test_real_exit_during_checks_retains_unknown_and_never_retries(self):
        self.kill('unknown', 78)
        self.assertEqual(self.call()['status'], 'SETTLING')
        before = ledger_path(self.project).read_bytes()
        with mock.patch.object(verification_engine, 'process_candidates') as checks:
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, 'UNKNOWN_LOCAL_CHECK_OUTCOME'):
                    scheduler.finalize_wrapper(self.project, True, 'r1')
                with self.assertRaises(ValueError): scheduler.check(self.project)
        checks.assert_not_called()
        self.assertEqual(before, ledger_path(self.project).read_bytes())
        self.assertEqual((self.root / 'offline-check-count.txt').read_text().splitlines(), ['one'])

    def test_changed_ready_receipt_or_attempt_stops_without_repeating_checks(self):
        self.kill('ready', 77)
        receipt = next((self.root / 'state/discovery/settlements').rglob('r1.json'))
        raw = receipt.read_bytes()
        data = configuration.load_json(receipt)
        data['after_attempt']['stagnation'] += 20
        configuration.atomic_json(receipt, data)
        with mock.patch.object(verification_engine, 'process_candidates') as checks:
            with self.assertRaisesRegex(ValueError, 'DISCOVERY_SETTLEMENT_'):
                scheduler.finalize_wrapper(self.project, True, 'r1')
        checks.assert_not_called()
        receipt.write_bytes(raw)
        current = ledger(self.project)
        current['attempts'][0]['budget'] += 20
        save_ledger(self.project, current)
        with self.assertRaisesRegex(ValueError, 'DISCOVERY_SETTLEMENT_CONFLICT'):
            scheduler.finalize_wrapper(self.project, True, 'r1')

    def test_pending_checkpoint_cannot_change_between_native_receipts(self):
        checkpoint = self.pending()
        checkpoint['next_action'] = 'A different unowned checkpoint must not overwrite the reserved one'
        before = ledger_path(self.project).read_bytes()
        with self.assertRaisesRegex(ValueError, 'DISCOVERY_PENDING_CHECKPOINT_CHANGED'):
            scheduler.finish_call(self.project, 'r1', accepted=True, checkpoint=checkpoint, pending_wrapper=True)
        self.assertEqual(before, ledger_path(self.project).read_bytes())

    def test_old_ledger_backup_cannot_erase_an_unknown_check_dispatch(self):
        self.pending()
        backup = ledger_path(self.project).read_bytes()
        with mock.patch.object(verification_engine, 'process_candidates', side_effect=RuntimeError('Unknown partial check')):
            with self.assertRaises(RuntimeError): scheduler.finalize_wrapper(self.project, True, 'r1')
        ledger_path(self.project).write_bytes(backup)
        with mock.patch.object(verification_engine, 'process_candidates') as checks:
            with self.assertRaisesRegex(ValueError, 'UNKNOWN_LOCAL_CHECK_OUTCOME'):
                scheduler.finalize_wrapper(self.project, True, 'r1')
        checks.assert_not_called()
        self.assertEqual(backup, ledger_path(self.project).read_bytes())

    def test_frozen_owner_cannot_disappear_or_change_during_wrapper_recovery(self):
        self.pending()
        original = ledger(self.project)
        ledger_path(self.project).unlink()
        with self.assertRaisesRegex(ValueError, 'DISCOVERY_OWNER_MISSING'):
            scheduler.finalize_wrapper(self.project, True, 'r1', expected_attempt_id='attempt-0001')
        self.assertFalse(ledger_path(self.project).exists())
        original['attempts'][0]['id'] = 'attempt-other'
        save_ledger(self.project, original)
        with self.assertRaisesRegex(ValueError, 'DISCOVERY_OWNER_CHANGED'):
            scheduler.finalize_wrapper(self.project, True, 'r1', expected_attempt_id='attempt-0001')

    def test_terminal_call_cannot_replace_the_trusted_completion_afterimage(self):
        self.pending()
        scheduler.finalize_wrapper(self.project,True,'r1',expected_attempt_id='attempt-0001')
        changed=ledger(self.project)
        changed['attempts'][0]['calls'][0]['evaluation']['procedural_progress']=True
        save_ledger(self.project,changed)
        with self.assertRaisesRegex(ValueError,'DISCOVERY_TERMINAL_RECEIPT_CHANGED'):
            scheduler.finalize_wrapper(self.project,True,'r1',expected_attempt_id='attempt-0001')

    def test_terminal_label_without_trusted_ready_receipt_cannot_complete_wrapper(self):
        self.pending()
        scheduler.finalize_wrapper(self.project,True,'r1',expected_attempt_id='attempt-0001')
        scheduler._settlement_path(self.project,'attempt-0001','r1').unlink()
        with self.assertRaisesRegex(ValueError,'UNKNOWN_LOCAL_CHECK_OUTCOME'):
            scheduler.finalize_wrapper(self.project,True,'r1',expected_attempt_id='attempt-0001')


if __name__ == '__main__':
    unittest.main()
