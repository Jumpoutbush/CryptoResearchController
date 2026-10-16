"""Protocol review CLI prepares evidence without granting scientific authority."""
import contextlib
import io
import json
import unittest

import research
import test_candidate_cli as fixtures
from candidate_search import security_model


class SecurityReviewCliTests(unittest.TestCase):
    def setUp(self):
        self.wrapper = fixtures.CandidateCliTests('test_three_cli_proposals_remain_unreviewed')
        self.wrapper.setUp()
        self.f = self.wrapper.f
        self.f.claim('LEMMA-1')
        self.wrapper.propose()
        self.card = security_model.template()
        self.card['proof_paths'] = ['proofs/derivation.md']
        self.card_file = self.f.root / 'security-card.json'
        self.card_file.write_text(json.dumps(self.card), encoding='utf8')

    def tearDown(self):
        self.wrapper.tearDown()

    def invoke(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = research.main(['candidate', *args])
        raw = output.getvalue().strip()
        return code, json.loads(raw) if raw else errors.getvalue()

    def prepare(self):
        return self.invoke('security-prepare', 'example', '--id', 'C-0001', '--claim', 'LEMMA-1',
                           '--card', str(self.card_file))

    def test_prepare_is_read_only_and_deterministic(self):
        before = self.f.files()
        code, request = self.prepare()
        self.assertEqual(code, 0)
        self.assertEqual(self.prepare(), (code, request))
        self.assertEqual(self.f.files(), before)

    def test_missing_frozen_model_is_structured_needs_input_and_not_acceptance(self):
        code, request = self.prepare()
        self.assertEqual(code, 0)
        original = self.f.files()
        request_file = self.f.root / 'security-request.json'
        request_file.write_text(json.dumps(request), encoding='utf8')
        code, report = self.invoke('security-review', 'example', '--request', str(request_file))
        self.assertEqual(code, 2)
        self.assertEqual(report['decision'], 'NEEDS_INPUT')
        self.assertEqual(report['finding_level'], 'REVIEW_FINDING')
        self.assertFalse(report['claim_status_changed'])
        self.assertFalse(report['scientific_acceptance'])
        rid = request['request_id']
        self.assertEqual(self.invoke('security-show', 'example', '--request-id', rid)[0], 0)
        self.assertEqual(self.invoke('security-recheck', 'example', '--request-id', rid)[0], 2)
        for path, data in original.items():
            if not path.startswith('locks/'):
                self.assertEqual((self.f.root / path).read_bytes(), data, path)
        self.assertFalse((self.f.root / 'state/discovery/example.json').exists())

    def test_authority_field_is_rejected_before_creating_a_report(self):
        self.card['accepted_contribution'] = True
        self.card_file.write_text(json.dumps(self.card), encoding='utf8')
        before = self.f.files()
        code, _ = self.prepare()
        self.assertEqual(code, 2)
        self.assertEqual(self.f.files(), before)
