"""Offline positive/negative replay of production supervision signals.

Reference expectations live in a fixture file which is never passed to the
production detector. No live projects, model calls or mathematical claims.
"""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

import supervision_quality as quality


FIXTURE = Path(__file__).parent / 'research_benchmark' / 'supervision_cases.json'


class SupervisionQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = json.loads(FIXTURE.read_text(encoding='utf-8'))

    def case(self, name):
        return copy.deepcopy(next(case for case in self.reference['cases'] if case['id'] == name))

    def assess(self, rounds, **kwargs):
        return quality.assess_quality(rounds, core_obligations=self.reference['core_obligations'],
                                      anchor_id=self.reference['anchor_id'], **kwargs)

    def codes(self, result):
        return {finding['code'] for finding in result['findings']}

    def test_reference_cases_use_the_production_detector(self):
        for reference in self.reference['cases']:
            with self.subTest(case=reference['id']):
                rounds = copy.deepcopy(reference['rounds'])
                before = copy.deepcopy(rounds)
                result = self.assess(rounds)
                self.assertEqual(result['assessment'], reference['expected']['assessment'])
                self.assertEqual(self.codes(result), set(reference['expected']['finding_codes']))
                self.assertEqual(result['window_run_ids'], [item['run_id'] for item in rounds])
                self.assertEqual(rounds, before)
                for finding in result['findings']:
                    self.assertTrue(finding['reason'])
                    self.assertEqual(finding['obligation_ids'], sorted(self.reference['core_obligations']))
                    self.assertTrue(set(finding['run_ids']) <= set(result['window_run_ids']))
                    self.assertTrue(finding['evidence_paths'])

    def test_repeated_receipt_cannot_inflate_a_support_streak(self):
        record = self.case('unrelated-auxiliary-lemmas')['rounds'][0]
        result = self.assess([record, copy.deepcopy(record), copy.deepcopy(record)])
        self.assertEqual(result['window_run_ids'], [record['run_id']])
        self.assertEqual(result['assessment'], 'INSUFFICIENT_DATA')
        self.assertEqual(result['findings'], [])

    def test_nonaccepted_events_are_excluded_from_ledger_replay(self):
        rounds = self.case('unrelated-auxiliary-lemmas')['rounds']
        rounds[-1]['type'] = 'FAILED_RESEARCH_ROUND'
        result = quality.from_ledger({'events': rounds},
                                    {'anchor_id': self.reference['anchor_id']},
                                    self.reference['core_obligations'])
        self.assertEqual(len(result['window_run_ids']), 2)
        self.assertEqual(result['assessment'], 'INSUFFICIENT_DATA')
        self.assertEqual(result['findings'], [])

    def test_duplicate_event_does_not_replace_accepted_metadata(self):
        rounds = self.case('necessary-direct-dependency')['rounds']
        false_duplicate = copy.deepcopy(rounds[-1])
        false_duplicate['goal_alignment'] = {'scope': 'SUPPORT', 'mainline_progress': False}
        result = self.assess(rounds + [false_duplicate])
        self.assertEqual(result['assessment'], 'ON_TRACK')
        self.assertEqual(result['findings'], [])

    def test_missing_legacy_metadata_is_unknown_and_inputs_stay_unchanged(self):
        ledger = {'events': [{'type': 'RESEARCH_ROUND', 'run_id': 'legacy-' + str(i)}
                             for i in range(3)],
                  'epochs': [{'counted_run_ids': ['legacy-' + str(i) for i in range(3)],
                              'effective_rounds': 3, 'stagnation': 3, 'round_budget': 7}]}
        original = copy.deepcopy(ledger)
        result = quality.from_ledger(ledger, {'anchor_id': self.reference['anchor_id']},
                                    self.reference['core_obligations'])
        self.assertEqual(result['assessment'], 'INSUFFICIENT_DATA')
        self.assertEqual(result['findings'], [])
        self.assertEqual(ledger, original)
        self.assertIn('unknown', result['note'])

    def test_missing_anchor_cannot_bind_older_support_work_to_current_goal(self):
        rounds = self.case('unrelated-auxiliary-lemmas')['rounds']
        for record in rounds:
            record.pop('anchor_id')
        result = self.assess(rounds)
        self.assertEqual(result['assessment'], 'INSUFFICIENT_DATA')
        self.assertEqual(result['findings'], [])

    def test_other_focus_is_excluded_and_old_drift_falls_outside_window(self):
        old = self.case('unrelated-auxiliary-lemmas')['rounds']
        current = self.case('necessary-direct-dependency')['rounds']
        for index, record in enumerate(current):
            record['run_id'] = 'current-' + str(index)
        for record in old:
            record['anchor_id'] = 'previous-focus'
        result = self.assess(old + current)
        self.assertEqual(result['assessment'], 'ON_TRACK')
        self.assertEqual(result['findings'], [])
        for record in old:
            record['anchor_id'] = self.reference['anchor_id']
        result = self.assess(old + current)
        self.assertEqual(result['assessment'], 'ON_TRACK')
        self.assertEqual(result['window_run_ids'], [record['run_id'] for record in current])

    def test_truncated_accepted_history_keeps_an_unknown_round_in_window(self):
        rounds = self.case('unrelated-auxiliary-lemmas')['rounds']
        ledger = {'events': rounds[:2],
                  'epochs': [{'counted_run_ids': [item['run_id'] for item in rounds]}]}
        result = quality.from_ledger(ledger, {'anchor_id': self.reference['anchor_id']},
                                    self.reference['core_obligations'])
        self.assertEqual(result['window_run_ids'], [item['run_id'] for item in rounds])
        self.assertEqual(result['assessment'], 'INSUFFICIENT_DATA')
        self.assertEqual(result['findings'], [])

    def test_shared_background_with_new_evidence_is_not_a_repeated_result(self):
        rounds = self.case('necessary-direct-dependency')['rounds']
        for record in rounds:
            record['evidence_hashes']['literature/background.txt'] = 'f' * 64
        result = self.assess(rounds)
        self.assertEqual(result['assessment'], 'ON_TRACK')
        self.assertEqual(result['findings'], [])

    def test_declared_progress_without_historical_evidence_is_unknown(self):
        rounds = self.case('necessary-direct-dependency')['rounds']
        for record in rounds:
            record.pop('evidence_hashes')
        result = self.assess(rounds)
        self.assertEqual(result['assessment'], 'INSUFFICIENT_DATA')
        self.assertEqual(result['findings'], [])

    def test_malformed_progress_and_hashes_do_not_create_positive_certification(self):
        rounds = self.case('necessary-direct-dependency')['rounds']
        rounds[0]['goal_alignment']['mainline_progress'] = 'true'
        rounds[1]['evidence_hashes'] = {'proofs/attempt.md': 'not-a-content-hash'}
        result = self.assess(rounds)
        self.assertEqual(result['assessment'], 'INSUFFICIENT_DATA')
        self.assertEqual(result['findings'], [])

    def test_less_than_three_explicit_support_rounds_do_not_imply_drift(self):
        rounds = self.case('unrelated-auxiliary-lemmas')['rounds']
        result = self.assess(rounds, window=2)
        self.assertEqual(result['assessment'], 'INSUFFICIENT_DATA')
        self.assertEqual(result['findings'], [])

    def test_replay_preserves_budgets_and_evidence_in_memory(self):
        rounds = self.case('unrelated-auxiliary-lemmas')['rounds']
        ledger = {'events': rounds, 'epochs': [{'counted_run_ids': [item['run_id'] for item in rounds],
                                              'round_budget': 9, 'effective_rounds': 3,
                                              'seconds_used': 123.4}]}
        original = copy.deepcopy(ledger)
        result = quality.from_ledger(ledger, {'anchor_id': self.reference['anchor_id']},
                                    self.reference['core_obligations'])
        self.assertIn('SUPPORT_DRIFT', self.codes(result))
        self.assertEqual(ledger, original)
        # Results must remain suitable for an auditable, schema-free JSON replay.
        self.assertEqual(json.loads(json.dumps(result)), result)

    def test_invalid_window_and_empty_anchor_are_rejected(self):
        for window in (0, 101, True, '3'):
            with self.subTest(window=window), self.assertRaises(ValueError):
                self.assess([], window=window)
        with self.assertRaises(ValueError):
            quality.assess_quality([], core_obligations={}, anchor_id='')

    def test_runner_acceptance_preserves_historical_quality_metadata(self):
        import configuration
        import research_focus
        import route_budget
        import runner

        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='supervision acceptance ') as directory:
            controller = Path(directory)
            shutil.copytree(source / 'config', controller / 'config')
            project = controller / 'projects' / 'synthetic-example'

            def put(relative, value):
                path = project / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value) if isinstance(value, dict) else value, encoding='utf-8')
                return path

            put('PROJECT.json', {'id': 'synthetic-example', 'checks': []})
            put('GOAL.md', 'Frozen synthetic invariant; preserve the exact input and output interface.')
            state = {'phase': 'FALSIFICATION', 'decision': 'CONTINUE', 'research_route': 'SYNTHETIC/MAIN',
                     'priority_problem': 'Establish the exact synthetic invariant.',
                     'next_task': 'Check the directly necessary construction dependency.', 'last_run': None}
            put('research/STATE.json', state)
            proof = put('proofs/dependency.md', 'Initial unresolved synthetic dependency.')
            with mock.patch.object(configuration, 'ROOT', controller):
                _, ledger, epoch = route_budget.load_ledger(controller, project, state)
                policy, _, _ = route_budget.policy_for(controller, project)
                focus = research_focus.ensure_focus(project, epoch, state)
                for index in range(3):
                    run_id = 'accepted-synthetic-' + str(index)
                    baseline = route_budget.evidence_snapshot(project)
                    proof.write_text('Fresh synthetic dependency evidence version ' + str(index), encoding='utf-8')
                    put('research/ROUND_REVIEW.json', {
                        'schema_version': 1, 'run_id': run_id, 'work_kind': 'PROOF',
                        'core_problem': 'The frozen synthetic invariant.',
                        'theoretical_obligation': 'A directly necessary invariant dependency.',
                        'nontriviality_argument': 'An explicit dependency is still open.',
                        'contribution_type': 'NONE', 'result_status': 'OPEN',
                        'evidence_paths': ['proofs/dependency.md'],
                        'goal_impact': {'anchor_id': focus['anchor_id'], 'scope': 'DIRECT_DEPENDENCY',
                                        'target_obligation': 'SECURITY', 'before': 'Open step ' + str(index),
                                        'after': 'Bound the explicit dependency ' + str(index),
                                        'consumer_claim': 'The frozen synthetic invariant.',
                                        'dependency_argument': 'The core construction directly invokes this bound.',
                                        'next_mainline_task': 'Test the next exact invariant condition.'}})
                    put('research/ROUTE_SIGNAL.json', {
                        'run_id': run_id, 'progress_type': 'PROOF_STEP',
                        'reason': 'New evidence addresses the explicitly necessary frozen construction dependency.',
                        'evidence_paths': ['proofs/dependency.md'], 'route_blocked': False})
                    state['last_run'] = run_id
                    put('research/STATE.json', state)
                    with mock.patch('builtins.print'):
                        runner.record_round(project, ledger, epoch, policy, state, baseline)
                    event = next(item for item in ledger['events'] if item.get('run_id') == run_id)
                    self.assertEqual(event['anchor_id'], focus['anchor_id'])
                    self.assertEqual(event['work_kind'], 'PROOF')
                    self.assertEqual(event['result_status'], 'OPEN')
                    self.assertEqual(event['evidence_hashes'], {
                        'proofs/dependency.md': hashlib.sha256(proof.read_bytes()).hexdigest()})
                    self.assertTrue(event['goal_alignment']['mainline_progress'])
                accepted_ledger = copy.deepcopy(ledger)
                original = quality.from_ledger(ledger, focus, self.reference['core_obligations'])
                self.assertEqual(original['assessment'], 'ON_TRACK')
                # Later file changes cannot rewrite the accepted historical hashes.
                proof.write_text('Later unaccepted contents must never backfill old evidence.', encoding='utf-8')
                self.assertEqual(quality.from_ledger(ledger, focus, self.reference['core_obligations']), original)
                self.assertEqual(ledger, accepted_ledger)


if __name__ == '__main__':
    unittest.main()
