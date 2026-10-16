"""Disposable R04 real-entry acceptance, including a killed controller process."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
import configuration
from research_focus import make_focus
import supervision
import supervision_calls as calls
import supervision_executor as executor
import supervision_guide as guide
import supervision_ledger as queue
import supervision_scheduler as scheduler
from verify_r03_offline import write, fingerprint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    output = parser.parse_args().output.resolve()
    if any(output.is_relative_to(SOURCE / name) for name in ('projects', 'state', 'logs', 'config')):
        raise ValueError('Evidence output must be outside personal project/runtime/config trees')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='crc-r04-fixture-') as directory:
        root = Path(directory)
        for source in SOURCE.glob('*.py'): shutil.copy2(source, root / source.name)
        for name in ('VERSION', 'research.cmd'): shutil.copy2(SOURCE / name, root / name)
        for name in ('engine', 'method', 'profiles'):
            shutil.copytree(SOURCE / name, root / name, ignore=shutil.ignore_patterns('__pycache__'))
        (root / 'config').mkdir()
        for source in (SOURCE / 'config').glob('*.json'): shutil.copy2(source, root / 'config' / source.name)
        configuration.ROOT = root
        project = root / 'projects/offline-example'
        sources = {
            'PROJECT.json': {'id': 'offline-example'},
            'GOAL.md': '# Frozen R04 synthetic goal\nProve O-1 under every original assumption.\n',
            'AGENTS.md': 'Synthetic user instructions remain unchanged.\n',
            'prompts/continue.md': 'Synthetic original next-round instructions.\n',
            'literature/queries.json': {'queries': []},
            'research/PROOF_OBLIGATIONS.json': {'obligations': [{'id': 'O-1', 'statement': 'All original quantifiers.'}]},
            'proofs/argument.md': 'A synthetic candidate, with no independent proof certificate.\n',
            'reports/LATEST.md': 'RUN_ID: r3\nSynthetic latest accepted report.\n',
            'research/ROUND_REVIEW.json': {'schema_version': 1, 'run_id': 'r3', 'evidence_paths': ['proofs/argument.md']}}
        for relative, value in sources.items(): write(project / relative, value)
        state = {'phase': 'PROOF', 'decision': 'CONTINUE', 'research_route': 'MAIN', 'last_run': 'r3',
                 'selected_idea': None, 'priority_problem': 'Synthetic frozen obligation', 'next_task': 'Review O-1.'}
        write(project / 'research/STATE.json', state)
        runs = ['r1', 'r2', 'r3']
        for run in runs: write(project / f'reports/{run}.md', f'RUN_ID: {run}\nSynthetic accepted candidate.\n')
        epoch = {'epoch': 1, 'route': 'MAIN', 'effective_rounds': 3, 'stagnation': 0, 'extensions_used': 0,
            'counted_run_ids': runs, 'last_processed_run': 'r3', 'review_pending': False, 'focus': make_focus(project, state)}
        ledger = {'schema_version': 1, 'project_id': 'offline-example', 'epochs': [epoch], 'events': [
            {'type': 'RESEARCH_ROUND', 'run_id': run, 'route': 'MAIN', 'effective_rounds': i + 1,
             'changed_evidence_paths': ['proofs/argument.md']} for i, run in enumerate(runs)]}
        write(root / 'state/routes/offline-example.json', ledger)
        for filename in ('supervision_defaults.json', 'supervision_policy.json'):
            path = root / 'config' / filename; data = configuration.load_json(path); data['enabled'] = True; write(path, data)
        guide.register_fixture(root, project)
        before = fingerprint([project, root / 'state/routes'], root)
        event = scheduler.record_postaccept(root, project, ledger, epoch, 'r3')['event_id']
        env = dict(os.environ, CRC_PYTHON=sys.executable, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf8')
        entry = ['cmd.exe', '/d', '/c', 'research.cmd'] if os.name == 'nt' else [sys.executable, '-B', 'research.py']
        evidence = {'fixture_only': True, 'provider_requests': 0, 'entry': entry[-1], 'steps': []}
        def invoke(args, expected=0, json_reply=True):
            result = subprocess.run(entry + args, cwd=root, env=env, capture_output=True,
                                    text=True, encoding='utf8', timeout=40)
            if result.returncode != expected: raise AssertionError((result.returncode, result.stdout, result.stderr))
            reply = json.loads(result.stdout) if json_reply else result.stdout
            evidence['steps'].append({'args': args, 'exit_code': result.returncode,
                'reply': reply if json_reply else {'guide_count': reply.count('# Controller-generated supervision guide'),
                    'prompt_sha256': guide._hash(reply.encode('utf8'))}})
            return reply
        invoke(['supervise', 'execute', 'offline-example', '--event-id', event, '--executor', 'fake'])
        cost_path = supervision._home(root, project) / 'ledger.json'; cost = cost_path.read_bytes()
        all_before = fingerprint([root], root)
        preview = invoke(['supervise', 'preview', 'offline-example', '--event', event])
        assert all_before == fingerprint([root], root)
        apply_args = ['supervise', 'apply', 'offline-example', '--event', event, '--expected-hash', preview['old_guide_sha256']]
        applied = invoke(apply_args); invoke(apply_args)
        assert applied['status'] == 'APPLIED'
        prompt = invoke(['prompt', 'offline-example'], json_reply=False)
        assert prompt.count('# Controller-generated supervision guide') == 1
        assert prompt.index('Synthetic original next-round instructions.') < prompt.index('# Controller-generated supervision guide')
        (output / 'normal-guide.md').write_bytes((project / guide.ACTIVE).read_bytes())
        write(output / 'normal-application.json', guide._object(guide._receipt_path(root, project, event, 'APPLY')))
        invoke(['supervise', 'rollback', 'offline-example', '--event', event, '--expected-hash', applied['new_guide_sha256']])
        assert not (project / guide.ACTIVE).exists(); assert cost_path.read_bytes() == cost
        second = scheduler.record_manual(root, project)['event_id']
        invoke(['supervise', 'execute', 'offline-example', '--event-id', second, '--executor', 'fake'])
        cost = cost_path.read_bytes()
        # Independent local worker dies after atomic replace, before receipt.
        worker = root / 'r04-fault-worker.py'; ready = root / 'r04-replaced.json'
        worker.write_text('import sys\nfrom pathlib import Path\nimport supervision_guide as g\n'
            'def crash_window(*args):\n Path(sys.argv[4]).write_text("replaced",encoding="utf8")\n sys.stdin.read()\n'
            'g._commit_receipt=crash_window\n'
            'g.apply(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3],expected_hash=g.ABSENT)\n', encoding='utf8')
        process = subprocess.Popen([sys.executable, '-B', str(worker), str(root), str(project), second, str(ready)],
            cwd=root, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 25
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline: time.sleep(.01)
            assert ready.exists(), 'Worker did not reach replacement fence'
            replaced = (project / guide.ACTIVE).read_bytes()
        finally:
            if process.poll() is None: process.kill()
            stdout, stderr = process.communicate(timeout=10)
        recovered = invoke(['supervise', 'guide-recover', 'offline-example', '--event', second])
        invoke(['supervise', 'guide-recover', 'offline-example', '--event', second])
        assert recovered['status'] == 'APPLIED'; assert (project / guide.ACTIVE).read_bytes() == replaced
        assert cost_path.read_bytes() == cost
        write(output / 'crash-plan.json', guide._plan(root, project, second, 'APPLY'))
        write(output / 'recovered-application.json', guide._object(guide._receipt_path(root, project, second, 'APPLY')))
        write(output / 'guide-operations.json', [op for op in queue.operations(root, project) if op['type'].startswith('GUIDE_')])
        invoke(['supervise', 'rollback', 'offline-example', '--event', second, '--expected-hash', recovered['new_guide_sha256']])
        assert not (project / guide.ACTIVE).exists()
        assert before == fingerprint([project, root / 'state/routes'], root)
        evidence.update(protected_unchanged=True, supervision_budget_unchanged_by_guides=True,
                        native_child_killed_after_replace=True, native_child_exit_code=process.returncode)
        write(output / 'acceptance.json', evidence)
        print(json.dumps({'accepted': True, 'steps': len(evidence['steps']), 'provider_requests': 0,
            'protected_unchanged': True, 'native_crash_recovered': True, 'output': str(output)}))
    return 0


if __name__ == '__main__': sys.exit(main())
