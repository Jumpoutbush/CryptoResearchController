"""R09 native evidence context acceptance. Only disposable synthetic data."""
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
from r07_fixture import seed


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',required=True,type=Path)
    output=parser.parse_args().output.resolve()
    if any(output.is_relative_to(SOURCE/n) for n in ('projects','state','logs','config')): raise ValueError('External evidence directory required')
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='crc-r09-fixture-') as directory:
        root=Path(directory)
        for file in SOURCE.glob('*.py'): shutil.copy2(file,root/file.name)
        for name in ('research.cmd','VERSION'): shutil.copy2(SOURCE/name,root/name)
        for name in ('engine','knowledge','method','profiles'):
            shutil.copytree(SOURCE/name,root/name,ignore=shutil.ignore_patterns('__pycache__'))
        (root/'config').mkdir()
        for file in (SOURCE/'config').glob('*.json'): shutil.copy2(file,root/'config'/file.name)
        entry=['cmd.exe','/d','/c',str(root/'research.cmd')] if os.name=='nt' else [sys.executable,'-B',str(root/'research.py')]
        env=dict(os.environ,CRC_PYTHON=sys.executable,PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf8')
        receipt={'fixture_only':True,'provider_requests':0,'steps':[]}
        def invoke(args,expected=0,cwd=root):
            result=subprocess.run(entry+args,cwd=cwd,env=env,capture_output=True,text=True,encoding='utf8',timeout=60)
            receipt['steps'].append({'args':args,'exit_code':result.returncode,'expected_exit_code':expected})
            if result.returncode!=expected: raise AssertionError((args,result.returncode,result.stdout,result.stderr))
            return json.loads(result.stdout) if expected==0 else result.stderr+result.stdout
        project=root/'projects/example'
        for rel,value in {'PROJECT.json':{'id':'example','checks':[]},'GOAL.md':'Frozen synthetic integer domain and goal.',
            'AGENTS.md':'Preserve original proof obligations.','RESEARCH_PROFILE.json':{'profiles':[],'read_order':[]},
            'research/STATE.json':{'phase':'PROOF','decision':'CONTINUE','research_route':'MAIN','last_run':None,'next_task':'Prove the frozen integer statement.'},
            'proofs/derivation.md':'Synthetic unverified candidate argument.',
            'proofs/review.md':'Synthetic operator-attested review; no cryptographic result.',
            'research/FAILED_PATHS.md':'# Bounded attempt failed\nFailure is local, not a theorem refutation.'}.items(): write(project/rel,value)
        problem={'schema_version':1,'id':'P-1','title':'Synthetic original obligation',
            'statement':'For every integer x, x*x is nonnegative.','quantifiers':'for every integer','domain':'integers',
            'input_contract':'an integer','output_contract':'a nonnegative square','goal_connection':'Exact frozen synthetic goal',
            'nontriviality_argument':'Controller provenance fixture only','assumptions':['integer arithmetic'],
            'immutable_constraints':['No weakened quantifier'],'baseline_exclusions':['No scientific novelty'],
            'contribution_type':'COMPLEXITY_THEOREM','source_paths':[],
            'obligations':[{'id':'O-1','statement':'Exact original integer invariant','acceptance_criterion':'Independent exact review'}]}
        spec=root/'fixture-spec.json'; write(spec,problem)
        invoke(['problem','import','example','--file',str(spec),'--reason','Register original disposable problem'])
        claims={}
        def import_claim(cid):
            write(spec,claims[cid]); invoke(['claim','import','example','--file',str(spec),'--reason','Bind exact disposable claim revision'])
        def review(cid):
            invoke(['claim','review','example','--id',cid,'--kind','proof_and_statement','--evidence','proofs/review.md',
                '--reviewer','independent-offline-operator','--reason','Attest this exact toy revision only'])
        for cid,deps in [('A',[]),('B',['A']),('C',['B'])]:
            claims[cid]={'schema_version':1,'id':cid,'statement':problem['statement'],'assumptions':problem['assumptions'],
                'dependencies':deps,'proposer':'toy-proposer','problem_id':'P-1','problem_version':1,'obligation_ids':['O-1'],
                'nontriviality_argument':'Synthetic provenance fixture only','contribution_type':'COMPLEXITY_THEOREM',
                'evidence_paths':['proofs/derivation.md'],'verification_mode':'INDEPENDENT_MANUAL',
                'formal_applicability_reason':'No formal theorem claimed by this infrastructure fixture'}
            import_claim(cid); review(cid)
        seed(project,claim_id='A')
        # The original existing importer binds the actual PDF into A, then rebinds B and C.
        claims['A']['evidence_paths'].append('literature/pdfs/toy-v1.pdf')
        for cid in claims: import_claim(cid); review(cid)
        spans=configuration.load_json(project/'literature/source_spans.json')
        a=next(c for c in configuration.load_json(project/'research/discovery/CLAIM_GRAPH.json')['claims'] if c['id']=='A')
        spans['spans'][0].update(claim_revision=a['revision'],claim_spec_sha256=a['spec_sha256'])
        write(project/'literature/source_spans.json',spans)
        invoke(['attempt','start','example','--problem','P-1']); invoke(['attempt','close','example','--reason','Record a bounded local failed route'])
        frozen=fingerprint([project,root/'state/discovery'],root)
        one=invoke(['knowledge','build','example'])['knowledge']
        normal=invoke(['knowledge','explain','example','--claim','C'])['knowledge']
        assert normal['claim']['proof_status']=='INDEPENDENTLY_REVIEWED'
        assert any(n['kind']=='THEOREM_SPAN' and n['location_status']=='FULLTEXT_LOCATED' for n in normal['nodes'])
        assert any(n['kind']=='FAILED_BRANCH' for n in configuration.load_json(root/'state/knowledge/example/index.json')['nodes'])
        assert frozen==fingerprint([project,root/'state/discovery'],root)
        write(output/'normal-subgraph.json',normal)
        # R09 exact context through the actual copied research.cmd; no model execution.
        before_context=fingerprint([root],root)
        query=['knowledge','context','example','--problem','P-1','--problem-version','1','--obligation','O-1','--task','Resolve original exact obligation','--dry-run']
        context=invoke(query)['knowledge']; assert context==invoke(query)['knowledge']
        assert before_context==fingerprint([root],root)
        assert context['frozen_goal']['text']==(project/'GOAL.md').read_text(encoding='utf8')
        assert any(n['positive_basis'] for n in context['selected'])
        write(output/'normal-context.json',context)
        invoke(['knowledge','context','--claim','C','--task','Exact frozen obligation','--dry-run'],cwd=project)
        small=invoke(['knowledge','context','example','--claim','C','--task','x'*6000,'--max-bytes','4096','--dry-run'])['knowledge']
        assert small['frozen_goal']['text'] and small['query']['task_truncated'] and small['context_bytes']<=4096
        write(output/'bounded-context.json',small)
        # A read-only prompt probe uses the frozen R08 function, not a reimplementation.
        shutil.copy2(SOURCE/'tests/fixtures/r09_build_prompt_r08.txt',root/'r08-prompt-baseline.txt')
        probe=root/'prompt-probe.py'
        probe.write_text("import json,hashlib,runner_core,configuration\nfrom pathlib import Path\np=Path(__file__).parent/'projects/example'\ns=configuration.load_json(p/'research/STATE.json')\nns=dict(vars(runner_core))\nexec(compile(Path(__file__).with_name('r08-prompt-baseline.txt').read_text(encoding='utf8'),'frozen-r08','exec'),ns)\nold=ns['build_prompt'](p,s,'r-context','critical')\nactual=runner_core.build_prompt(p,s,'r-context','critical')\nenabled=configuration.settings_for(p)['knowledge_policy']['enabled']\nif enabled:\n from knowledge.context_builder import prompt_context\n section=prompt_context(runner_core.ROOT,p,s)\n assert actual.replace('\\n\\n'+section,'',1)==old\nelse: assert actual==old\nassert (p/'GOAL.md').read_text(encoding='utf8') in actual\nassert 'Do not call paid APIs' in actual\nprint(json.dumps({'enabled':enabled,'original_prompt_preserved':True,'sha256':hashlib.sha256(actual.encode()).hexdigest(),'utf8_bytes':len(actual.encode())}))\n",encoding='utf8')
        def prompt_probe():
            result=subprocess.run([sys.executable,'-B',str(probe)],cwd=root,env=env,capture_output=True,text=True,encoding='utf8',timeout=60)
            receipt['steps'].append({'args':['python','-B','prompt-probe.py'],'exit_code':result.returncode,'expected_exit_code':0})
            assert result.returncode==0,(result.stdout,result.stderr)
            return json.loads(result.stdout)
        frozen_prompt=fingerprint([project,root/'state/discovery'],root)
        write(output/'disabled-prompt-receipt.json',prompt_probe())
        write(root/'config/projects/example.json',{'knowledge_policy':{'enabled':True}})
        write(output/'enabled-prompt-receipt.json',prompt_probe())
        assert frozen_prompt==fingerprint([project,root/'state/discovery'],root)

        pdf=project/'literature/pdfs/toy-v1.pdf'; original=pdf.read_bytes(); pdf.write_bytes(original+b'\nchanged original')
        two=invoke(['knowledge','build','example'])['knowledge']
        fault=invoke(['knowledge','explain','example','--claim','C'])['knowledge']
        assert fault['claim']['proof_status']=='PENDING_REVALIDATION'
        assert any([s.get('claim_id') for s in p]==['C','B','A'] for p in fault['lineage']['cause_paths'])
        write(output/'source-loss-subgraph.json',fault)
        failed_context=invoke(['knowledge','context','example','--claim','C','--task','Exact frozen obligation','--dry-run'])['knowledge']
        assert not any(n['positive_basis'] for n in failed_context['selected'])
        assert failed_context['missing_required'] or failed_context['missing_required_summary']['count']
        write(output/'invalidated-context.json',failed_context)

        before=fingerprint([root],root)
        diff=invoke(['knowledge','diff','example','--from-index',one['graph_sha256'],'--to-index',two['graph_sha256']])['knowledge']
        assert before==fingerprint([root],root); assert {c['claim_id'] for c in diff['affected_claims']}=={'A','B','C'}
        write(output/'version-diff.json',diff)
        invoke(['knowledge','diff','--from-index',one['graph_sha256'],'--to-index',two['graph_sha256']],cwd=project)
        missing=invoke(['knowledge','diff','example','--from-index','0'*64,'--to-index',two['graph_sha256']])['knowledge']
        assert missing['status']=='HISTORY_UNAVAILABLE'
        # Real formal revision clears reviews; restored PDF must not reapprove the old chain.
        pdf.write_bytes(original); claims['A']['statement']+=' Revised exact source and proof obligation.'; import_claim('A')
        invoke(['claim','refresh','example']); three=invoke(['knowledge','build','example'])['knowledge']
        revised=invoke(['knowledge','explain','example','--claim','C'])['knowledge']; assert revised['claim']['proof_status']=='PENDING_REVALIDATION'
        write(output/'revision-subgraph.json',revised)
        cache=root/'state/knowledge/example/index.json'; history=cache.with_name('history.json'); saved=history.read_bytes()
        cache_bytes=cache.read_bytes(); cache.unlink(); invoke(['knowledge','build','example'])
        assert cache_bytes==cache.read_bytes() and saved==history.read_bytes()
        # Terminate a real controller process immediately after atomic history commit.
        write(project/'proofs/derivation.md','Changed synthetic source before interrupted indexing.')
        helper=root/'interrupt-index.py'
        helper.write_text("import os,runpy,sys\nfrom pathlib import Path\nimport supervision\noriginal=supervision._write\ndef interrupt(path,raw):\n original(path,raw)\n if path.name=='history.json': os._exit(78)\nsupervision._write=interrupt\nsys.argv=['research.py','knowledge','build','example']\nrunpy.run_path(str(Path(__file__).with_name('research.py')),run_name='__main__')\n",encoding='utf8')
        interrupted=subprocess.run([sys.executable,'-B',str(helper)],cwd=root,env=env,capture_output=True,timeout=60)
        receipt['steps'].append({'args':['python','-B','interrupt-index.py'],'exit_code':interrupted.returncode,'expected_exit_code':78})
        assert interrupted.returncode==78 and cache.read_bytes()==cache_bytes
        saved=history.read_bytes(); invoke(['knowledge','build','example']); assert saved==history.read_bytes()
        tampered=configuration.load_json(history); tampered['events'][-1]['previous_sha256']='0'*64; write(history,tampered)
        damaged=history.read_bytes(); cache.unlink()
        failure=invoke(['knowledge','build','example'],expected=2); assert 'HISTORY_INTEGRITY' in failure
        repaired=invoke(['knowledge','build','example','--cache-only'])['knowledge']; assert repaired['history']['status']=='CORRUPT'
        assert damaged==history.read_bytes()
        assert invoke(['knowledge','explain','example','--claim','C'])['knowledge']['claim']['proof_status']=='PENDING_REVALIDATION'
        (output/'corrupt-history-error.txt').write_text(failure,encoding='utf8')
        (output/'valid-history.json').write_bytes(saved); (output/'tampered-history.json').write_bytes(damaged)
        authority=project/'research/discovery/CLAIM_GRAPH.json'; original_authority=authority.read_bytes()
        broken=configuration.load_json(authority)
        next(c for c in broken['claims'] if c['id']=='C')['dependency_pins']={}
        write(authority,broken); broken_bytes=authority.read_bytes()
        error=invoke(['knowledge','context','example','--claim','C','--dry-run'],expected=2)
        (output/'invalid-dependency-binding-error.txt').write_text(error,encoding='utf8')
        assert 'CLAIM_DEPENDENCY_BINDING_INVALID:C:' in error and authority.read_bytes()==broken_bytes,error
        authority.write_bytes(original_authority)
        receipt.update(steps_count=len(receipt['steps']),three_level_chain=True,original_pdf_loss_propagated=True,
            revision_requires_new_review=True,cache_recovery_idempotent=True,history_tamper_preserved=True,
            terminated_after_history_commit_recovered=True,
            readonly_diff=True,scientific_discovery=False,context_readonly=True,byte_budget_enforced=True,default_off_prompt_preserved=True,enabled_prompt_preserves_original=True,invalid_dependency_rejected_without_repair=True)
        write(output/'acceptance.json',receipt); print(json.dumps({k:v for k,v in receipt.items() if k!='steps'}))


if __name__=='__main__': main()
