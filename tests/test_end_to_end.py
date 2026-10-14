import tempfile,pathlib,shutil,subprocess,os,json,re,sys,unittest
source=pathlib.Path(__file__).resolve().parents[1]

@unittest.skipIf(os.name == 'nt', 'POSIX simulated executable; Windows launchers require native smoke test')
class SubprocessIntegrationTests(unittest.TestCase):
 def test_full_pipeline_acceptance_review_and_failure(self):
  with tempfile.TemporaryDirectory(prefix='crc-e2e-') as td:
   root=pathlib.Path(td)/'Controller Space';shutil.copytree(source,root,ignore=shutil.ignore_patterns('.git','__pycache__','state','logs','locks'))
   fake=pathlib.Path(td)/'bin';fake.mkdir();codex=fake/'codex'
   codex.write_text('''#!/usr/bin/env python3
import sys,re,json,pathlib,os
prompt=sys.stdin.read();rid=re.search(r"# Autonomous cryptography research round ([^\\n]+)",prompt).group(1)
p=pathlib.Path.cwd();sfile=p/'research/STATE.json';s=json.loads(sfile.read_text())
(p/'proofs/e2e-evidence.md').write_text('mock subprocess evidence '+rid+'\\n')
if os.environ.get('CRC_SMOKE_FAIL'):
 s['last_run']=rid;s['next_task']='bad partial change';sfile.write_text(json.dumps(s));sys.exit(7)
s['last_run']=rid;s['next_task']='Next falsifiable mock task after '+rid;s['decision']='CONTINUE';sfile.write_text(json.dumps(s,ensure_ascii=False))
(p/'reports'/f'{rid}.md').write_text('RUN_ID: '+rid+'\\n'+'E2E simulated report with traceable local evidence. '*12)
(p/'research/ROUTE_SIGNAL.json').write_text(json.dumps({'run_id':rid,'progress_type':'REPRODUCIBLE_TEST','reason':'Saved a fresh reproducible test witness for controller integration only.','evidence_paths':['proofs/e2e-evidence.md'],'route_blocked':False}))
if '【强制路线复评' in prompt:
 (p/'research/ROUTE_VERDICT.json').write_text(json.dumps({'run_id':rid,'outcome':'EXTEND','reason':'A new bounded integration test remains and justifies one procedural extension.','evidence_paths':['proofs/e2e-evidence.md'],'requires_goal_change':False,'candidates':[],'next_task':'Run the next independent falsifiable integration witness after route review.'}))
''',encoding='utf8');codex.chmod(0o755)
   def call(args,env=None):
    out=subprocess.run(args,cwd=root,env=env,capture_output=True,text=True)
    if out.returncode:raise RuntimeError(str(args)+': '+out.stdout[-1800:]+out.stderr[-1800:])
    return out
   call(['git','init','-b','main'])
   call(['git','add','.'])
   call(['git','-c','user.name=Integration Test','-c','user.email=test@localhost','commit','-m','baseline'])
   env=os.environ.copy();env['PATH']=str(fake)+os.pathsep+env['PATH']
   out=call([sys.executable,str(root/'research.py'),'run','secagg-research','--rounds','3','--route-budget','2','--no-fetch'],env)
   ledger=json.loads((root/'state/routes/secagg-research.json').read_text());epoch=ledger['epochs'][-1]
   assert epoch['effective_rounds']==2 and epoch['extensions_used']==1 and epoch['review_count']==1,epoch
   commits=call(['git','log','--format=%s']).stdout.splitlines();assert len(commits)==4,commits
   assert not call(['git','diff','--cached','--name-only']).stdout.strip()
   project=root/'projects/secagg-research';before=(project/'research/STATE.json').read_bytes();proof=(project/'proofs/e2e-evidence.md').read_bytes();head=call(['git','rev-parse','HEAD']).stdout
   env['CRC_SMOKE_FAIL']='1'
   bad=subprocess.run([sys.executable,str(root/'research.py'),'run','secagg-research','--no-fetch'],cwd=root,env=env,capture_output=True,text=True)
   assert bad.returncode==7,(bad.returncode,bad.stdout[-1000:],bad.stderr[-1000:])
   assert before==(project/'research/STATE.json').read_bytes()
   assert proof==(project/'proofs/e2e-evidence.md').read_bytes()
   assert call(['git','rev-parse','HEAD']).stdout==head
   assert list((root/'state/failed_runs/secagg-research').rglob('failure.json'))
   print(json.dumps({'status':'PASS','scope':'real frontend-wrapper-core subprocess chain with simulated Codex only','accepted_research_rounds':2,'route_review_rounds':1,'failure_restored':True,'accepted_git_commits':3,'space_in_root_path':True},indent=2))

if __name__ == "__main__": unittest.main()
