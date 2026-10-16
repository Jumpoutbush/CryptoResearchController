"""The updater must never overwrite personal projects, parameters or .git."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/apply_update.py'
spec=importlib.util.spec_from_file_location('framework_update',SCRIPT)
updater=importlib.util.module_from_spec(spec);spec.loader.exec_module(updater)

class FrameworkUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        self.bundle=root/'Bundle';self.target=root/'Target Space'
        (self.bundle/'payload').mkdir(parents=True);self.target.mkdir()
        self.put(self.target/'runner.py',b'# old runner\n');self.put(self.target/'research.py',b'# old front\n')
        self.private={
            'projects/private/research/STATE.json':b'{"phase":"PROOF","last_run":"keep"}',
            'projects/private/PROJECT.json':b'{"id":"private"}',
            'config/projects/private.json':b'{"route_policy":{"initial_round_budget":11}}',
            'config/defaults.json':b'{"custom":"models remain untouched"}',
            'state/routes/private.json':b'private budget',
            '.git/config':b'private remote and repository metadata',
        }
        for p,data in self.private.items():self.put(self.target/p,data)
    def tearDown(self):self.tmp.cleanup()
    def put(self,p,data):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    def manifest(self,items):
        files=[]
        for path,data,action in items:
            self.put(self.bundle/'payload'/path,data)
            files.append({'path':path,'sha256':updater.digest(data),'action':action})
        (self.bundle/'UPDATE_MANIFEST.json').write_text(json.dumps({'schema_version':1,'files':files}),encoding='utf8')
    def preserved(self):
        for rel,data in self.private.items():self.assertEqual((self.target/rel).read_bytes(),data,rel)
    def test_framework_apply_preserves_personal_bytes_and_custom_ignore(self):
        self.put(self.target/'.gitignore',b'# my rules\n/my-other-data/\n')
        self.manifest([('runner.py',b'# new runner\n','replace'),('.gitignore',b'# source defaults\n','merge_ignore'),('config/research_policy.json',b'{"theory_first":true}','preserve_existing')])
        backup=updater.apply(self.bundle,self.target,perform=True,verify=False)
        self.preserved();self.assertEqual((self.target/'runner.py').read_bytes(),b'# new runner\n')
        ignore=(self.target/'.gitignore').read_text();self.assertIn('/my-other-data/',ignore);self.assertIn('/projects/',ignore)
        self.assertTrue((backup/'before/runner.py').is_file())
        updater.rollback(self.target,backup)
        self.preserved();self.assertEqual((self.target/'runner.py').read_bytes(),b'# old runner\n')
        self.assertEqual((self.target/'.gitignore').read_bytes(),b'# my rules\n/my-other-data/\n')
    def test_private_path_payload_is_rejected_before_writes(self):
        for path in ('projects/private/GOAL.md','config/projects/private.json','state/routes/private.json','.git/config','config/defaults.json'):
            self.manifest([(path,b'bad replacement','replace')])
            with self.assertRaises(ValueError):updater.apply(self.bundle,self.target,perform=True,verify=False)
            self.preserved();self.assertFalse((self.target/'backups').exists())
    def test_preview_is_read_only(self):
        self.manifest([('runner.py',b'new','replace')])
        before=sorted(str(p.relative_to(self.target)) for p in self.target.rglob('*'))
        updater.apply(self.bundle,self.target)
        self.assertEqual(before,sorted(str(p.relative_to(self.target)) for p in self.target.rglob('*')))
        self.assertEqual((self.target/'runner.py').read_bytes(),b'# old runner\n')
    def test_active_project_blocks_update(self):
        self.manifest([('runner.py',b'new','replace')])
        with updater.lock(self.target/'locks/route-private.lock'):
            with self.assertRaises(RuntimeError):updater.apply(self.bundle,self.target,perform=True,verify=False)
        self.preserved();self.assertEqual((self.target/'runner.py').read_bytes(),b'# old runner\n')
    def test_existing_quality_policy_is_preserved(self):
        self.put(self.target/'config/research_policy.json',b'{"max_consecutive_support_rounds":5}')
        self.manifest([('config/research_policy.json',b'{"max_consecutive_support_rounds":2}','preserve_existing')])
        updater.apply(self.bundle,self.target,perform=True,verify=False)
        self.assertEqual((self.target/'config/research_policy.json').read_bytes(),b'{"max_consecutive_support_rounds":5}')
    def test_supervision_policy_must_preserve_existing_operator_choices(self):
        self.put(self.target/'config/supervision_policy.json',b'{"enabled":true,"max_reviews":9}')
        self.manifest([('config/supervision_policy.json',b'{"enabled":false}','replace')])
        with self.assertRaises(ValueError):updater.apply(self.bundle,self.target,perform=True,verify=False)
        self.manifest([('config/supervision_policy.json',b'{"enabled":false}','preserve_existing')])
        updater.apply(self.bundle,self.target,perform=True,verify=False)
        self.assertEqual((self.target/'config/supervision_policy.json').read_bytes(),b'{"enabled":true,"max_reviews":9}')
    def test_failed_postcheck_rolls_back_framework_files(self):
        self.manifest([('runner.py',b'# updated runner','replace')])
        with patch.object(updater.subprocess,'run',side_effect=RuntimeError('postcheck failed')):
            with self.assertRaises(RuntimeError):updater.apply(self.bundle,self.target,perform=True)
        self.assertEqual((self.target/'runner.py').read_bytes(),b'# old runner\n');self.preserved()
    def test_hash_tampering_is_detected(self):
        self.manifest([('runner.py',b'# intended','replace')]);self.put(self.bundle/'payload/runner.py',b'# tampered')
        with self.assertRaises(ValueError):updater.apply(self.bundle,self.target,perform=True,verify=False)
        self.preserved()

if __name__=='__main__':unittest.main()
