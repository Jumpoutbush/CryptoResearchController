import tempfile,pathlib,shutil,subprocess,os,json,re,sys,unittest
source=pathlib.Path(__file__).resolve().parents[1]

@unittest.skipIf(os.name == 'nt', 'POSIX simulated executable; Windows launchers require native smoke test')
class SubprocessIntegrationTests(unittest.TestCase):
 def test_full_pipeline_acceptance_review_and_failure(self):
  with tempfile.TemporaryDirectory(prefix='crc-e2e-') as td:
   root=pathlib.Path(td)/'Controller Space';shutil.copytree(source,root,ignore=shutil.ignore_patterns('.git','__pycache__','state','logs','locks','projects'))
   fake=pathlib.Path(td)/'bin';fake.mkdir();codex=fake/'codex'
   codex.write_text('''#!/usr/bin/env python3
import sys,re,json,pathlib,os
prompt=sys.stdin.read();rid=re.search(r"# Autonomous cryptography research round ([^\\n]+)",prompt).group(1)
p=pathlib.Path.cwd();sfile=p/'research/STATE.json';s=json.loads(sfile.read_text())
anchor=re.search(r'"anchor_id": "([a-f0-9]+)"',s['next_task']).group(1)
impact={'anchor_id':anchor,'scope':'CORE','target_obligation':'Mock core integration obligation','before':'Unresolved test condition','after':'New bound fixture evidence','next_mainline_task':'Run the next independent falsifiable integration witness after route review.'}
(p/'proofs/e2e-evidence.md').write_text('mock subprocess evidence '+rid+'\\n')
if os.environ.get('CRC_SMOKE_FAIL'):
 s['last_run']=rid;s['next_task']='bad partial change';sfile.write_text(json.dumps(s));sys.exit(7)
s['last_run']=rid;s['next_task']='Next falsifiable mock task after '+rid;s['decision']='CONTINUE';sfile.write_text(json.dumps(s,ensure_ascii=False))
if s.get('initialization_required'):
 sys.path.insert(0,str(p.parents[1]))
 from engine.initialization import DOCUMENTS,input_bindings
 from research_quality import hash_file
 for rel in DOCUMENTS:
  dest=p/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text('Derived initialization fixture, no actual theorem or novelty is claimed. '*4)
 template=p.parents[1]/'templates/project/research/PROBLEM_TEMPLATE.json'
 proposal=json.loads(template.read_text());proposal.update(title='Exact fixture problem',statement='For every integer x, x*x >= 0',quantifiers='For all integers x',domain='Integers',input_contract='An exact integer x',output_contract='A nonnegative square',assumptions=['x is an integer'],immutable_constraints=['Exact arithmetic'],goal_connection='Initialization fixture',nontriviality_argument='Test fixture only; no research result',baseline_exclusions=['No novelty claimed'],obligations=[{'id':'O-001','statement':'Show square nonnegative','acceptance_criterion':'Independent proof review'}])
 (p/'research/PROBLEM_PROPOSAL.json').write_text(json.dumps(proposal))
 (p/'research/PROOF_OBLIGATIONS.json').write_text(json.dumps({'schema_version':1,'obligations':[{'id':'O-001','statement':'Unresolved exact fixture obligation requiring independent review','status':'OPEN','acceptance_criterion':'Independent proof review'}]}))
 (p/'literature/SEARCH_PLAN.json').write_text(json.dumps({'queries':['exact integer invariant cryptography'],'scope':'Simulated initialization only; no real literature review'}))
 manifest={'schema_version':1,'run_id':rid,'status':'READY_FOR_PROBLEM_REVIEW','source_bindings':input_bindings(p),'documents':[{'file':rel,'sha256':hash_file(p/rel),'status':'DRAFT','source_paths':['GOAL.md']} for rel in DOCUMENTS],'unresolved_inputs':[]}
 (p/'research/INITIALIZATION.json').write_text(json.dumps(manifest))
 s.update(initialization_required=False,initialization_status='READY_FOR_PROBLEM_REVIEW',phase='INTAKE');sfile.write_text(json.dumps(s))
(p/'reports'/f'{rid}.md').write_text('RUN_ID: '+rid+'\\n'+'E2E simulated report with traceable local evidence. '*12)
(p/'research/ROUTE_SIGNAL.json').write_text(json.dumps({'run_id':rid,'progress_type':'REPRODUCIBLE_TEST','reason':'Saved a fresh reproducible test witness for controller integration only.','evidence_paths':['proofs/e2e-evidence.md'],'route_blocked':False}))
(p/'research/ROUND_REVIEW.json').write_text(json.dumps({'schema_version':1,'run_id':rid,'work_kind':'PROOF','core_problem':'Mock integration obstruction','theoretical_obligation':'Check quantified integration condition','nontriviality_argument':'Fake evidence for infrastructure verification only','contribution_type':'NONE','result_status':'SUPPORT_ONLY' if os.environ.get('CRC_SMOKE_SUPPORT') else 'OPEN','evidence_paths':['proofs/e2e-evidence.md'],'goal_impact':impact}))
if '【强制路线复评' in prompt:
 assert '# ROUTE REVIEW MODE' in prompt and '# AUDIT MODE' not in prompt
 (p/'research/ROUTE_VERDICT.json').write_text(json.dumps({'run_id':rid,'outcome':'REFOCUS' if os.environ.get('CRC_SMOKE_SUPPORT') else 'EXTEND','reason':'A new bounded integration test remains and justifies a concrete core continuation.','evidence_paths':['proofs/e2e-evidence.md'],'requires_goal_change':False,'candidates':[],'next_task':impact['next_mainline_task'],'next_goal_impact':impact}))
''',encoding='utf8');codex.chmod(0o755)
   def call(args,env=None):
    out=subprocess.run(args,cwd=root,env=env,capture_output=True,text=True)
    if out.returncode:raise RuntimeError(str(args)+': '+out.stdout[-1800:]+out.stderr[-1800:])
    return out
   goal=pathlib.Path(td)/'goal.md';goal.write_text('Test a precise theoretical invariant and preserve the fixed interface.',encoding='utf8')
   call([sys.executable,str(root/'research.py'),'new','integration','--goal-file',str(goal),'--title','Integration test'])
   call([sys.executable,str(root/'research.py'),'ready','integration'])
   call(['git','init','-b','main'])
   call(['git','add','.'])
   call(['git','-c','user.name=Integration Test','-c','user.email=test@localhost','commit','-m','baseline'])
   env=os.environ.copy();env['PATH']=str(fake)+os.pathsep+env['PATH']
   out=call([sys.executable,str(root/'research.py'),'run','integration','--rounds','3','--route-budget','2','--no-fetch'],env)
   ledger=json.loads((root/'state/routes/integration.json').read_text());epoch=ledger['epochs'][-1]
   assert epoch['effective_rounds']==2 and epoch['extensions_used']==1 and epoch['review_count']==1,epoch
   commits=call(['git','log','--format=%s']).stdout.splitlines();assert len(commits)==1,commits
   assert not call(['git','diff','--cached','--name-only']).stdout.strip()
   assert not call(['git','ls-files','--','projects','state']).stdout.strip()
   project=root/'projects/integration';before=(project/'research/STATE.json').read_bytes();proof=(project/'proofs/e2e-evidence.md').read_bytes();head=call(['git','rev-parse','HEAD']).stdout
   env['CRC_SMOKE_FAIL']='1'
   bad=subprocess.run([sys.executable,str(root/'research.py'),'run','integration','--no-fetch'],cwd=root,env=env,capture_output=True,text=True)
   assert bad.returncode==7,(bad.returncode,bad.stdout[-1000:],bad.stderr[-1000:])
   assert before==(project/'research/STATE.json').read_bytes()
   assert proof==(project/'proofs/e2e-evidence.md').read_bytes()
   assert call(['git','rev-parse','HEAD']).stdout==head
   assert list((root/'state/failed_runs/integration').rglob('failure.json'))
   del env['CRC_SMOKE_FAIL'];env['CRC_SMOKE_SUPPORT']='1'
   call([sys.executable,str(root/'research.py'),'new','support','--goal-file',str(goal),'--title','Supporting work fixture'])
   call([sys.executable,str(root/'research.py'),'ready','support'])
   out=call([sys.executable,str(root/'research.py'),'run','support','--rounds','3','--route-budget','6','--no-fetch'],env)
   ledger=json.loads((root/'state/routes/support.json').read_text());epoch=ledger['epochs'][-1]
   assert epoch['effective_rounds']==2 and epoch['extensions_used']==0 and epoch['review_count']==1,epoch
   assert epoch['stagnation']==0 and epoch['support_rounds']==0 and not epoch['review_pending'],epoch
   rounds=[e for e in ledger['events'] if e['type']=='RESEARCH_ROUND']
   assert len(rounds)==2 and all(not e['substantive_progress_claim'] for e in rounds),rounds
   assert 'ROUTE_DECISION: REFOCUSED' in out.stdout,out.stdout[-1500:]
   print(json.dumps({'status':'PASS','scope':'real frontend-wrapper-core subprocess chain with simulated Codex only','accepted_research_rounds':4,'route_review_rounds':2,'failure_restored':True,'support_loop_refocused':True,'accepted_git_commits':0,'space_in_root_path':True},indent=2))

if __name__ == "__main__": unittest.main()
