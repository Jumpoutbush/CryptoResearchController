"""Candidate scheduling CLI preserves catalog commands and frozen plan CAS."""
import json
import unittest

import test_candidate_cli as fixtures


class CandidateScheduleCliTests(unittest.TestCase):
    def setUp(self):
        self.wrapper = fixtures.CandidateCliTests('test_three_cli_proposals_remain_unreviewed')
        self.wrapper.setUp()
        self.f = self.wrapper.f

    def tearDown(self):
        self.wrapper.tearDown()

    def test_plan_and_schedule_status_are_read_only(self):
        self.wrapper.propose()
        before = self.f.files()
        code, first = self.wrapper.invoke('plan', 'example', '--dry-run')
        self.assertEqual(code, 0)
        self.assertEqual(self.wrapper.invoke('plan', 'example')[1], first)
        self.assertEqual(self.wrapper.invoke('schedule-status', 'example')[0], 0)
        self.assertEqual(self.f.files(), before)

    def test_select_rejects_incomplete_or_stale_plan_file(self):
        self.wrapper.propose()
        self.assertEqual(self.wrapper.invoke('status', 'example', '--id', 'C-0001',
            '--status', 'READY_FOR_ATTEMPT', '--expected-revision', '1', '--reason', 'Prepare fixture')[0], 0)
        file = self.f.root / 'plan.json'
        file.write_text(json.dumps({'snapshot': {}}), encoding='utf8')
        args = ['select', 'example', '--id', 'C-0001', '--expected-revision', '1',
                '--plan-file', str(file), '--reason', 'Explicit selection of fixture']
        self.assertEqual(self.wrapper.invoke(*args)[0], 2)
        code, plan = self.wrapper.invoke('plan', 'example')
        self.assertEqual(code, 0)
        file.write_text(json.dumps(plan), encoding='utf8')
        self.wrapper.propose('C-0002')
        self.assertEqual(self.wrapper.invoke(*args)[0], 2)

    def test_select_is_advisory_and_legacy_candidate_status_still_works(self):
        self.wrapper.propose()
        code, ready = self.wrapper.invoke('status', 'example', '--id', 'C-0001',
            '--status', 'READY_FOR_ATTEMPT', '--expected-revision', '1', '--reason', 'Prepare fixture')
        self.assertEqual(code, 0)
        self.assertTrue(ready['eligible_for_attempt'])
        state_before = (self.f.project / 'research/STATE.json').read_bytes()
        problem_before = (self.f.project / 'research/discovery/PROBLEMS.json').read_bytes()
        code, plan = self.wrapper.invoke('plan', 'example')
        self.assertEqual(code, 0)
        file = self.f.root / 'plan.json'
        file.write_text(json.dumps(plan), encoding='utf8')
        args = ['select', 'example', '--id', 'C-0001', '--expected-revision', '1',
                '--plan-file', str(file), '--reason', 'Review original fixed problem before attempting']
        first = self.wrapper.invoke(*args)
        self.assertEqual(first[0], 0)
        before_retry = {k: v for k, v in self.f.files().items() if not k.startswith('locks/')}
        second = self.wrapper.invoke(*args)
        self.assertEqual(second[0], 0)
        self.assertEqual(second[1]['selection'], first[1]['selection'])
        self.assertEqual({k: v for k, v in self.f.files().items() if not k.startswith('locks/')}, before_retry)
        self.assertFalse((self.f.root / 'state/discovery/example.json').exists())
        self.assertEqual((self.f.project / 'research/STATE.json').read_bytes(), state_before)
        self.assertEqual((self.f.project / 'research/discovery/PROBLEMS.json').read_bytes(), problem_before)
