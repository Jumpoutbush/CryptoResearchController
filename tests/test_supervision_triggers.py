"""R02 offline queue, receipt priority and shared supervision cost invariants."""
from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest import mock

import configuration
import research
import route_budget
import supervision
import supervision_ledger as queue
import supervision_scheduler as scheduler
import test_supervision_contract as contract_fixture


ROOT = Path(__file__).resolve().parents[1]


class SupervisionTriggerTests(unittest.TestCase):
    def setUp(self):
        contract_fixture.SupervisionContractTests.setUp(self)
        self.state.update(priority_problem='The exact frozen obligation', next_task='Prove the unchanged quantified statement.')
        self.put('research/STATE.json', self.state)
    put = contract_fixture.SupervisionContractTests.put
    save_ledger = contract_fixture.SupervisionContractTests.save_ledger
    files = contract_fixture.SupervisionContractTests.files

    def enable(self):
        defaults = configuration.load_json(self.root / 'config/supervision_defaults.json')
        defaults['enabled'] = True
        configuration.atomic_json(self.root / 'config/supervision_defaults.json', defaults)
        policy = configuration.load_json(self.root / 'config/supervision_policy.json')
        policy['enabled'] = True
        configuration.atomic_json(self.root / 'config/supervision_policy.json', policy)

    def rounds(self, number, *, pending=False):
        epoch = self.ledger['epochs'][0]
        epoch.update(effective_rounds=number, counted_run_ids=[f'r{i}' for i in range(1, number + 1)],
                     last_processed_run=f'r{number}', review_pending=pending, review_reason='scheduled' if pending else None)
        self.ledger['events'] = [{'type': 'RESEARCH_ROUND', 'run_id': f'r{i}', 'route': 'MAIN',
            'effective_rounds': i, 'changed_evidence_paths': ['proofs/argument.md']} for i in range(1, number + 1)]
        self.state['last_run'] = f'r{number}'; self.put('research/STATE.json', self.state)
        for i in range(1, number + 1): self.put(f'reports/r{i}.md', f'RUN_ID: r{i}\nAccepted offline fixture.')
        self.put('reports/LATEST.md', f'RUN_ID: r{number}\nLatest fixture.')
        self.put('research/ROUND_REVIEW.json', {'schema_version': 1, 'run_id': f'r{number}',
            'evidence_paths': ['proofs/argument.md']})
        self.save_ledger()
        return epoch

    def record(self, number, *, pending=False):
        epoch = self.rounds(number, pending=pending)
        return scheduler.record_postaccept(self.root, self.project, self.ledger, epoch,
            f'r{number}', review_required=pending)

    def review(self, run='review-3', *, accepted=True):
        epoch = self.ledger['epochs'][0]
        epoch.update(review_pending=False, last_processed_run=run)
        self.state['last_run'] = run; self.put('research/STATE.json', self.state)
        self.put(f'reports/{run}.md', f'RUN_ID: {run}\nRoute review, not a counted scientific round.')
        self.put('research/ROUND_REVIEW.json', {'schema_version': 1, 'run_id': run,
            'evidence_paths': ['proofs/argument.md']})
        self.ledger['events'].append({'type': 'ROUTE_REVIEW', 'run_id': run, 'route': 'MAIN'})
        self.ledger['events'].append({'type': 'ROUTE_VERDICT_RECORDED', 'run_id': run, 'outcome': 'REFOCUS'})
        self.put('research/ROUTE_VERDICT.json', {'run_id': run, 'outcome': 'REFOCUS'})
        self.save_ledger()
        return scheduler.record_postaccept(self.root, self.project, self.ledger, epoch,
            run, reviewed=True, accepted=accepted)

    def test_periodic_uses_original_epoch_rounds_and_queueing_is_free(self):
        self.enable()
        policy = configuration.load_json(self.root / 'config/route_policy.json')
        policy['initial_round_budget'] = 30
        configuration.atomic_json(self.root / 'config/route_policy.json', policy)
        events = []
        with mock.patch.object(supervision, '_execute', side_effect=AssertionError('No models')):
            for number in range(1, 7):
                result = self.record(number)
                if result.get('event_id'): events.append(result['event_id'])
        self.assertEqual(len(events), 2)
        pending = scheduler.pending(self.root, self.project)
        self.assertEqual({e['trigger_run_id'] for e in pending['events']}, {'r3', 'r6'})
        self.assertEqual(pending['attempts_used'], 0)
        self.assertEqual(self.ledger['epochs'][0]['effective_rounds'], 6)

    def test_mid_epoch_enable_has_no_retroactive_bucket_or_recount(self):
        policy = configuration.load_json(self.root / 'config/route_policy.json')
        policy['initial_round_budget'] = 30
        configuration.atomic_json(self.root / 'config/route_policy.json', policy)
        self.rounds(5); self.enable()
        self.assertEqual(self.record(5)['status'], 'not_due')
        self.assertEqual(self.record(6)['status'], 'queued')
        self.assertEqual(len(scheduler.pending(self.root, self.project)['events']), 1)

    def test_duplicate_failure_and_dryrun_do_not_queue_or_spend(self):
        self.enable(); epoch = self.rounds(3)
        before = self.files()
        for kwargs in ({'accepted': False}, {'dry_run': True}):
            scheduler.record_postaccept(self.root, self.project, self.ledger, epoch, 'r3', **kwargs)
            self.assertEqual(before, self.files())
        one = scheduler.record_postaccept(self.root, self.project, self.ledger, epoch, 'r3')
        two = scheduler.record_postaccept(self.root, self.project, self.ledger, epoch, 'r3')
        three = scheduler.record_postaccept(self.root, self.project, self.ledger, epoch, 'r3')
        self.assertEqual(one['event_id'], two['event_id'])
        self.assertEqual(one['event_id'], three['event_id'])
        self.assertEqual(len(scheduler.pending(self.root, self.project)['events']), 1)
        self.assertEqual(scheduler.pending(self.root, self.project)['attempts_used'], 0)

    def test_missing_round_receipt_cannot_queue(self):
        self.enable(); epoch = self.rounds(3)
        (self.project / 'research/ROUND_REVIEW.json').unlink()
        with self.assertRaises(ValueError):
            scheduler.record_postaccept(self.root, self.project, self.ledger, epoch, 'r3')
        self.assertFalse(queue.home(self.root, self.project).exists())

    def test_route_review_defers_then_merges_with_post_review_snapshot(self):
        self.enable(); deferred = self.record(3, pending=True)
        self.assertEqual(deferred['status'], 'deferred')
        before = scheduler.pending(self.root, self.project)
        self.assertEqual(before['events'], [])
        self.assertEqual(len(before['deferred']), 1)
        self.assertEqual(before['attempts_used'], 0)
        one = self.review(); two = self.review()
        self.assertEqual(one['event_id'], two['event_id'])
        view = scheduler.pending(self.root, self.project)
        self.assertEqual(len(view['events']), 1)
        item = queue.read_event(self.root, self.project, one['event_id'])
        self.assertEqual(item['event']['trigger_type'], 'POST_ROUTE_REVIEW')
        self.assertEqual(item['event']['trigger_run_id'], 'r3')
        self.assertEqual(item['context']['review_run_id'], 'review-3')
        self.assertEqual(item['snapshot']['route_summary']['accepted_run_ids'], ['r1', 'r2', 'r3'])
        self.assertEqual(item['context']['trigger_reasons'], ['PERIODIC', 'ROUTE_REVIEW'])
        self.assertEqual(self.ledger['epochs'][0]['effective_rounds'], 3)

    def test_failed_review_keeps_deferred_and_changed_binding_conflicts(self):
        self.enable(); self.record(3, pending=True)
        self.review(accepted=False)
        self.assertEqual(len(scheduler.pending(self.root, self.project)['deferred']), 1)
        self.put('GOAL.md', 'A different operator goal, never silently rebound.')
        result = self.review('review-4')
        self.assertEqual(result['status'], 'conflict')
        self.assertEqual(scheduler.pending(self.root, self.project)['events'], [])

    def test_immutable_event_survives_log_write_interruption_and_restarts(self):
        self.enable(); self.rounds(3)
        with mock.patch.object(queue, 'append', side_effect=OSError('offline journal write failure')):
            with self.assertRaises(OSError):
                scheduler.record_postaccept(self.root, self.project, self.ledger,
                    self.ledger['epochs'][0], 'r3')
        view = scheduler.pending(self.root, self.project)
        self.assertEqual(len(view['events']), 1)
        self.assertTrue(view['events'][0]['recovery_required'])
        scheduler.record_postaccept(self.root, self.project, self.ledger, self.ledger['epochs'][0], 'r3')
        self.assertFalse(scheduler.pending(self.root, self.project)['events'][0]['recovery_required'])

    def test_claim_reserves_existing_budget_once_and_crash_never_refunds(self):
        self.enable(); event = self.record(3)['event_id']
        supervision.configure(self.root, self.project, {'enabled': True})
        old = supervision._load(self.root, self.project)
        old['attempts_used'] = 2; old['seconds_used'] = 5.0
        old['events'].append({'type': 'PRESERVE_ME', 'at': '2026-10-16T00:00:00Z'})
        supervision._save(self.root, self.project, old)
        first = scheduler.claim_event(self.root, self.project, event)
        second = scheduler.claim_event(self.root, self.project, event)
        self.assertTrue(first['claimed']); self.assertFalse(second['claimed'])
        saved = supervision._load(self.root, self.project)
        self.assertEqual(saved['attempts_used'], 3)
        self.assertEqual(saved['seconds_used'], 605.0)
        self.assertTrue(any(e['type'] == 'PRESERVE_ME' for e in saved['events']))
        self.assertEqual(scheduler.pending(self.root, self.project)['events'][0]['state'], 'RUNNING')
        scheduler.finish_claim(self.root, self.project, event, first['claim_token'], state='FAILED', elapsed_seconds=7)
        scheduler.finish_claim(self.root, self.project, event, first['claim_token'], state='FAILED', elapsed_seconds=7)
        self.assertEqual(supervision._load(self.root, self.project)['seconds_used'], 12.0)
        self.assertEqual(supervision._load(self.root, self.project)['attempts_used'], 3)
        self.assertFalse(scheduler.claim_event(self.root, self.project, event)['claimed'])

    def test_stop_needs_input_and_incomplete_transaction_block_claim(self):
        self.enable(); event = self.record(3)['event_id']
        for decision in ('STOP', 'NEEDS_INPUT'):
            self.state['decision'] = decision; self.put('research/STATE.json', self.state)
            self.assertFalse(scheduler.claim_event(self.root, self.project, event)['claimed'])
        self.state['decision'] = 'CONTINUE'; self.put('research/STATE.json', self.state)
        self.put('.control/STOP_REQUESTED', 'Operator stop')
        self.assertFalse(scheduler.claim_event(self.root, self.project, event)['claimed'])
        (self.project / '.control/STOP_REQUESTED').unlink()
        supervision.configure(self.root, self.project, {'enabled': True})
        data = supervision._load(self.root, self.project); data['pending_transaction'] = {'incomplete': True}
        supervision._save(self.root, self.project, data)
        self.assertFalse(scheduler.claim_event(self.root, self.project, event)['claimed'])
        self.assertEqual(supervision._load(self.root, self.project)['attempts_used'], 0)

    def test_active_attempt_is_readonly_and_cannot_be_closed_or_retargeted(self):
        self.enable(); event = self.record(3)['event_id']
        path = self.root / 'state/discovery/example.json'
        configuration.atomic_json(path, {'schema_version': 1, 'active_attempt': 'a1',
            'attempts': [{'id': 'a1', 'status': 'ACTIVE', 'problem_id': 'P-1', 'budget': 4}]})
        before = path.read_bytes()
        item = scheduler.pending(self.root, self.project)['events'][0]
        self.assertIn('ACTIVE_ATTEMPT_READONLY', item['restrictions'])
        result = scheduler.claim_event(self.root, self.project, event)
        self.assertTrue(result['claimed']); self.assertFalse(result['can_apply_guidance'])
        self.assertEqual(path.read_bytes(), before)

    def test_budget_limit_and_corrupt_queue_fail_without_resetting_counters(self):
        self.enable(); event = self.record(3)['event_id']
        supervision.configure(self.root, self.project, {'enabled': True, 'max_reviews': 1})
        saved = supervision._load(self.root, self.project); saved['attempts_used'] = 1
        supervision._save(self.root, self.project, saved)
        self.assertFalse(scheduler.claim_event(self.root, self.project, event)['claimed'])
        path = queue.home(self.root, self.project) / 'events.jsonl'
        path.write_text(path.read_text(encoding='utf8') + '{truncated', encoding='utf8')
        with self.assertRaises(ValueError): scheduler.pending(self.root, self.project)
        self.assertEqual(supervision._load(self.root, self.project)['attempts_used'], 1)

    def test_readonly_pending_and_cli_create_no_files_or_locks(self):
        self.enable()
        before = self.files()
        with mock.patch.object(research, 'ROOT', self.root), mock.patch.object(supervision, '_execute') as model:
            for argv in (['supervise', 'pending', '--dry-run'], ['supervise', 'status', 'example']):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(research.main(argv), 0)
            model.assert_not_called()
        self.assertEqual(self.files(), before)

    def test_disabled_event_protocol_preserves_legacy_policy_and_has_no_queue(self):
        epoch = self.rounds(3); before = self.files()
        result = scheduler.record_postaccept(self.root, self.project, self.ledger, epoch, 'r3')
        self.assertEqual(result['status'], 'disabled')
        self.assertEqual(before, self.files())

    def test_two_native_processes_claim_once(self):
        self.enable(); event = self.record(3)['event_id']
        worker = self.root / 'claim_worker.py'
        worker.write_text('import sys,json\nfrom pathlib import Path\n'
            + 'sys.path.insert(0,' + repr(str(ROOT)) + ')\n'
            + 'import configuration,supervision_scheduler as s\n'
            + 'configuration.ROOT=Path(sys.argv[1])\n'
            + 'print(json.dumps(s.claim_event(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3])))\n', encoding='utf8')
        command = [sys.executable, '-B', str(worker), str(self.root), str(self.project), event]
        one = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        two = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        outputs = [one.communicate(timeout=30), two.communicate(timeout=30)]
        self.assertEqual(one.returncode, 0, outputs[0]); self.assertEqual(two.returncode, 0, outputs[1])
        replies = [json.loads(out) for out, err in outputs]
        self.assertEqual(sum(r['claimed'] for r in replies), 1)
        self.assertEqual(supervision._load(self.root, self.project)['attempts_used'], 1)

    def test_acknowledged_input_cannot_disappear_or_be_rebuilt_with_new_sources(self):
        self.enable(); event = self.record(3)['event_id']
        path = queue.home(self.root, self.project) / 'events' / (event + '.json')
        path.unlink()
        with self.assertRaises(ValueError): scheduler.pending(self.root, self.project)
        self.put('proofs/argument.md', 'Changed source must not replace lost frozen inputs.')
        with self.assertRaises(ValueError): self.record(3)

    def test_reservation_ack_failure_cannot_hide_removed_cost_receipt(self):
        self.enable(); event = self.record(3)['event_id']
        append = queue.append
        def fail_reserved(controller, project, kind, key, **details):
            if kind == 'CALL_RESERVED': raise OSError('After shared cost reservation, before ack')
            return append(controller, project, kind, key, **details)
        with mock.patch.object(queue, 'append', side_effect=fail_reserved):
            with self.assertRaises(OSError): scheduler.claim_event(self.root, self.project, event)
        data = supervision._load(self.root, self.project)
        self.assertEqual(data['attempts_used'], 1)
        del data['event_reservations'][event]; supervision._save(self.root, self.project, data)
        with self.assertRaises(ValueError): scheduler.claim_event(self.root, self.project, event)
        self.assertEqual(supervision._load(self.root, self.project)['attempts_used'], 1)

    def test_finish_ack_interruption_is_visible_and_repaired_without_refund_twice(self):
        self.enable(); event = self.record(3)['event_id']
        first = scheduler.claim_event(self.root, self.project, event)
        with mock.patch.object(queue, 'append', side_effect=OSError('After cost completion, before ack')):
            with self.assertRaises(OSError): scheduler.finish_claim(self.root, self.project, event,
                first['claim_token'], state='FAILED', elapsed_seconds=3)
        self.assertTrue(scheduler.pending(self.root, self.project)['events'][0]['recovery_required'])
        scheduler.finish_claim(self.root, self.project, event, first['claim_token'], state='FAILED', elapsed_seconds=3)
        self.assertFalse(scheduler.pending(self.root, self.project)['events'][0]['recovery_required'])
        self.assertEqual(supervision._load(self.root, self.project)['attempts_used'], 1)
        self.assertEqual(supervision._load(self.root, self.project)['seconds_used'], 3)

    def test_current_epoch_focus_or_route_review_prevents_stale_claim(self):
        self.enable(); event = self.record(3)['event_id']
        saved = copy.deepcopy(self.ledger)
        for mutate in (lambda e: e.update(epoch=2), lambda e: e['focus'].update(anchor_id='0' * 64),
                       lambda e: e.update(review_pending=True)):
            self.ledger = copy.deepcopy(saved); mutate(self.ledger['epochs'][0]); self.save_ledger()
            self.assertFalse(scheduler.claim_event(self.root, self.project, event)['claimed'])
        self.assertIsNone(supervision._load(self.root, self.project))

    def test_fake_epoch_and_legacy_pause_cannot_bypass_preflight(self):
        self.enable(); epoch = self.rounds(2)
        fake = copy.deepcopy(epoch); fake['effective_rounds'] = 3
        with self.assertRaises(ValueError): scheduler.record_postaccept(self.root, self.project, self.ledger, fake, 'r2')
        supervision.configure(self.root, self.project, {'enabled': True})
        data = supervision._load(self.root, self.project)
        data['records']['old-paused-review'] = {'decision': 'PAUSE'}
        data['active_review'] = 'old-paused-review'; supervision._save(self.root, self.project, data)
        self.assertFalse(scheduler.before_run(self.root, self.project, self.ledger, epoch)['proceed'])

    def test_invalid_route_review_cannot_resolve_a_deferred_trigger(self):
        self.enable(); self.record(3, pending=True)
        self.review(accepted=False)
        self.ledger['events'] = [e for e in self.ledger['events'] if e['type'] != 'ROUTE_VERDICT_RECORDED']
        self.ledger['events'].append({'type': 'ROUTE_REVIEW_INVALID', 'run_id': 'review-3'})
        self.save_ledger()
        result = scheduler.record_postaccept(self.root, self.project, self.ledger,
            self.ledger['epochs'][0], 'review-3', reviewed=True)
        self.assertEqual(result['status'], 'deferred')
        self.assertEqual(len(scheduler.pending(self.root, self.project)['deferred']), 1)
        self.assertEqual(scheduler.pending(self.root, self.project)['events'], [])

    def test_manual_request_defers_durably_even_before_review_pending_is_marked(self):
        self.enable(); self.rounds(3)
        policy = configuration.load_json(self.root / 'config/route_policy.json')
        policy['initial_round_budget'] = 3; configuration.atomic_json(self.root / 'config/route_policy.json', policy)
        result = scheduler.record_manual(self.root, self.project)
        self.assertEqual(result['status'], 'deferred')
        deferred = scheduler.pending(self.root, self.project)['deferred']
        self.assertEqual(len(deferred), 1)
        self.assertIn('MANUAL', deferred[0]['context']['trigger_reasons'])
        self.review()
        event = scheduler.pending(self.root, self.project)['events'][0]
        self.assertIn('MANUAL', event['context']['trigger_reasons'])

    def test_scheduler_checks_original_stagnation_even_if_caller_omits_reason(self):
        self.enable(); epoch = self.rounds(3)
        epoch['stagnation'] = 3; self.save_ledger()
        result = scheduler.record_postaccept(self.root, self.project, self.ledger, epoch, 'r3')
        self.assertEqual(result['status'], 'deferred')
        self.assertEqual(scheduler.pending(self.root, self.project)['events'], [])

    def test_multiple_deferrals_select_latest_scientific_run_in_ledger_order(self):
        self.enable(); self.record(3, pending=True); self.record(6, pending=True)
        self.review(accepted=False)
        deferred = sorted(queue.deferrals(self.root, self.project), key=lambda d: d['identity']['trigger_run_id'], reverse=True)
        with mock.patch.object(queue, 'deferrals', return_value=deferred):
            result = scheduler.record_postaccept(self.root, self.project, self.ledger,
                self.ledger['epochs'][0], 'review-3', reviewed=True)
        event = queue.read_event(self.root, self.project, result['event_id'])
        self.assertEqual(event['event']['trigger_run_id'], 'r6')
        self.assertEqual(set(event['context']['origin_run_ids']), {'r3', 'r6'})

    def test_native_lock_owner_crash_keeps_pending_and_releases_for_one_reservation(self):
        self.enable(); event = self.record(3)['event_id']
        worker = self.root / 'lock_owner.py'
        ready = self.root / 'owner-ready'
        worker.write_text('import sys\nfrom pathlib import Path\n'
            + 'sys.path.insert(0,' + repr(str(ROOT)) + ')\nfrom route_budget import file_lock\n'
            + 'with file_lock(Path(sys.argv[1])):\n Path(sys.argv[2]).write_text("ready")\n sys.stdin.read()\n', encoding='utf8')
        lock = self.root / 'locks/route-example.lock'
        owner = subprocess.Popen([sys.executable, '-B', str(worker), str(lock), str(ready)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: owner.communicate(timeout=10) if owner.poll() is not None else
                        (owner.kill(), owner.communicate(timeout=10)))
        deadline = time.monotonic() + 15
        while not ready.exists() and owner.poll() is None and time.monotonic() < deadline: time.sleep(.01)
        self.assertTrue(ready.exists(), 'Native process failed to acquire the lock')
        result = scheduler.claim_event(self.root, self.project, event)
        self.assertEqual(result['reason'], 'LOCKED')
        self.assertEqual(scheduler.pending(self.root, self.project)['events'][0]['state'], 'QUEUED')
        self.assertIsNone(supervision._load(self.root, self.project))
        self.assertEqual(len(list((queue.home(self.root, self.project) / 'lock-conflicts').glob('*.json'))), 1)
        owner.terminate(); owner.communicate(timeout=10)
        self.assertTrue(scheduler.claim_event(self.root, self.project, event)['claimed'])
        self.assertEqual(supervision._load(self.root, self.project)['attempts_used'], 1)

    def test_entire_cost_ledger_loss_after_reservation_ack_failure_blocks_reenrollment(self):
        self.enable(); event = self.record(3)['event_id']
        append = queue.append
        def fail_ack(controller, project, kind, key, **details):
            if kind == 'CALL_RESERVED': raise OSError('After cost commit, before acknowledgement')
            return append(controller, project, kind, key, **details)
        with mock.patch.object(queue, 'append', side_effect=fail_ack):
            with self.assertRaises(OSError): scheduler.claim_event(self.root, self.project, event)
        path = supervision._home(self.root, self.project) / 'ledger.json'
        original = path.read_bytes(); path.unlink()
        with self.assertRaises(ValueError): scheduler.claim_event(self.root, self.project, event)
        self.assertFalse(path.exists(), 'Missing ledger cannot be re-enrolled as zero cost')
        path.write_bytes(original)
        self.assertFalse(scheduler.claim_event(self.root, self.project, event)['claimed'])
        self.assertEqual(supervision._load(self.root, self.project)['attempts_used'], 1)

    def test_cost_save_interruption_before_dispatch_recovers_same_reservation_intent(self):
        self.enable(); event = self.record(3)['event_id']
        supervision.configure(self.root, self.project, {'enabled': True})
        original = supervision._save
        def fail_cost(controller, project, data):
            if data.get('event_reservations'): raise OSError('Before cost commit')
            return original(controller, project, data)
        with mock.patch.object(supervision, '_save', side_effect=fail_cost):
            with self.assertRaises(OSError): scheduler.claim_event(self.root, self.project, event)
        self.assertEqual(supervision._load(self.root, self.project)['attempts_used'], 0)
        intents = [op for op in queue.operations(self.root, self.project) if op['type'] == 'RESERVATION_INTENT']
        self.assertEqual(len(intents), 1)
        result = scheduler.claim_event(self.root, self.project, event)
        self.assertTrue(result['claimed'])
        self.assertEqual(supervision._load(self.root, self.project)['attempts_used'], 1)
        self.assertEqual(len([op for op in queue.operations(self.root, self.project) if op['type'] == 'RESERVATION_INTENT']), 1)


if __name__ == '__main__': unittest.main()
