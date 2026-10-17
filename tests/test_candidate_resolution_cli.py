"""Public branch resolution commands preserve project science and old budgets."""
import contextlib
import io
import json
import unittest

import research
import test_candidate_cli as fixtures


class CandidateResolutionCliTests(unittest.TestCase):
    def setUp(self):
        self.wrapper = fixtures.CandidateCliTests('test_three_cli_proposals_remain_unreviewed')
        self.wrapper.setUp()
        self.f = self.wrapper.f
        self.wrapper.propose()

    def tearDown(self):
        self.wrapper.tearDown()

    def invoke(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = research.main(['candidate', *args])
        raw = output.getvalue().strip()
        return code, json.loads(raw) if raw else errors.getvalue()

    def test_history_and_compare_are_readonly_without_resolutions(self):
        self.wrapper.propose('C-0002')
        before = self.f.files()
        self.assertEqual(self.invoke('history', 'example')[0], 0)
        self.assertEqual(self.invoke('compare', 'example', '--id', 'C-0001', '--id', 'C-0002')[0], 0)
        self.assertEqual(self.f.files(), before)

    def test_retire_without_claim_keeps_scientific_project_and_original_budget(self):
        before = self.f.files()
        code, result = self.invoke('retire', 'example', '--id', 'C-0001', '--expected-revision', '1',
            '--reason', 'Operator pauses this construction only', '--scope', 'Exact first toy construction',
            '--restart-conditions', 'New evidence and an independently reviewed assumption')
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'RETIRED')
        self.assertFalse(result['scientific_acceptance'])
        self.assertEqual(self.invoke('history', 'example', '--id', 'C-0001')[0], 0)
        after = self.f.files()
        protected = lambda files: {k:v for k,v in files.items()
            if not k.startswith(('state/candidates/', 'locks/'))}
        self.assertEqual(protected(before), protected(after))
        self.assertFalse((self.f.project / 'research/discovery/CLAIM_GRAPH.json').exists())

    def test_stop_blocks_switch_preparation_without_mutation(self):
        self.f.put('research/STATE.json', {
            **json.loads((self.f.project/'research/STATE.json').read_text(encoding='utf8')), 'decision':'STOP'})
        before = self.f.files()
        code, _ = self.invoke('switch-prepare', 'example', '--id', 'C-0001', '--expected-revision', '1',
            '--phase', 'START', '--reason', 'Must not resume stopped science')
        self.assertEqual(code, 2)
        self.assertEqual(self.f.files(), before)
