"""Two-project native entry acceptance; all records are disposable toy fixtures."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE))
import configuration
from verify_r03_offline import write, fingerprint


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',required=True,type=Path)
    output = parser.parse_args().output.resolve()
    if any(output.is_relative_to(SOURCE/name) for name in ('projects','state','logs','config')):
        raise ValueError('Evidence output must be outside personal runtime')
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='crc-r06-fixture-') as directory:
        root = Path(directory)
        for source in SOURCE.glob('*.py'): shutil.copy2(source,root/source.name)
        for name in ('research.cmd','VERSION'): shutil.copy2(SOURCE/name,root/name)
        for name in ('engine','knowledge','method','profiles'):
            shutil.copytree(SOURCE/name,root/name,ignore=shutil.ignore_patterns('__pycache__'))
        (root/'config').mkdir()
        for source in (SOURCE/'config').glob('*.json'): shutil.copy2(source,root/'config'/source.name)
        entry = ['cmd.exe','/d','/c',str(root/'research.cmd')] if os.name=='nt' else [sys.executable,'-B',str(root/'research.py')]
        env = dict(os.environ,CRC_PYTHON=sys.executable,PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf8')
        evidence = {'provider_requests':0,'fixture_only':True,'steps':[]}
        def invoke(args,cwd=root):
            result = subprocess.run(entry+args,cwd=cwd,env=env,capture_output=True,text=True,encoding='utf8',timeout=50)
            evidence['steps'].append({'args':args,'exit_code':result.returncode})
            if result.returncode: raise AssertionError((args,result.returncode,result.stdout,result.stderr))
            return json.loads(result.stdout)
        for name in ('example-a','example-b'):
            project = root/'projects'/name
            for relative,value in {'PROJECT.json':{'id':name,'checks':[]},
                'GOAL.md':'# 冻结的合成目标\nPreserve the exact integer claim and all assumptions.\n',
                'AGENTS.md':'Preserve the frozen goal and never certify an unreviewed candidate.',
                'RESEARCH_PROFILE.json':{'profiles':[],'read_order':[]},
                'research/STATE.json':{'phase':'PROOF','decision':'CONTINUE','research_route':'MAIN','last_run':None,
                    'next_task':'Prove the original exact integer condition.'},
                'proofs/derivation.md':'Candidate argument only; independent review is pending.\n',
                'research/FAILED_PATHS.md':'# Abandoned bounded candidate\nA recorded local failure only.\n',
                'literature/paper.txt':'Synthetic source excerpt; no original-paper verification.\n',
                'literature/seed_papers.json':{'schema_version':1,'papers':[{'id':'PAPER-1','title':'Toy source',
                    'path':'literature/paper.txt'}]}}.items(): write(project/relative,value)
            problem = {'schema_version':1,'id':'P-1','title':'Same title, explicit local assumptions',
                'statement':'For every allowed integer x, x*x >= 0.','quantifiers':'for all x','domain':'integers',
                'input_contract':'an allowed integer x','output_contract':'a nonnegative square',
                'goal_connection':'The exact frozen integer fixture goal',
                'nontriviality_argument':'Infrastructure fixture only; no novel research result asserted',
                'assumptions':['x is an integer' if name=='example-a' else 'x is a nonnegative integer'],
                'immutable_constraints':['Exact integer arithmetic'],'baseline_exclusions':['No novelty claim'],
                'contribution_type':'COMPLEXITY_THEOREM','source_paths':[],
                'obligations':[{'id':'O-1','statement':'The original integer condition',
                    'acceptance_criterion':'Independent proof and statement review'}]}
            claim = {'schema_version':1,'id':'C-1','statement':problem['statement'],'assumptions':problem['assumptions'],
                'dependencies':[],'proposer':'offline-fixture','problem_id':'P-1','problem_version':1,
                'obligation_ids':['O-1'],'nontriviality_argument':'Infrastructure fixture only, no cryptographic novelty',
                'contribution_type':'COMPLEXITY_THEOREM','evidence_paths':['proofs/derivation.md'],
                'verification_mode':'INDEPENDENT_MANUAL','formal_applicability_reason':'Toy provenance fixture only'}
            p = root/'fixture-specs'/name/'problem.json'; c = p.with_name('claim.json')
            write(p,problem); write(c,claim)
            invoke(['problem','import',name,'--file',str(p),'--reason','Register disposable original problem'])
            invoke(['claim','import',name,'--file',str(c),'--reason','Register unverified disposable candidate'])
            invoke(['attempt','start',name,'--problem','P-1'])
            invoke(['attempt','close',name,'--reason','Recorded local experiment boundary; no proof established'])
        projects = root/'projects'; frozen = fingerprint([projects,root/'state/discovery'],root)
        canonical = {name:invoke(['claim','status',name]) for name in ('example-a','example-b')}
        before_dry = fingerprint([root],root)
        invoke(['knowledge','build','example-a','--dry-run'])
        assert before_dry==fingerprint([root],root)
        receipts = {name:invoke(['knowledge','build',name])['knowledge'] for name in canonical}
        explanations = {name:invoke(['knowledge','explain',name,'--claim','C-1'])['knowledge'] for name in canonical}
        a,b = (explanations[name] for name in canonical)
        assert a['claim']['id']!=b['claim']['id']
        for explanation in explanations.values():
            kinds = {n['id']:n['kind'] for n in explanation['nodes']}
            pairs = {(kinds[e['from']],kinds[e['to']]) for e in explanation['edges']}
            assert {('CLAIM_REVISION','OBLIGATION'),('OBLIGATION','PROBLEM_VERSION'),('PROBLEM_VERSION','GOAL')}<=pairs
            assert explanation['claim']['proof_status']=='CANDIDATE'
        cache = root/'state/knowledge/example-a/index.json'; original = cache.read_bytes()
        cache.unlink(); invoke(['knowledge','build','example-a'])
        assert cache.read_bytes()==original
        assert frozen==fingerprint([projects,root/'state/discovery'],root)
        for name in canonical: assert invoke(['claim','status',name])==canonical[name]
        # Read-only CLI project inference uses the actual copied research.cmd.
        invoke(['knowledge','explain','--claim','C-1'],cwd=projects/'example-a')
        (output/'normal-subgraph.json').write_text(json.dumps(a,ensure_ascii=False,indent=2),encoding='utf8')
        write(output/'normal-receipts.json',receipts)
        # Source loss/changes keep the original pin and downgrade the live projection.
        graph_before = (projects/'example-a/research/discovery/CLAIM_GRAPH.json').read_bytes()
        write(projects/'example-a/proofs/derivation.md','Operator changed the source; pending revalidation.\n')
        assert invoke(['knowledge','status','example-a'])['knowledge']['projection']['cache_status']=='STALE'
        assert cache.read_bytes()==original
        invoke(['knowledge','build','example-a'])
        changed = invoke(['knowledge','explain','example-a','--claim','C-1'])['knowledge']
        assert changed['claim']['proof_status']=='PENDING_REVALIDATION'
        assert any(e['verified_status']=='PENDING_REVALIDATION' for e in changed['edges'])
        assert graph_before==(projects/'example-a/research/discovery/CLAIM_GRAPH.json').read_bytes()
        damaged = root/'state/knowledge/example-b/index.json'; good = damaged.read_bytes(); damaged.write_bytes(b'broken cache')
        assert invoke(['knowledge','status','example-b'])['knowledge']['projection']['cache_status']=='CORRUPT'
        assert damaged.read_bytes()==b'broken cache'
        invoke(['knowledge','build','example-b']); assert damaged.read_bytes()==good
        write(output/'changed-source-subgraph.json',changed)
        evidence.update(two_projects=True,cache_rebuild_identical=True,canonical_records_unchanged=True,
            source_change_pending=True,corrupt_cache_repaired=True,steps_count=len(evidence['steps']))
        write(output/'acceptance.json',evidence)
        print(json.dumps({k:v for k,v in evidence.items() if k!='steps'},ensure_ascii=False))


if __name__=='__main__': main()
