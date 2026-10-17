"""N03: original COMPLETE acceptance survives legal route display truncation."""
import contextlib
import io
import json
import unittest
from unittest import mock

import configuration
import research_acceptance
import route_budget
import runner
import runner_core
from candidate_search import scheduler
from engine import discovery_scheduler
from engine.common import ledger, object_hash
import test_candidate_scheduler as fixture


class CandidateHistoryReviewTests(unittest.TestCase):
    setUp = fixture.CandidateSchedulerTests.setUp
    tearDown = fixture.CandidateSchedulerTests.tearDown
    put = fixture.CandidateSchedulerTests.put
    files = fixture.CandidateSchedulerTests.files
    make = fixture.CandidateSchedulerTests.make
    candidate_spec = fixture.CandidateSchedulerTests.candidate_spec
    spec_problem = fixture.CandidateSchedulerTests.spec_problem
    add = fixture.CandidateSchedulerTests.add
    selection = fixture.CandidateSchedulerTests.selection
    register_route = fixture.CandidateSchedulerTests.register_route
    bind = fixture.CandidateSchedulerTests.bind

    def accepted(self):
        """Use the real wrapper commit/recovery and original call settlement."""
        self.register_route()
        self.add()
        selected = self.selection()
        attempt = self.bind(selected)
        run_id = 'original-accepted-offline-run'
        path, data, epoch = route_budget.load_ledger(self.root, self.project, route_budget.state_read(self.project))
        transaction = runner_core.ProjectTransaction(self.project).capture()
        journal = research_acceptance.begin(self.root, self.project, transaction, path, data)
        before = route_budget.evidence_snapshot(self.project)
        discovery_scheduler.begin_call(self.project, run_id)
        state = route_budget.state_read(self.project)
        state['last_run'] = run_id
        self.put('research/STATE.json', state)
        self.put('research/ROUND_REVIEW.json', {
            'schema_version': 1, 'run_id': run_id, 'work_kind': 'CORE_RESEARCH',
            'result_status': 'NO_PROGRESS', 'core_problem': 'The unchanged exact integer fixture',
            'theoretical_obligation': 'No mathematical progress or new theorem is asserted',
            'nontriviality_argument': 'Exercise original local acceptance and historical ownership only',
            'contribution_type': 'NONE', 'evidence_paths': []})
        self.put('research/ROUTE_SIGNAL.json', {'run_id': run_id, 'progress_type': 'NO_PROGRESS',
            'reason': 'Original controller acceptance fixture without model execution or a scientific success claim.',
            'evidence_paths': [], 'route_blocked': False})
        policy = route_budget.policy_for(self.root, self.project)[0]
        with contextlib.redirect_stdout(io.StringIO()):
            runner.record_round(self.project, data, epoch, policy, state, before)
        discovery_scheduler.finish_call(self.project, run_id, accepted=True, pending_wrapper=True)
        research_acceptance.commit(self.root, self.project, journal, data, run_id, 'ACCEPTED',
                                   initialization=False, reviewed=False)
        with mock.patch.object(runner, 'run_child', side_effect=AssertionError('No research dispatch')), \
             mock.patch.object(runner_core, 'codex_run', side_effect=AssertionError('No model')), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.continue_accepted(self.project, policy, journal), (0, 'ACCEPTED'))
        complete = research_acceptance.load(self.root, self.project)
        self.assertEqual(complete['phase'], 'COMPLETE')
        self.assertEqual(complete['discovery_owner_attempt_id'], attempt['id'])
        self.assertEqual(ledger(self.project)['attempts'][0]['calls'][0]['status'], 'ACCEPTED')
        self.assertEqual(complete['route_after']['epochs'][-1]['effective_rounds'], 1)
        self.assertFalse(ledger(self.project)['attempts'][0]['calls'][0]['evaluation']['scientific_acceptance'])
        self.assertTrue((research_acceptance.path_for(self.root, self.project).parent / 'example' /
                         (complete['transaction_id'] + '.json')).is_file())
        return selected, attempt, run_id, complete

    def trim_display(self, run_id):
        state = route_budget.state_read(self.project)
        path, data, _ = route_budget.load_ledger(self.root, self.project, state)
        data['events'].extend({'type': 'LOCAL_AUDIT_NOTE', 'sequence': number} for number in range(3001))
        route_budget.save_ledger(path, data)
        current = json.loads(path.read_text(encoding='utf8'))
        self.assertEqual(len(current['events']), 3000)
        self.assertFalse(any(event.get('run_id') == run_id for event in current['events']))
        self.assertIn(run_id, current['epochs'][0]['counted_run_ids'])

    def map(self, selected, attempt, run_id):
        return scheduler.record_run_mapping(self.project, selected['selection']['selection_id'], run_id,
            expected_attempt_id=attempt['id'], reason='Map original owner-bound historical acceptance')

    def authority_files(self):
        return {path: data for path, data in self.files().items() if not path.startswith(
            ('state/candidates/', 'state/candidate_selection_registry/', 'locks/'))}

    def all_files(self):
        return {path: data for path, data in self.files().items() if not path.startswith('locks/')}

    def complete_paths(self):
        latest = research_acceptance.path_for(self.root, self.project)
        return [latest, *list((latest.parent / 'example').glob('*.json'))]

    def alter_complete(self, change):
        for path in self.complete_paths():
            value = json.loads(path.read_text(encoding='utf8'))
            change(value)
            value['journal_sha256'] = research_acceptance.digest({key: item for key, item in value.items()
                                                                  if key != 'journal_sha256'})
            configuration.atomic_json(path, value)

    def test_t05_existing_mapping_replay_is_read_only_after_legal_event_truncation(self):
        selected, attempt, run_id, _ = self.accepted()
        first = self.map(selected, attempt, run_id)
        self.trim_display(run_id)
        before = self.all_files()
        repeated = self.map(selected, attempt, run_id)
        self.assertTrue(repeated['idempotent'])
        self.assertEqual(first['mapping'], repeated['mapping'])
        self.assertEqual(self.all_files(), before)
        self.assertEqual(len(scheduler.status(self.project)['run_mappings']), 1)

    def test_t06_first_late_mapping_uses_original_complete_after_display_truncation(self):
        selected, attempt, run_id, complete = self.accepted()
        self.trim_display(run_id)
        before = self.authority_files()
        result = self.map(selected, attempt, run_id)
        self.assertFalse(result['idempotent'])
        self.assertEqual(result['mapping']['call_status'], 'ACCEPTED')
        self.assertEqual(result['mapping']['route_event_sha256'], object_hash(complete['route_after']['events'][-1]))
        self.assertFalse(result['mapping']['new_budget_charge'])
        self.assertFalse(result['mapping']['scientific_acceptance'])
        self.assertEqual(self.authority_files(), before)

    def test_t06_missing_complete_cannot_invent_first_mapping(self):
        selected, attempt, run_id, _ = self.accepted()
        self.trim_display(run_id)
        for path in self.complete_paths():
            path.unlink()
        before = self.all_files()
        with self.assertRaisesRegex(ValueError, 'COMPLETE acceptance receipt'):
            self.map(selected, attempt, run_id)
        self.assertEqual(self.all_files(), before)

    def test_t06_late_first_mapping_reads_archive_when_latest_is_another_transaction(self):
        selected, attempt, run_id, _ = self.accepted()
        self.trim_display(run_id)
        path, data, _ = route_budget.load_ledger(self.root, self.project, route_budget.state_read(self.project))
        transaction = runner_core.ProjectTransaction(self.project).capture()
        later = research_acceptance.begin(self.root, self.project, transaction, path, data)
        research_acceptance.abort(self.root, self.project, later, 'Unexecuted later local fixture transaction')
        before = self.authority_files()
        mapped = self.map(selected, attempt, run_id)
        self.assertEqual(mapped['mapping']['call_status'], 'ACCEPTED')
        self.assertFalse(mapped['mapping']['scientific_acceptance'])
        self.assertEqual(self.authority_files(), before)

    def test_late_first_mapping_still_checks_complete_original_owner(self):
        selected, attempt, run_id, _ = self.accepted()
        self.trim_display(run_id)
        self.alter_complete(lambda value: value.update(discovery_owner_attempt_id='attempt-9999'))
        before = self.all_files()
        with self.assertRaisesRegex(ValueError, 'COMPLETE acceptance receipt binding|DISCOVERY_AUTHORITY'):
            self.map(selected, attempt, run_id)
        self.assertEqual(self.all_files(), before)

    def test_late_first_mapping_still_checks_settlement(self):
        selected, attempt, run_id, _ = self.accepted()
        self.trim_display(run_id)
        discovery_scheduler._settlement_path(self.project, attempt['id'], run_id).unlink()
        before = self.all_files()
        with self.assertRaises(ValueError):
            self.map(selected, attempt, run_id)
        self.assertEqual(self.all_files(), before)

    def test_late_first_mapping_still_checks_frozen_anchor_and_epoch(self):
        selected, attempt, run_id, _ = self.accepted()
        self.trim_display(run_id)
        self.alter_complete(lambda value: value['route_after']['events'][-1].update(anchor_id='0' * 64))
        with self.assertRaisesRegex(ValueError, 'anchor|epoch'):
            self.map(selected, attempt, run_id)

    def test_late_first_mapping_still_checks_original_epoch_identity(self):
        selected, attempt, run_id, _ = self.accepted()
        self.trim_display(run_id)
        self.alter_complete(lambda value: value['route_after']['epochs'][0].update(epoch=999))
        with self.assertRaisesRegex(ValueError, 'epoch'):
            self.map(selected, attempt, run_id)

    def test_late_first_mapping_still_checks_complete_terminal_call_binding(self):
        selected, attempt, run_id, _ = self.accepted()
        self.trim_display(run_id)
        self.alter_complete(lambda value: value['steps']['discovery'].update(call_sha256='0' * 64))
        with self.assertRaisesRegex(ValueError, 'settled owner/call'):
            self.map(selected, attempt, run_id)

    def test_late_first_mapping_still_requires_archived_counted_identity(self):
        selected, attempt, run_id, _ = self.accepted()
        self.trim_display(run_id)
        self.alter_complete(lambda value: value['route_after']['epochs'][0]['counted_run_ids'].clear())
        with self.assertRaisesRegex(ValueError, 'COMPLETE acceptance route image'):
            self.map(selected, attempt, run_id)

    def test_current_visible_event_conflicting_with_complete_is_rejected(self):
        selected, attempt, run_id, _ = self.accepted()
        path, data, _ = route_budget.load_ledger(self.root, self.project, route_budget.state_read(self.project))
        data['events'][-1]['note'] = 'Not the immutable event accepted for this run'
        route_budget.save_ledger(path, data)
        with self.assertRaisesRegex(ValueError, 'COMPLETE acceptance route image'):
            self.map(selected, attempt, run_id)


if __name__ == '__main__':
    unittest.main()
