"""Native run/watch acceptance with disposable synthetic science and Fake review."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
import configuration
import supervision
import supervision_guide as guide
from verify_r03_offline import write, fingerprint


SYNTHETIC_MAIN = r'''
def r05_offline_science():
    import argparse
    import supervision_guide as g
    parser = argparse.ArgumentParser(); parser.add_argument('--project', required=True)
    args, extra = parser.parse_known_args()
    project = pathlib.Path(args.project).resolve()
    if os.environ.get('CRC_R05_FAKE_SCIENCE') != '1': raise ValueError('Offline science is test-only')
    g._require_fixture(ROOT, project)
    if '--dry-run' in extra: return 0
    state = json.loads((project / 'research/STATE.json').read_text(encoding='utf8'))
    number = len(list((project / 'reports').glob('round-*.md'))) + 1
    rid = 'round-' + str(number)
    target = ROOT / 'offline-prompts' / (rid + '.txt'); target.parent.mkdir(exist_ok=True)
    target.write_text(build_prompt(project, state, rid, 'critical'), encoding='utf8')
    def put(relative, value):
        path = project / relative; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value, encoding='utf8')
    state.update(last_run=rid, next_task='Check the remaining original quantified condition with reproducible evidence.')
    put('research/STATE.json', state)
    report = 'RUN_ID: ' + rid + '\n' + ('Synthetic candidate evidence only, no independent proof certification. ' * 12)
    put('reports/' + rid + '.md', report); put('reports/LATEST.md', report)
    put('proofs/new.md', 'Distinct synthetic candidate evidence for ' + rid)
    from research_focus import make_focus
    impact = {'anchor_id': make_focus(project, state)['anchor_id'], 'scope':'CORE',
        'target_obligation':'Original quantified condition', 'before':'An unresolved core candidate',
        'after':'A reproducible candidate excludes one bounded case', 'next_mainline_task':state['next_task']}
    put('research/ROUTE_SIGNAL.json', {'run_id':rid,'progress_type':'PROOF_STEP',
        'reason':'A distinct candidate obstruction with exact reproducible evidence.',
        'evidence_paths':['proofs/new.md'],'route_blocked':False})
    put('research/ROUND_REVIEW.json', {'schema_version':1,'run_id':rid,'work_kind':'PROOF',
        'core_problem':'Original quantified obstruction', 'theoretical_obligation':'Prove the original condition',
        'nontriviality_argument':'Prior bounded cases leave the exact original quantified obligation open',
        'contribution_type':'NONE','result_status':'OPEN','evidence_paths':['proofs/new.md'],'goal_impact':impact})
    return 0
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output.resolve()
    if any(output.is_relative_to(SOURCE / name) for name in ('projects', 'state', 'logs', 'config')):
        raise ValueError('Output must be outside personal runtime trees')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='crc-r04-fixture-') as directory:
        root = Path(directory)
        for path in SOURCE.glob('*.py'): shutil.copy2(path, root / path.name)
        for name in ('research.cmd', 'VERSION'): shutil.copy2(SOURCE / name, root / name)
        for name in ('engine', 'method', 'profiles'):
            shutil.copytree(SOURCE / name, root / name, ignore=shutil.ignore_patterns('__pycache__'))
        (root / 'config').mkdir()
        for path in (SOURCE / 'config').glob('*.json'): shutil.copy2(path, root / 'config' / path.name)
        core = root / 'runner_core.py'; original = core.read_text(encoding='utf8')
        assert original.count('sys.exit(main())') == 1
        core.write_text(original.replace("if __name__ == '__main__':", SYNTHETIC_MAIN + "\nif __name__ == '__main__':").replace(
            'sys.exit(main())', 'sys.exit(r05_offline_science())'), encoding='utf8')
        configuration.ROOT = root
        project = root / 'projects/offline-example'
        for relative, value in {
            'PROJECT.json': {'id':'offline-example'}, 'GOAL.md':'# Frozen synthetic goal\nProve original O-1.\n',
            'AGENTS.md':'Preserve all frozen goals and assumptions.\n',
            'prompts/continue.md':'Original next-round instructions.\n',
            'RESEARCH_PROFILE.json':{'profiles':[],'read_order':[]}, 'literature/queries.json':{'queries':[]},
            'research/PROOF_OBLIGATIONS.json':{'obligations':[{'id':'O-1','statement':'All original quantifiers.'}]},
            'research/STATE.json':{'phase':'FALSIFICATION','decision':'CONTINUE','research_route':'MAIN',
                'last_run':None,'selected_idea':None,'priority_problem':'One explicit original quantified obstruction',
                'next_task':'Search for a reproducible counterexample under original assumptions.',
                'verified_results':[],'publication_status':'NOT_ESTABLISHED'},
            'proofs/original.md':'Synthetic candidate; unverified.\n'}.items(): write(project / relative, value)
        policy = configuration.load_json(root / 'config/route_policy.json')
        policy.update(initial_round_budget=30, stagnation_rounds=30); write(root / 'config/route_policy.json', policy)
        guide.register_fixture(root, project)
        env = dict(os.environ, CRC_PYTHON=sys.executable, CRC_R05_FAKE_SCIENCE='1',
            PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf8')
        entry = ['cmd.exe','/d','/c',str(root / 'research.cmd')] if os.name == 'nt' else [sys.executable,'-B',str(root / 'research.py')]
        evidence = {'fixture_only':True,'provider_requests':0,'steps':[]}
        def invoke(args, *, cwd=root, expected=0):
            proc = subprocess.run(entry + args, cwd=cwd, env=env, capture_output=True, text=True, encoding='utf8', timeout=100)
            evidence['steps'].append({'args':args,'exit_code':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr})
            if proc.returncode != expected: raise AssertionError(evidence['steps'][-1])
            return proc.stdout
        initial = fingerprint([project], root)
        invoke(['supervise','enable','--all','--dry-run'])
        assert initial == fingerprint([project], root)
        invoke(['supervise','enable','offline-example','--executor','fake'])
        before_dry = fingerprint([project, root / 'state/routes'], root)
        invoke(['run','offline-example','--dry-run','--offline','--no-fetch'])
        assert before_dry == fingerprint([project, root / 'state/routes'], root)
        invoke(['watch','offline-example','--max-rounds','3','--pause-seconds','0','--offline','--no-fetch'])
        view = json.loads(invoke(['supervise','pending','offline-example','--dry-run']))['event_queue']
        assert len(view['events']) == 1 and view['attempts_used'] == 1 and view['events'][0]['state'] == 'APPLIED'
        event = view['events'][0]['event_id']; guide_bytes = (project / guide.ACTIVE).read_bytes()
        before_replay = fingerprint([project, root / 'state/routes'], root)
        costs = (supervision._home(root, project) / 'ledger.json').read_bytes()
        invoke(['supervise','recover','offline-example']); invoke(['supervise','recover','offline-example'])
        assert before_replay == fingerprint([project, root / 'state/routes'], root)
        assert costs == (supervision._home(root, project) / 'ledger.json').read_bytes()
        invoke(['run','--offline','--no-fetch'], cwd=project)
        prompts = [(root / 'offline-prompts' / f'round-{n}.txt').read_text(encoding='utf8') for n in range(1,5)]
        assert [p.count('# Controller-generated supervision guide') for p in prompts] == [0,0,0,1]
        invoke(['supervise','disable','offline-example'])
        invoke(['run','offline-example','--offline','--no-fetch'])
        assert '# Controller-generated supervision guide' not in (root / 'offline-prompts/round-5.txt').read_text(encoding='utf8')
        assert guide_bytes == (project / guide.ACTIVE).read_bytes()
        assert costs == (supervision._home(root, project) / 'ledger.json').read_bytes()
        (output / 'normal-guide.md').write_bytes(guide_bytes)
        evidence.update(accepted_rounds=5, prompt_guide_counts=[0,0,0,1,0], supervision_calls=1,
            event_id=event, disabled_preserves_history=True)
        invoke(['supervise','enable','offline-example','--executor','fake'])
        import supervision_scheduler as scheduler
        second = scheduler.record_manual(root, project)['event_id']
        frozen = fingerprint([project / 'research', root / 'state/routes'], root)
        consumers = [subprocess.Popen(entry + ['supervise','recover','offline-example'], cwd=root, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf8') for _ in range(2)]
        replies = []
        for consumer in consumers:
            stdout, stderr = consumer.communicate(timeout=60)
            assert consumer.returncode in {0,2}, (consumer.returncode, stdout, stderr)
            replies.append({'exit_code':consumer.returncode,'stdout':stdout,'stderr':stderr})
        final = json.loads(invoke(['supervise','pending','offline-example','--dry-run']))['event_queue']
        assert final['attempts_used'] == 2
        assert next(e for e in final['events'] if e['event_id'] == second)['state'] == 'APPLIED'
        assert frozen == fingerprint([project / 'research', root / 'state/routes'], root)
        evidence['concurrent_consumers'] = replies
        evidence['total_supervision_calls_after_concurrency'] = 2
        # Original R04 native kill/restart proof is rerun against this source by
        # the acceptance driver alongside these official scientific receipts.
        write(output / 'acceptance.json', evidence)
        write(output / 'scientific-ledger.json', configuration.load_json(root / 'state/routes/offline-example.json'))
        print(json.dumps({k:v for k,v in evidence.items() if k != 'steps'}, ensure_ascii=False))


if __name__ == '__main__': main()
