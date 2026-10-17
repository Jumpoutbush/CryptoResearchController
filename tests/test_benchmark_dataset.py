"""R16 public dataset calibration, never a model-quality claim."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from evaluation import cases, registry, schema, validate_cases


class BenchmarkDatasetTests(unittest.TestCase):
    def test_six_categories_have_pinned_public_tasks(self):
        items=cases.list_cases()['cases']
        self.assertEqual(len({item['category'] for item in items}),6)
        self.assertEqual(validate_cases.validate_dataset()['status'],'PENDING_CURATION')

    def test_public_views_and_bundles_exclude_private_indices_and_reference_labels(self):
        with tempfile.TemporaryDirectory(prefix='r16 public bundle ') as temp:
            base=Path(temp)
            for item in cases.list_cases()['cases']:
                view=cases.public_view(item['case_id']); schema.no_private_fields(view)
                result=cases.build_agent_bundle(item['case_id'],base/item['case_id'])
                self.assertFalse(result['formal_counted']); self.assertFalse(result['agent_execution_allowed'])
                for path in (base/item['case_id']).rglob('*'):
                    if path.is_file():
                        content=path.read_text(encoding='utf8')
                        self.assertNotIn('oracle',content.casefold()); self.assertNotIn('"expected"',content)

    def test_source_or_task_mutation_invalidates_old_public_pins(self):
        with tempfile.TemporaryDirectory(prefix='r16 mutable dataset ') as temp:
            base=Path(temp)/'dataset'; shutil.copytree(schema.root_path(),base)
            task=cases.public_view('BENCH-LIT-001',root=base)['task']; source=base/task['sources'][0]['file']; original=source.read_bytes()
            source.write_bytes(original+b' changed')
            with self.assertRaisesRegex(ValueError,'source changed'): cases.public_view('BENCH-LIT-001',root=base)
            source.write_bytes(original); path=base/'public/BENCH-LIT-001/v1/task.json'; changed=schema.read(path); changed['frozen_goal']+=' altered'
            path.write_bytes(schema.canonical_bytes(changed))
            with self.assertRaisesRegex(ValueError,'task changed'): cases.public_view('BENCH-LIT-001',root=base)

    def test_agent_bundle_preserves_the_exact_original_task_bytes(self):
        with tempfile.TemporaryDirectory(prefix='r16 exact public bytes ') as temp:
            base=Path(temp)/'dataset'; shutil.copytree(schema.root_path(),base)
            relative='public/BENCH-CE-001/v1/task.json'; path=base/relative
            raw=json.dumps(schema.read(path),separators=(',',':')).encode('utf8'); path.write_bytes(raw)
            manifest=schema.read(base/'manifest.json')
            next(row for row in manifest['cases'] if row['case_id']=='BENCH-CE-001')['task_sha256']=schema.sha_file(path)
            (base/'manifest.json').write_bytes(schema.canonical_bytes(manifest))
            destination=Path(temp)/'agent'; cases.build_agent_bundle('BENCH-CE-001',destination,root=base)
            self.assertEqual((destination/'task.json').read_bytes(),raw)

    def test_oracle_registration_cannot_use_the_public_workspace(self):
        from test_benchmark_cases import fixture_oracle
        task=cases.public_view('BENCH-CE-001')['task']
        with self.assertRaisesRegex(ValueError,'outside'):
            registry.register(schema.root_path()/'private',task['case_id'],fixture_oracle(task),reviewer='independent',
                reason='Independent temporary curation must never be written into the public workspace.')
