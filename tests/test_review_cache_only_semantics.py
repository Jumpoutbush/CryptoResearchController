"""N04: diagnostics, derived cache repair, and persistent observation differ."""
import unittest

import test_review_revocation as fixtures
from engine import claim_graph
from knowledge import build


class CacheOnlySemanticsTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ClaimRevocationReviewTests('test_cache_only_recovery_never_writes_canonical_revocation_or_other_authority')
        self.f.setUp()
        self.f.chain()
        build.build(self.f.root, self.f.project)

    def tearDown(self):
        self.f.doCleanups()

    def data_files(self):
        return {path: value for path, value in self.f.files(self.f.root).items()
                if not path.startswith('locks/')}

    def test_build_dry_run_and_cache_repair_preserve_distinct_authorities(self):
        source = self.f.project / 'proofs/source-A.md'
        original = source.read_bytes()
        source.write_bytes(original + b'\nchanged source')
        before = self.data_files()
        with self.assertRaisesRegex(ValueError, 'CANONICAL_REVOCATION_OBSERVATION_REQUIRED'):
            build.build(self.f.root, self.f.project)
        self.assertEqual(self.data_files(), before)
        preview = build.build(self.f.root, self.f.project, dry_run=True)
        self.assertTrue(preview['pending_revocations'])
        self.assertEqual(self.data_files(), before)
        repaired = build.build(self.f.root, self.f.project, cache_only=True)
        self.assertTrue(repaired['pending_revocations'])
        after = self.data_files()
        index = build.cache_path(self.f.root, self.f.project).relative_to(self.f.root).as_posix()
        changes = {name for name in before.keys() | after.keys() if before.get(name) != after.get(name)}
        self.assertEqual(changes, {index})
        self.assertTrue(all(row['proof_status'] == 'PENDING_REVALIDATION'
                            for row in claim_graph.status(self.f.project)['claims']))
        source.write_bytes(original)
        self.assertTrue(all(row['proof_status'] == 'INDEPENDENTLY_REVIEWED'
                            for row in claim_graph.status(self.f.project)['claims']))

    def test_explicit_refresh_after_cache_repair_persists_revocation(self):
        source = self.f.project / 'proofs/source-A.md'
        original = source.read_bytes()
        source.write_bytes(original + b'\nchanged source')
        build.build(self.f.root, self.f.project, cache_only=True)
        claim_graph.refresh(self.f.project)
        source.write_bytes(original)
        self.assertTrue(all(row['proof_status'] == 'PENDING_REVALIDATION'
                            for row in claim_graph.status(self.f.project)['claims']))
