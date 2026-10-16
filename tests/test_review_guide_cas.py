"""A stale R04 transaction must preserve a concurrent third guide version."""
from pathlib import Path
import unittest
from unittest import mock

import supervision_guide as guide
import test_supervision_guide as fixtures


class GuideStaleCASReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SupervisionGuideTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.project = self.fixture.root, self.fixture.project
        self.event = self.fixture.proposed()
        self.target = self.project / guide.ACTIVE
        self.third = b'Operator-authored third version: preserve these exact bytes.\n'
        self.protected = {p: (self.project / p).read_bytes() for p in ('GOAL.md', 'research/STATE.json')}
        self.route = self.fixture.route_path.read_bytes()

    def assert_third_preserved_and_pending(self):
        self.assertEqual(self.target.read_bytes(), self.third)
        self.assertFalse(guide._abort_path(self.root, self.project, self.event).exists())
        self.assertFalse(guide._receipt_path(self.root, self.project, self.event, 'APPLY').exists())
        self.assertEqual(guide._history(self.root, self.project)['pending'], [('APPLY', self.event)])
        for name, raw in self.protected.items(): self.assertEqual((self.project / name).read_bytes(), raw)
        self.assertEqual(self.fixture.route_path.read_bytes(), self.route)
        with self.assertRaisesRegex(ValueError, 'GUIDE_CONFLICT'):
            guide.recover(self.root, self.project, self.event)
        self.assertEqual(self.target.read_bytes(), self.third)

    def test_third_version_written_during_post_replace_freshness_is_preserved(self):
        original = guide._fresh; calls = 0
        def race(controller, project, record, **kwargs):
            nonlocal calls
            calls += 1
            # apply preflight, resume preflight, then post-replacement freshness.
            if calls == 3:
                self.target.write_bytes(self.third)
                self.fixture.put('proofs/argument.md', 'New operator source during final freshness check.')
            return original(controller, project, record, **kwargs)
        with mock.patch.object(guide, '_fresh', side_effect=race):
            with self.assertRaisesRegex(ValueError, 'GUIDE_CONFLICT'):
                guide.apply(self.root, self.project, self.event, expected_hash=guide.ABSENT)
        self.assertEqual(calls, 3)
        self.assert_third_preserved_and_pending()

    def test_third_version_written_during_recovery_freshness_is_preserved(self):
        with mock.patch.object(guide, '_commit_receipt', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                guide.apply(self.root, self.project, self.event, expected_hash=guide.ABSENT)
        original = guide._fresh
        def race(controller, project, record, **kwargs):
            self.target.write_bytes(self.third)
            self.fixture.put('proofs/argument.md', 'New source while recovering a prepared afterimage.')
            return original(controller, project, record, **kwargs)
        with mock.patch.object(guide, '_fresh', side_effect=race):
            with self.assertRaisesRegex(ValueError, 'GUIDE_CONFLICT'):
                guide.recover(self.root, self.project, self.event)
        self.assert_third_preserved_and_pending()

    def test_stale_afterimage_without_external_edit_still_restores_original_absence(self):
        original = guide._fresh; calls = 0
        def stale(controller, project, record, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 3:
                self.fixture.put('proofs/argument.md', 'New source invalidates only the transaction afterimage.')
            return original(controller, project, record, **kwargs)
        with mock.patch.object(guide, '_fresh', side_effect=stale):
            result = guide.apply(self.root, self.project, self.event, expected_hash=guide.ABSENT)
        self.assertEqual(result['status'], 'REJECTED_STALE')
        self.assertFalse(self.target.exists())
        self.assertEqual(guide._history(self.root, self.project)['pending'], [])
        for name, raw in self.protected.items(): self.assertEqual((self.project / name).read_bytes(), raw)
        self.assertEqual(self.fixture.route_path.read_bytes(), self.route)


if __name__ == '__main__':
    unittest.main()
