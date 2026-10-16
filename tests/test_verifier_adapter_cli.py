"""Candidate verifier CLI returns scoped results without scientific promotion."""
import contextlib
import io
import json
import unittest

import research
import test_candidate_cli as fixtures
from engine import claim_graph


class VerifierAdapterCliTests(unittest.TestCase):
    def setUp(self):
        self.wrapper = fixtures.CandidateCliTests('test_three_cli_proposals_remain_unreviewed')
        self.wrapper.setUp()
        self.f = self.wrapper.f
        self.f.claim('LEMMA-1', machine_statement={'domain': 'INTEGER', 'variables': ['x'],
                     'preconditions': [], 'conclusion': 'x*x == x'})
        item = claim_graph.get(self.f.project, 'LEMMA-1')
        self.wrapper.propose(dependency_claims=[{'id': item['id'], 'revision': item['revision'],
                                                'spec_sha256': item['spec_sha256']}])

    def tearDown(self):
        self.wrapper.tearDown()

    def invoke(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = research.main(['candidate', *args])
        raw = output.getvalue().strip()
        return code, json.loads(raw) if raw else errors.getvalue()

    def prepare(self, adapter='integer-v1'):
        return self.invoke('verify-prepare', 'example', '--id', 'C-0001', '--claim', 'LEMMA-1',
                           '--adapter', adapter, '--bounds', '-3', '3')

    def test_preparation_is_deterministic_and_does_not_dispatch(self):
        before = self.f.files()
        code, request = self.prepare()
        self.assertEqual(code, 0)
        self.assertEqual(self.prepare(), (code, request))
        self.assertEqual(self.f.files(), before)

    def test_exact_witness_show_and_recheck_keep_canonical_bytes(self):
        code, request = self.prepare()
        self.assertEqual(code, 0)
        before = {name: (self.f.project / name).read_bytes() for name in
                  ('research/discovery/CLAIM_GRAPH.json', 'research/discovery/PROBLEMS.json', 'research/STATE.json')}
        path = self.f.root / 'verification.json'
        path.write_text(json.dumps(request), encoding='utf8')
        code, receipt = self.invoke('verify', 'example', '--request', str(path))
        self.assertEqual(code, 0)
        self.assertEqual(receipt['result_status'], 'COUNTEREXAMPLE_FOUND')
        rid = request['request_id']
        self.assertEqual(self.invoke('verification-show', 'example', '--request-id', rid)[0], 0)
        self.assertEqual(self.invoke('verification-recheck', 'example', '--request-id', rid)[0], 0)
        for name, data in before.items():
            self.assertEqual((self.f.project / name).read_bytes(), data)
        self.assertFalse((self.f.root / 'state/discovery/example.json').exists())

    def test_unknown_adapter_returns_unsupported_json_and_nonzero(self):
        code, request = self.prepare('unknown-v1')
        self.assertEqual(code, 0)
        path = self.f.root / 'unknown-verification.json'
        path.write_text(json.dumps(request), encoding='utf8')
        code, receipt = self.invoke('verify', 'example', '--request', str(path))
        self.assertEqual(code, 2)
        self.assertEqual(receipt['result_status'], 'UNSUPPORTED')
