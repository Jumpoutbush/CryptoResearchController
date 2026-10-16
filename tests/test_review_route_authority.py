"""F04: missing or rolled-back route authority cannot mint a fresh budget."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

import research
import route_budget as routes
import test_runner as fixtures


class RouteAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RunnerTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root, self.project = self.fixture.root, self.fixture.project
        patcher = mock.patch.object(research, 'ROOT', self.root)
        patcher.start(); self.addCleanup(patcher.stop)
        self.path, self.ledger, self.epoch = routes.load_ledger(self.root, self.project, self.fixture.current())
        self.registry = self.root / 'state/route_registry/subject.json'

    def protected(self):
        return {p.relative_to(self.project).as_posix(): p.read_bytes()
                for p in self.project.rglob('*') if p.is_file()}

    def save(self, used=3):
        self.epoch.update(effective_rounds=used, counted_run_ids=['r' + str(i + 1) for i in range(used)])
        routes.save_ledger(self.path, self.ledger)

    def load(self):
        return routes.load_ledger(self.root, self.project, self.fixture.current())

    def cli(self, argv):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return research.main(argv)

    def test_registered_missing_ledger_stops_and_does_not_write_project(self):
        self.save(6); before = self.protected(); self.path.unlink()
        with self.assertRaisesRegex(ValueError, 'authority|registered|ledger'):
            self.load()
        self.assertFalse(self.path.exists())
        self.assertEqual(self.protected(), before)

    def test_registered_empty_and_old_ledger_are_rejected(self):
        self.save(2); old = self.path.read_bytes()
        self.save(6); latest = self.path.read_bytes()
        for content in (b'{}', b'{"schema_version":1,"project_id":"subject","epochs":[],"events":[]}', old):
            with self.subTest(content=content[:40]):
                self.path.write_bytes(content)
                with self.assertRaises(ValueError): self.load()
        self.path.write_bytes(latest)
        self.assertEqual(self.load()[2]['effective_rounds'], 6)

    def test_registration_marker_missing_on_either_side_is_rejected(self):
        self.save(); original = self.registry.read_bytes()
        self.registry.unlink()
        with self.assertRaisesRegex(ValueError, 'registration|registry|witness'): self.load()
        self.registry.write_bytes(original)
        data = json.loads(self.path.read_text(encoding='utf8')); data.pop('budget_registration_id')
        routes.atom_json(self.path, data)
        with self.assertRaises(ValueError): self.load()

    def test_new_project_inspection_is_read_only_and_legacy_complete_budget_is_preserved(self):
        before = sorted(str(p) for p in self.root.rglob('*'))
        self.load()
        self.assertEqual(before, sorted(str(p) for p in self.root.rglob('*')))
        legacy = copy.deepcopy(self.ledger)
        legacy['epochs'][0]['effective_rounds'] = 4
        legacy['epochs'][0]['counted_run_ids'] = ['r1', 'r2', 'r3', 'r4']
        legacy.pop('budget_registration_id', None)
        routes.atom_json(self.path, legacy)
        raw = self.path.read_bytes()
        path, ledger, epoch = self.load()
        self.assertEqual(epoch['effective_rounds'], 4)
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertFalse(self.registry.exists())
        routes.save_ledger(path, ledger)
        self.assertTrue(self.registry.is_file())
        self.assertEqual(self.load()[2]['counted_run_ids'], ['r1', 'r2', 'r3', 'r4'])

    def test_existing_history_requires_explicit_baseline_and_cli_does_not_clear_counts(self):
        state = self.fixture.current(); state['last_run'] = 'r3'
        routes.atom_json(self.project / 'research/STATE.json', state)
        before = self.protected()
        with self.assertRaisesRegex(ValueError, 'baseline|history|registration'): self.load()
        self.assertFalse(self.path.exists())
        baseline = copy.deepcopy(self.ledger)
        baseline['epochs'][0].update(effective_rounds=3, counted_run_ids=['r1', 'r2', 'r3'], last_processed_run='r3')
        source = self.root / 'operator-baseline.json'; routes.atom_json(source, baseline)
        code = self.cli(['budget', 'subject', '--register-baseline', str(source),
                         '--reason', 'Explicit operator-confirmed historical consumption'])
        self.assertEqual(code, 0)
        self.assertEqual(self.load()[2]['effective_rounds'], 3)
        self.assertEqual(self.protected(), before)
        with self.assertRaises(ValueError):
            routes.register_baseline(self.root, self.project, baseline, 'Cannot reset existing authority')

    def test_pending_before_ledger_write_is_recovered_once_without_recount(self):
        self.save(2); before = self.path.read_bytes()
        self.epoch.update(effective_rounds=3, counted_run_ids=['r1', 'r2', 'r3'])
        original = routes.atom_json
        def interrupted(path, data):
            if Path(path) == self.path: raise OSError('simulated ledger replace failure')
            return original(path, data)
        with mock.patch.object(routes, 'atom_json', side_effect=interrupted):
            with self.assertRaises(OSError): routes.save_ledger(self.path, self.ledger)
        self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaisesRegex(ValueError, 'pending|recover'): self.load()
        routes.recover_ledger(self.path)
        recovered = (self.path.read_bytes(), self.registry.read_bytes())
        routes.recover_ledger(self.path)
        self.assertEqual((self.path.read_bytes(), self.registry.read_bytes()), recovered)
        self.assertEqual(self.load()[2]['effective_rounds'], 3)

    def test_pending_after_ledger_write_requires_same_afterimage(self):
        self.save(2); self.epoch.update(effective_rounds=3, counted_run_ids=['r1', 'r2', 'r3'])
        original = routes.atom_json
        def interrupted(path, data):
            if Path(path) == self.registry and data.get('pending') is None:
                raise OSError('simulated witness completion failure')
            return original(path, data)
        with mock.patch.object(routes, 'atom_json', side_effect=interrupted):
            with self.assertRaises(OSError): routes.save_ledger(self.path, self.ledger)
        with self.assertRaisesRegex(ValueError, 'pending|recover'): self.load()
        other = copy.deepcopy(self.ledger); other['epochs'][0]['effective_rounds'] = 4
        with self.assertRaisesRegex(ValueError, 'pending|afterimage'): routes.save_ledger(self.path, other)
        routes.save_ledger(self.path, self.ledger)
        self.assertEqual(self.load()[2]['effective_rounds'], 3)

    def test_stale_in_memory_afterimage_cannot_overwrite_newer_consumption(self):
        self.save(2); old = copy.deepcopy(self.ledger)
        self.save(6)
        before = (self.path.read_bytes(), self.registry.read_bytes())
        with self.assertRaisesRegex(ValueError, 'roll back|discard'):
            routes.save_ledger(self.path, old)
        self.assertEqual((self.path.read_bytes(), self.registry.read_bytes()), before)

    def test_first_registration_interruption_is_recovered_without_zero_reset(self):
        self.epoch.update(effective_rounds=4, counted_run_ids=['r1', 'r2', 'r3', 'r4'])
        original = routes.atom_json
        def interrupted(path, data):
            if Path(path) == self.path: raise OSError('first ledger replace failure')
            return original(path, data)
        with mock.patch.object(routes, 'atom_json', side_effect=interrupted):
            with self.assertRaises(OSError): routes.save_ledger(self.path, self.ledger)
        self.assertFalse(self.path.exists())
        with self.assertRaises(ValueError): self.load()
        before = self.protected()
        code = self.cli(['budget', 'subject', '--recover-ledger',
            '--reason', 'Complete exact first registration after local crash'])
        self.assertEqual(code, 0)
        self.assertEqual(self.load()[2]['effective_rounds'], 4)
        self.assertEqual(self.protected(), before)
        self.assertEqual(json.loads(self.registry.read_text(encoding='utf8'))['recoveries'][-1]['kind'],
                         'PREPARED_LOCAL_AFTERIMAGE')

    def test_malformed_witness_cannot_be_interpreted_as_a_legacy_budget(self):
        self.save(4); witness = json.loads(self.registry.read_text(encoding='utf8'))
        witness.pop('pending')
        routes.atom_json(self.registry, witness)
        before = (self.path.read_bytes(), self.registry.read_bytes())
        with self.assertRaises(ValueError): self.load()
        self.assertEqual((self.path.read_bytes(), self.registry.read_bytes()), before)

    def test_restore_requires_latest_witness_hash_not_old_backup(self):
        self.save(2); old = self.root / 'old-backup.json'; old.write_bytes(self.path.read_bytes())
        self.save(6); backup = self.root / 'latest-backup.json'; backup.write_bytes(self.path.read_bytes())
        before = self.protected(); self.path.unlink()
        with self.assertRaisesRegex(ValueError, 'hash|SHA|latest|witness'):
            routes.restore_registered_ledger(self.root, self.project, old, 'Reject stale backup rollback')
        self.assertFalse(self.path.exists())
        code = self.cli(['budget', 'subject', '--restore-ledger', str(backup),
                         '--reason', 'Restore exact witnessed latest ledger backup'])
        self.assertEqual(code, 0)
        self.assertEqual(self.load()[2]['effective_rounds'], 6)
        self.assertEqual(self.path.read_bytes(), backup.read_bytes())
        self.assertEqual(self.protected(), before)

    def test_hard_exit_between_ledger_and_witness_completion_recovers_exact_afterimage(self):
        self.save(2)
        payload = self.root / 'afterimage.json'
        target = copy.deepcopy(self.ledger)
        target['epochs'][0].update(effective_rounds=3, counted_run_ids=['r1', 'r2', 'r3'])
        routes.atom_json(payload, target)
        code = """import json,os,sys
from pathlib import Path
import route_budget as r
path=Path(sys.argv[1]); target=json.loads(Path(sys.argv[2]).read_text(encoding='utf8'))
original=r.atom_json
def interrupted(dest,data):
    original(dest,data)
    if Path(dest)==path: os._exit(73)
r.atom_json=interrupted
r.save_ledger(path,target)
"""
        child = subprocess.run([sys.executable, '-B', '-c', code, str(self.path), str(payload)],
            cwd=fixtures.SOURCE, capture_output=True, timeout=30)
        self.assertEqual(child.returncode, 73, child.stderr.decode(errors='replace'))
        with self.assertRaisesRegex(ValueError, 'pending|recover'): self.load()
        routes.recover_ledger(self.path)
        self.assertEqual(self.load()[2]['effective_rounds'], 3)
        self.assertEqual(self.load()[2]['counted_run_ids'], ['r1', 'r2', 'r3'])

    def test_refocus_late_failure_restores_both_ledger_and_registration(self):
        self.save(2)
        before = (self.path.read_bytes(), self.registry.read_bytes(), self.protected())
        original = routes.save_ledger
        def interrupted(path, data):
            original(path, data)
            raise OSError('failure after witness completion')
        with mock.patch.object(routes, 'save_ledger', side_effect=interrupted):
            code = self.cli(['refocus', 'subject', '--task',
                'Resolve the exact frozen obligation with an independently testable proof step.',
                '--reason', 'Operator-directed refocus regression fixture'])
        self.assertEqual(code, 2)
        self.assertEqual((self.path.read_bytes(), self.registry.read_bytes(), self.protected()), before)
        self.assertEqual(self.load()[2]['effective_rounds'], 2)


if __name__ == '__main__':
    unittest.main()
