"""R10 actual CLI acceptance in disposable NTRU toy projects; no models/network."""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE))
import configuration
from research_quality import hash_file
from verify_r03_offline import write,fingerprint


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',required=True,type=Path)
    output=parser.parse_args().output.resolve()
    if any(output.is_relative_to(SOURCE/n) for n in ('projects','state','logs','config')): raise ValueError('External evidence directory required')
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='crc-r10-fixture-') as directory:
        root=Path(directory)
        for file in SOURCE.glob('*.py'): shutil.copy2(file,root/file.name)
        for name in ('research.cmd','VERSION'): shutil.copy2(SOURCE/name,root/name)
        for name in ('engine','knowledge','method','profiles'):
            shutil.copytree(SOURCE/name,root/name,ignore=shutil.ignore_patterns('__pycache__'))
        (root/'config').mkdir()
        for file in (SOURCE/'config').glob('*.json'): shutil.copy2(file,root/'config'/file.name)
        entry=['cmd.exe','/d','/c',str(root/'research.cmd')] if os.name=='nt' else [sys.executable,'-B',str(root/'research.py')]
        env=dict(os.environ,CRC_PYTHON=sys.executable,PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf8')
        receipt={'fixture_only':True,'provider_requests':0,'network_requests':0,'steps':[]}
        def invoke(args,expected=0,cwd=root):
            process=subprocess.run(entry+args,cwd=cwd,env=env,capture_output=True,text=True,encoding='utf8',timeout=60)
            receipt['steps'].append({'args':args,'exit_code':process.returncode,'expected_exit_code':expected})
            assert process.returncode==expected,(args,process.returncode,process.stdout,process.stderr)
            return json.loads(process.stdout) if expected==0 else process.stdout+process.stderr
        projects={}; claims={}
        for key,q,adversary in (('alpha',7,'STATIC_CORRUPTION'),('beta',17,'ADAPTIVE_CORRUPTION')):
            project=root/'projects'/key; projects[key]=project
            for relative,value in {'PROJECT.json':{'id':key,'checks':[]},'GOAL.md':'Frozen NTRU toy equation; q='+str(q)+'; '+adversary,
                'AGENTS.md':'Preserve all toy constraints. No real theorem or novelty is claimed.',
                'RESEARCH_PROFILE.json':{'profiles':[],'read_order':[]},
                'research/STATE.json':{'phase':'PROOF','decision':'CONTINUE','research_route':'MAIN','last_run':None,'next_task':'Resolve frozen NTRU toy obligation'},
                'proofs/derivation.md':'Synthetic operator-attested argument, not a cryptographic proof.',
                'proofs/review.md':'Independent toy fixture review only; not a scientific finding.',
                'inputs/private.pdf':'PRIVATE PDF SENTINEL','proofs/private.py':'PRIVATE SOURCE SENTINEL',
                'reports/private.log':'PRIVATE LOG SENTINEL',
                'knowledge/shared/sources/paper.txt':'Public NTRU toy equation f*g = h (mod q), q='+str(q),
                'knowledge/shared/drafts/summary.txt':'NTRU toy equation f*g = h (mod q); not a new research result.'}.items(): write(project/relative,value)
            spec={'schema_version':1,'id':'P-1','title':'Same NTRU toy equation',
                'statement':'f*g = h in R_q','quantifiers':'For fixed public toy parameters','domain':'R_q = Z_q[x]/(x^n-1)',
                'input_contract':'Toy ring elements','output_contract':'Independent review of exact toy equation',
                'goal_connection':'Frozen NTRU toy example only','nontriviality_argument':'Infrastructure test only',
                'assumptions':['q='+str(q),adversary],'immutable_constraints':['No transfer between adversary models'],
                'baseline_exclusions':['No research or novelty claim'],'contribution_type':'COMPLEXITY_THEOREM','source_paths':[],
                'obligations':[{'id':'O-1','statement':'Exact toy equation','acceptance_criterion':'Independent toy review'}]}
            path=root/'spec.json'; write(path,spec); invoke(['problem','import',key,'--file',str(path),'--reason','Register isolated toy problem'])
            claim={'schema_version':1,'id':'NTRU-1','statement':spec['statement'],'assumptions':spec['assumptions'],
                'dependencies':[],'proposer':'toy-proposer','problem_id':'P-1','problem_version':1,'obligation_ids':['O-1'],
                'nontriviality_argument':'Infrastructure fixture only','contribution_type':'COMPLEXITY_THEOREM',
                'evidence_paths':['proofs/derivation.md'],'verification_mode':'INDEPENDENT_MANUAL','formal_applicability_reason':'No Lean assertion in this toy test'}
            claims[key]=claim; write(path,claim); invoke(['claim','import',key,'--file',str(path),'--reason','Bind exact toy claim'])
            for kind in ('proof','statement'):
                invoke(['claim','review',key,'--id','NTRU-1','--kind',kind,'--evidence','proofs/review.md',
                    '--reviewer','independent-toy-operator','--reason','Review this exact toy revision only'])
            problem=configuration.load_json(project/'research/discovery/PROBLEMS.json')['problems'][0]['revisions'][0]
            write(project/'knowledge/shared/MODEL.json',{'schema_version':1,'goal_sha256':hash_file(project/'GOAL.md'),
                'problem_id':'P-1','problem_version':1,'problem_sha256':problem['spec_sha256'],
                'model':{'model':'NTRU_TOY_MODEL','domain':spec['domain'],'quantifiers':spec['quantifiers'],'assumptions':spec['assumptions'],
                    'parameters':'q='+str(q),'adversary':adversary,'leakage':'Public toy view; '+adversary}})
        assert invoke(['knowledge','shared','beta','--dry-run'])['knowledge']['status']=='DISABLED'
        policy={'schema_version':1,'enabled':True,'projects':{}}
        capsules={}
        for key,other in (('alpha','beta'),('beta','alpha')):
            draft=invoke(['knowledge','share-preview',key,'--claim','NTRU-1','--reference-id','NTRU-EQ','--revision','1',
                '--summary','knowledge/shared/drafts/summary.txt','--public-source','knowledge/shared/sources/paper.txt',
                '--license','CC0-1.0','--approved-by','fixture-operator','--reason','Explicit public toy fixture authorization','--dry-run'])['knowledge']
            capsules[key]=draft; file=projects[key]/'knowledge/shared/references/NTRU-EQ.json'; write(file,draft)
            policy['projects'][key]={'enabled':True,'model_sha256':hash_file(projects[key]/'knowledge/shared/MODEL.json'),
                'imports':[],'exports':[{'id':'NTRU-EQ','path':'knowledge/shared/references/NTRU-EQ.json','sha256':hash_file(file),'destinations':[other]}]}
        for key,other in (('alpha','beta'),('beta','alpha')):
            policy['projects'][key]['imports']=[{'origin_project':other,'id':'NTRU-EQ','sha256':policy['projects'][other]['exports'][0]['sha256']}]
        write(root/'config/sharing_policy.json',policy)
        before=fingerprint([root],root)
        normal=invoke(['knowledge','shared','beta','--query','NTRU','--dry-run'])['knowledge']
        assert normal==invoke(['knowledge','shared','beta','--query','NTRU','--dry-run'])['knowledge']
        reverse=invoke(['knowledge','shared','alpha','--dry-run'])['knowledge']
        inferred=invoke(['knowledge','shared','--query','NTRU','--dry-run'],cwd=projects['beta'])['knowledge']
        assert inferred==normal and reverse['references'][0]['origin_project']=='beta'
        ref=normal['references'][0]
        assert ref['status']=='REFERENCE_ONLY' and not ref['positive_basis'] and ref['origin_project']=='alpha'
        assert 'ADVERSARY_MISMATCH' in ref['reuse_review']['reasons'] and len(ref['reuse_review']['mapping'])==7
        assert 'PRIVATE' not in json.dumps(normal) and ref['private_upstream_status']=='NOT_READ_OR_REVALIDATED'
        assert before==fingerprint([root],root)
        write(output/'normal-reference.json',normal); write(output/'reverse-reference.json',reverse)
        trace=invoke(['knowledge','explain','alpha','--claim','NTRU-1'])['knowledge']; write(output/'origin-proof-chain.json',trace)
        # Guard a real controller invocation against any unapproved origin file read.
        guard=root/'guard-shared.py'
        guard.write_text("import runpy,sys\nfrom pathlib import Path\nfrom unittest.mock import patch\nroot=Path(__file__).parent\noriginal=Path.open\ndef opening(path,*a,**k):\n if path.is_relative_to(root/'projects/alpha') and path.relative_to(root/'projects/alpha').as_posix() not in {'PROJECT.json','knowledge/shared/references/NTRU-EQ.json','knowledge/shared/sources/paper.txt'}: raise AssertionError('Private origin read')\n return original(path,*a,**k)\nsys.argv=['research.py','knowledge','shared','beta','--dry-run']\nwith patch.object(Path,'open',new=opening),patch('urllib.request.urlopen',side_effect=AssertionError('No network')): runpy.run_path(str(root/'research.py'),run_name='__main__')\n",encoding='utf8')
        guarded=subprocess.run([sys.executable,'-B',str(guard)],cwd=root,env=env,capture_output=True,text=True,encoding='utf8',timeout=60)
        receipt['steps'].append({'args':['python','-B','guard-shared.py'],'exit_code':guarded.returncode})
        assert guarded.returncode==0,guarded.stderr
        write(output/'guarded-reference.json',json.loads(guarded.stdout))
        # R06-R09 loop, including exact reconstruction and bounded local context.
        first=invoke(['knowledge','build','alpha'])['knowledge']; cache=root/'state/knowledge/alpha/index.json'; old=cache.read_bytes()
        history=cache.with_name('history.json').read_bytes(); cache.unlink(); second=invoke(['knowledge','build','alpha'])['knowledge']
        assert first['graph_sha256']==second['graph_sha256'] and old==cache.read_bytes() and history==cache.with_name('history.json').read_bytes()
        compact=invoke(['knowledge','context','alpha','--claim','NTRU-1','--max-bytes','4096','--dry-run'])['knowledge']
        assert compact['context_bytes']<=4096; write(output/'bounded-local-context.json',compact)
        statuses={key:invoke(['claim','status',key]) for key in projects}
        write(projects['alpha']/'knowledge/shared/sources/paper.txt','Changed authorized public original source')
        stale=invoke(['knowledge','shared','beta','--dry-run'])['knowledge']
        assert not stale['references'] and 'PUBLIC_SOURCE_CHANGED' in json.dumps(stale['diagnostics'])
        assert statuses=={key:invoke(['claim','status',key]) for key in projects}
        write(output/'stale-reference.json',stale)
        # Formal claim revision is visible to its own authority, not silently promoted by an index.
        claims['alpha']['statement']+=' Revised toy statement.'; path=root/'spec.json'; write(path,claims['alpha'])
        invoke(['claim','import','alpha','--file',str(path),'--reason','Register exact revised toy statement'])
        revised=invoke(['knowledge','context','alpha','--claim','NTRU-1','--dry-run'])['knowledge']
        assert not any(n['positive_basis'] for n in revised['selected']); write(output/'revision-context.json',revised)
        # A cached former summary is never a source of authorization.
        write(root/'state/knowledge/beta/federation.json',{'references':[ref]})
        policy['projects']['alpha']['enabled']=False; write(root/'config/sharing_policy.json',policy)
        revoked=invoke(['knowledge','shared','beta','--dry-run'])['knowledge']
        assert not revoked['references'] and not revoked['cache_used'] and ref['summary'] not in json.dumps(revoked)
        write(output/'revoked-reference.json',revoked)
        descriptor=projects['beta']/'knowledge/shared/MODEL.json'; saved=descriptor.read_bytes()
        changed=configuration.load_json(descriptor); changed['model']['adversary']='STATIC_CORRUPTION'; write(descriptor,changed)
        error=invoke(['knowledge','shared','beta','--dry-run'],expected=2)
        assert 'TARGET_MODEL_PIN_CHANGED' in error; descriptor.write_bytes(saved)
        (output/'model-pin-rejection.txt').write_text(error,encoding='utf8')
        policy['enabled']=False; write(root/'config/sharing_policy.json',policy)
        assert invoke(['knowledge','shared','beta','--dry-run'])['knowledge']['status']=='DISABLED'
        receipt.update(steps_count=len(receipt['steps']),bilateral_authorization=True,reference_only=True,private_origin_not_read=True,
            source_hash_expiration=True,revocation_ignores_cache=True,model_pin_enforced=True,cache_rebuilt=True,
            T07=True,T08=True,T09=True,scientific_discovery=False)
        write(output/'acceptance.json',receipt); print(json.dumps({k:v for k,v in receipt.items() if k!='steps'}))


if __name__=='__main__': main()
