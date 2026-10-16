"""Public CLI candidate registration without any research dispatch."""
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest import mock

import research
import test_candidate_contract as fixtures


class CandidateCliTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.CandidateContractTests('test_same_title_different_hypothesis_is_not_deduplicated')
        self.f.setUp()

    def tearDown(self):
        self.f.tearDown()

    def invoke(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            result = research.main(['candidate', *args])
        return result, json.loads(output.getvalue()) if result == 0 else errors.getvalue()

    def propose(self, cid='C-0001', **updates):
        file = self.f.root / 'proposal.json'
        file.write_text(json.dumps(self.f.make(cid, **updates)), encoding='utf8')
        return self.invoke('propose', 'example', '--file', str(file), '--reason', 'Register isolated CLI fixture')

    def test_anchor_and_empty_list_do_not_create_catalog_or_budget(self):
        before = self.f.files()
        self.assertEqual(self.invoke('anchor', 'example')[0], 0)
        self.assertEqual(self.invoke('list', 'example')[1]['candidates'], [])
        self.assertEqual(self.f.files(), before)

    def test_three_cli_proposals_remain_unreviewed(self):
        for cid in ('C-0001', 'C-0002', 'C-0003'):
            code, item = self.propose(cid)
            self.assertEqual(code, 0)
            self.assertEqual(item['status'], 'PROPOSED')
            self.assertFalse(item['positive_basis'])
        self.assertEqual(len(self.invoke('list', 'example')[1]['candidates']), 3)

    def test_revision_conflict_preserves_old_spec_and_event_count(self):
        _, old = self.propose()
        file = self.f.root / 'revision.json'
        changed = dict(old['spec'], hypothesis='An explicitly different exact construction')
        file.write_text(json.dumps(changed), encoding='utf8')
        args = ['revise', 'example', '--file', str(file), '--reason', 'Explicit new construction', '--expected-revision']
        self.assertEqual(self.invoke(*args, '99')[0], 2)
        self.assertEqual(self.invoke('list', 'example')[1]['event_count'], 1)
        self.assertEqual(self.invoke(*args, '1')[1]['revision'], 2)
        self.assertEqual(self.invoke('show', 'example', '--id', 'C-0001', '--revision', '1')[1]['spec'], old['spec'])

    def test_status_uses_expected_revision_and_never_starts_attempt(self):
        self.propose()
        args = ['status', 'example', '--id', 'C-0001', '--status', 'READY_FOR_ATTEMPT',
                '--reason', 'Ready for explicit future scheduling', '--expected-revision']
        self.assertEqual(self.invoke(*args, '9')[0], 2)
        self.assertTrue(self.invoke(*args, '1')[1]['eligible_for_attempt'])
        self.assertFalse((self.f.root / 'state/discovery/example.json').exists())

    def test_unknown_and_traversal_ids_fail_without_new_history(self):
        self.propose()
        self.assertEqual(self.invoke('show', 'example', '--id', '../other')[0], 2)
        self.assertEqual(self.invoke('show', 'example', '--id', 'MISSING')[0], 2)
        self.assertEqual(self.invoke('list', 'example')[1]['event_count'], 1)

    def test_project_directory_inference_uses_existing_resolver(self):
        self.propose()
        with mock.patch.object(Path, 'cwd', return_value=self.f.project):
            code, item = self.invoke('show', '--id', 'C-0001')
        self.assertEqual(code, 0)
        self.assertEqual(item['project_id'], 'example')

    def test_active_is_not_a_manual_status_option(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            research.main(['candidate', 'status', 'example', '--id', 'C-0001', '--status', 'ACTIVE',
                           '--reason', 'Cannot bypass original attempt', '--expected-revision', '1'])
        self.assertEqual(error.exception.code, 2)
