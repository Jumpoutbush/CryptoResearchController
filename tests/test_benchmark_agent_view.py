"""R16 public data boundary; bundle filtering never certifies OS isolation."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import research


class BenchmarkAgentViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='r16 public view ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.secret = 'UNIQUE_HOST_ONLY_ORACLE_SENTINEL_49e57a8f'
        private = self.root / 'private/oracle.json'
        private.parent.mkdir()
        private.write_text(json.dumps({'answer': self.secret}), encoding='utf8')

    def invoke(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = research.main(['benchmark', *args])
        return code, json.loads(output.getvalue()) if output.getvalue().strip() else errors.getvalue()

    def rows(self):
        from evaluation import cases
        result = cases.list_cases()
        return result['cases'] if isinstance(result, dict) else result

    def assert_public(self, value):
        forbidden = {'oracle_path', 'oracle_sha256', 'oracle', 'expected', 'reference_rationale',
                     'reference_answer', 'correct_answer', 'private_root'}
        def visit(item):
            if isinstance(item, dict):
                self.assertFalse(forbidden & set(item))
                for child in item.values(): visit(child)
            elif isinstance(item, list):
                for child in item: visit(child)
        visit(value)
        rendered = json.dumps(value, ensure_ascii=False)
        self.assertNotIn(self.secret, rendered)
        self.assertNotIn(str(self.root / 'private'), rendered)

    def test_six_categories_public_views_exclude_reference_answers(self):
        from evaluation import cases
        rows = self.rows()
        self.assertEqual(len({row['category'] for row in rows}), 6)
        for row in rows:
            with self.subTest(case=row['case_id']):
                self.assert_public(cases.public_view(row['case_id']))
                code, view = self.invoke('show', '--case', row['case_id'])
                self.assertEqual(code, 0)
                self.assert_public(view)

    def test_exported_bundle_contains_only_public_files_and_no_sibling_oracle(self):
        from evaluation import cases
        cid = self.rows()[0]['case_id']
        target = self.root / 'agent'
        cases.build_agent_bundle(cid, target)
        files = [p for p in target.rglob('*') if p.is_file()]
        self.assertTrue(files)
        for file in files:
            self.assertNotIn(self.secret.encode(), file.read_bytes())
            self.assertNotEqual(file.name, 'oracle.json')
            if file.suffix == '.json': self.assert_public(json.loads(file.read_text(encoding='utf8')))
        with self.assertRaises(ValueError): cases.build_agent_bundle(cid, target)

    def test_absent_oracle_fails_scoring_without_creating_private_state(self):
        cid = self.rows()[0]['case_id']
        response = self.root / 'response.json'
        response.write_text('{}', encoding='utf8')
        missing = self.root / 'missing-private'
        code, result = self.invoke('score-fixture', '--case', cid, '--response', str(response),
                                   '--private-root', str(missing))
        self.assertEqual(code, 2)
        self.assertEqual(result['status'], 'STALE_OR_INVALID')
        self.assertFalse(missing.exists())

    def test_isolation_status_cannot_claim_a_certified_agent_or_formal_result(self):
        code, result = self.invoke('isolation-status')
        self.assertEqual(code, 0)
        self.assertEqual(result['isolation_status'], 'NOT_ISOLATED')
        self.assertFalse(result['formal_counted'])
        self.assertFalse(result['agent_execution_allowed'])
