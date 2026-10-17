"""Explicit authority migration CLI must preserve legacy attempts and bytes."""
import contextlib
import hashlib
import io
import json
import unittest

import configuration
import research
import test_discovery as fixtures
from engine import discovery_scheduler
from engine.common import ledger, ledger_path


class DiscoveryAuthorityCliTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.DiscoveryTests('test_problem_revisions_do_not_silently_replace_active_statement')
        self.f.setUp()
        plan = discovery_scheduler.prepare_start(self.f.project, 'P-1', version=1)
        configuration.atomic_json(ledger_path(self.f.project), plan['after_ledger'])
        configuration.atomic_json(self.f.project / 'research/STATE.json', plan['after_state'])

    def tearDown(self):
        self.f.tearDown()

    def invoke(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = research.main(['attempt', *args])
        return code, json.loads(output.getvalue()) if code == 0 else errors.getvalue()

    def files(self):
        return {p.relative_to(self.f.root).as_posix(): p.read_bytes()
                for p in self.f.root.rglob('*') if p.is_file() and 'locks' not in p.relative_to(self.f.root).parts}

    def test_legacy_status_is_readonly_and_enrollment_preserves_the_exact_original_owner(self):
        before = self.files()
        raw = ledger_path(self.f.project).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        code, status = self.invoke('authority-status', 'example')
        self.assertEqual(code, 0)
        self.assertEqual(status['actual_ledger_sha256'], digest)
        self.assertEqual(self.files(), before)
        code, _ = self.invoke('authority-enroll', 'example', '--reason', 'Explicitly retain all original owner consumption',
            '--expected-ledger-sha256', digest)
        self.assertEqual(code, 0)
        self.assertEqual(ledger_path(self.f.project).read_bytes(), raw)
        self.assertEqual(ledger(self.f.project)['active_attempt'], 'attempt-0001')
        self.assertEqual(len(ledger(self.f.project)['attempts']), 1)
        self.assertEqual(before, {p: value for p, value in self.files().items() if p in before})

    def test_wrong_legacy_sha_cannot_enroll_or_rewrite_any_history(self):
        before = self.files()
        code, _ = self.invoke('authority-enroll', 'example', '--reason', 'Explicit migration must bind exact reviewed bytes',
            '--expected-ledger-sha256', '0' * 64)
        self.assertEqual(code, 2)
        self.assertEqual(self.files(), before)
