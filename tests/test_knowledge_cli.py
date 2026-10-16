"""Offline knowledge CLI checks: read-only views and locked, scoped mutations."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import configuration
import research
from engine import knowledge_graph
from route_budget import file_lock


SOURCE = Path(__file__).resolve().parents[1]


class KnowledgeCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='knowledge cli space ')
        self.root = Path(self.temp.name)
        shutil.copytree(SOURCE / 'config', self.root / 'config')
        self.project = self.root / 'projects/example'
        self.project.mkdir(parents=True)
        self.put('PROJECT.json', {'id': 'example', 'title': 'Example', 'checks': []})
        self.put('GOAL.md', 'Keep the original security requirements and target.')
        self.put('AGENTS.md', 'Preserve the scientific scope.')
        self.put('research/STATE.json', {'phase': 'PROOF', 'decision': 'CONTINUE',
            'last_run': 'accepted-before-upgrade', 'research_route': 'C',
            'priority_problem': 'Original question', 'next_task': 'Prove the missing lemma.'})
        self.put('research/notes.md', 'Original evidence.\nAssumptions remain explicit.\n')
        self.budget = self.root / 'state/routes/example.json'
        self.budget.parent.mkdir(parents=True)
        self.budget.write_bytes(b'{"epochs":[{"used_rounds":7}]}')
        self.spec = {'schema_version': 1, 'id': 'E-1', 'kind': 'evidence',
            'title': 'Original evidence', 'statement': 'Two recorded lines with bounded scope.',
            'sources': [{'path': 'research/notes.md', 'locator': 'lines:1-2'}],
            'dependencies': [], 'claim_ids': []}
        self.spec_path = self.root / 'record.json'
        self.spec_path.write_text(json.dumps(self.spec), encoding='utf8')
        self.patches = [patch.object(configuration, 'ROOT', self.root),
                        patch.object(research, 'ROOT', self.root)]
        for item in self.patches: item.start()

    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    def put(self, relative, obj):
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj) if isinstance(obj, dict) else obj, encoding='utf8')
        return path

    def cli(self, *args):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            code = research.main(['knowledge', *args])
        return code, stream.getvalue()

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def import_fixture(self):
        code, output = self.cli('import', 'example', '--file', str(self.spec_path),
                                '--reason', 'Register exact local evidence')
        self.assertEqual(code, 0, output)

    def test_readonly_views_create_no_graph_ledger_or_locks(self):
        before = self.snapshot()
        for args in [('status', 'example'), ('status', 'all'),
                     ('search', 'all', '--query', 'evidence')]:
            code, output = self.cli(*args)
            self.assertEqual(code, 0, output)
        self.assertEqual(self.snapshot(), before)

    def test_import_trace_and_invalidation_preserve_state_and_budget_without_model(self):
        state = (self.project / 'research/STATE.json').read_bytes()
        budget = self.budget.read_bytes()
        with patch.object(research, 'run_child') as run:
            self.import_fixture()
            for args in [('show', 'example', '--id', 'memory:E-1'),
                         ('trace', 'example', '--id', 'E-1'),
                         ('impact', 'example', '--id', 'E-1'),
                         ('search', 'example', '--query', 'evidence', '--kind', 'evidence')]:
                code, output = self.cli(*args)
                self.assertEqual(code, 0, output)
                self.assertIn('E-1', output)
            code, output = self.cli('invalidate', 'example', '--id', 'E-1', '--reason', 'Source retracted')
            self.assertEqual(code, 0, output)
            run.assert_not_called()
        self.assertEqual((self.project / 'research/STATE.json').read_bytes(), state)
        self.assertEqual(self.budget.read_bytes(), budget)

    def test_mutations_respect_both_existing_locks(self):
        locks = [research.project_lock(self.project), file_lock(self.root / 'locks/example.lock')]
        for lock in locks:
            with lock:
                code, output = self.cli('import', 'example', '--file', str(self.spec_path), '--reason', 'Locked')
                self.assertEqual(code, 2, output)
                self.assertEqual(self.cli('status', 'example')[0], 0)
        self.assertFalse((self.project / 'research/discovery/CLAIM_GRAPH.json').exists())

    def test_invalid_source_import_keeps_current_graph_bytes(self):
        self.import_fixture()
        graph = self.project / 'research/discovery/CLAIM_GRAPH.json'
        original = graph.read_bytes()
        self.spec['sources'][0]['path'] = '../outside.md'
        self.spec_path.write_text(json.dumps(self.spec), encoding='utf8')
        code, output = self.cli('import', 'example', '--file', str(self.spec_path), '--reason', 'Invalid source')
        self.assertEqual(code, 2, output)
        self.assertEqual(graph.read_bytes(), original)

    def test_project_inference_and_historical_revision_are_readonly(self):
        self.import_fixture()
        before = self.snapshot()
        nested = self.project / 'research'
        with patch.object(Path, 'cwd', return_value=nested):
            code, output = self.cli('show', '--id', 'E-1', '--revision', '1')
        self.assertEqual(code, 0, output)
        self.assertIn('E-1', output)
        self.assertEqual(self.snapshot(), before)

    def test_search_history_and_trace_keep_pinned_statement_without_writes(self):
        self.spec['statement'] = 'Old exact upstream lemma for historical retrieval.'
        self.spec_path.write_text(json.dumps(self.spec), encoding='utf8')
        self.import_fixture()
        downstream = {**self.spec, 'id': 'E-2', 'title': 'Downstream statement',
                      'statement': 'Uses the original upstream lemma.', 'dependencies': ['E-1']}
        downstream_file = self.root / 'downstream.json'
        downstream_file.write_text(json.dumps(downstream), encoding='utf8')
        code, output = self.cli('import', 'example', '--file', str(downstream_file),
                                '--reason', 'Pin the exact upstream revision')
        self.assertEqual(code, 0, output)
        self.spec['statement'] = 'Revised current upstream lemma with a different scope.'
        self.spec_path.write_text(json.dumps(self.spec), encoding='utf8')
        self.import_fixture()
        before = self.snapshot()
        code, output = self.cli('trace', 'example', '--id', 'E-2')
        self.assertEqual(code, 0, output)
        trace = json.loads(output)['knowledge']
        frozen = next(n for n in trace['frozen_nodes'] if n['id'] == 'E-1')
        self.assertEqual(frozen['revision'], 1)
        self.assertIn('Old exact upstream lemma', frozen['statement'])
        self.assertEqual(trace['unresolved_pins'], [])
        code, output = self.cli('search', 'example', '--query', 'Old exact upstream lemma', '--kind', 'evidence')
        self.assertEqual(code, 0, output)
        result = json.loads(output)['knowledge']
        self.assertTrue(any(n['key'] == 'memory:E-1@r1' and n['historical'] for n in result['matches']))
        self.assertEqual(self.snapshot(), before)

    def test_bulk_mutation_is_rejected_before_writes(self):
        before = self.snapshot()
        for action in ('refresh', 'invalidate'):
            args = [action, 'all']
            if action == 'invalidate': args += ['--id', 'E-1', '--reason', 'No bulk changes']
            code, output = self.cli(*args)
            self.assertEqual(code, 2, output)
        self.assertEqual(self.snapshot(), before)

    def test_new_projects_inherit_knowledge_guidance_without_active_graph(self):
        shutil.copytree(SOURCE / 'templates', self.root / 'templates')
        goal = self.root / 'goal.md'
        goal.write_text('Keep a precise research target.', encoding='utf8')
        with contextlib.redirect_stdout(io.StringIO()):
            code = research.main(['new', 'second', '--goal-file', str(goal)])
        self.assertEqual(code, 0)
        project = self.root / 'projects/second'
        template = configuration.load_json(project / 'research/KNOWLEDGE_TEMPLATE.json')
        self.assertEqual(template['kind'], 'evidence')
        self.assertIn('CLAIM_GRAPH.json', (project / 'AGENTS.md').read_text(encoding='utf8'))
        self.assertFalse((project / 'research/discovery/CLAIM_GRAPH.json').exists())
        self.assertEqual(configuration.load_json(project / 'research/STATE.json')['decision'], 'PAUSE')


if __name__ == '__main__':
    unittest.main()
