"""R03 real-entry acceptance using disposable synthetic projects, no models.

python -B scripts/verify_r03_offline.py --output <local-evidence-directory>
"""
import argparse
import hashlib
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
from research_focus import make_focus
import supervision
import supervision_calls as calls
import supervision_ledger as queue
import supervision_scheduler as scheduler


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) if isinstance(value, (dict, list))
                    else value, encoding='utf8')


def fingerprint(paths, root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for base in paths for p in base.rglob('*') if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output.resolve()
    # Evidence may never be placed in the controller's research/runtime trees.
    if any(output.is_relative_to(SOURCE / name) for name in ('projects', 'state', 'logs', 'config')):
        raise ValueError('Choose an evidence output outside project/runtime/config trees')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='r03-accept-') as directory:
        root = Path(directory)
        if root.resolve().is_relative_to(SOURCE): raise ValueError('Fixture must be outside the controller')
        for source in SOURCE.glob('*.py'): shutil.copy2(source, root / source.name)
        for name in ('VERSION', 'research.cmd'): shutil.copy2(SOURCE / name, root / name)
        for name in ('engine', 'method'):
            shutil.copytree(SOURCE / name, root / name, ignore=shutil.ignore_patterns('__pycache__'))
        (root / 'config').mkdir()
        for source in (SOURCE / 'config').glob('*.json'): shutil.copy2(source, root / 'config' / source.name)
        configuration.ROOT = root
        project = root / 'projects/offline-example'
        for relative, content in {
            'PROJECT.json': {'id': 'offline-example'},
            'GOAL.md': '# Frozen synthetic goal\nProve O-1 without weakening any assumption.\n',
            'AGENTS.md': 'Synthetic original instructions.\n',
            'prompts/continue.md': 'Synthetic original next task.\n',
            'proofs/argument.md': 'Candidate support only. No proof or refutation certificate.\n',
            'research/PROOF_OBLIGATIONS.json': {'obligations': [{'id': 'O-1', 'statement': 'All original quantifiers.'}]},
            'research/ROUND_REVIEW.json': {'schema_version': 1, 'run_id': 'r3', 'evidence_paths': ['proofs/argument.md']},
            'reports/LATEST.md': 'RUN_ID: r3\nSynthetic accepted report.\n',
        }.items(): write(project / relative, content)
        state = {'phase': 'PROOF', 'decision': 'CONTINUE', 'research_route': 'MAIN', 'last_run': 'r3',
                 'selected_idea': None, 'priority_problem': 'Synthetic frozen obligation', 'next_task': 'Review O-1.'}
        write(project / 'research/STATE.json', state)
        runs = ['r1', 'r2', 'r3']
        for run in runs: write(project / f'reports/{run}.md', f'RUN_ID: {run}\nSynthetic accepted candidate.\n')
        epoch = {'epoch': 1, 'route': 'MAIN', 'effective_rounds': 3, 'stagnation': 0, 'extensions_used': 0,
                 'counted_run_ids': runs, 'last_processed_run': 'r3', 'review_pending': False,
                 'focus': make_focus(project, state)}
        ledger = {'schema_version': 1, 'project_id': 'offline-example', 'epochs': [epoch], 'events': [
            {'type': 'RESEARCH_ROUND', 'run_id': run, 'route': 'MAIN', 'effective_rounds': i + 1,
             'changed_evidence_paths': ['proofs/argument.md']} for i, run in enumerate(runs)]}
        write(root / 'state/routes/offline-example.json', ledger)
        for filename in ('supervision_defaults.json', 'supervision_policy.json'):
            path = root / 'config' / filename
            data = configuration.load_json(path); data['enabled'] = True; write(path, data)
        protected = fingerprint([project, root / 'state/routes'], root)
        event = scheduler.record_postaccept(root, project, ledger, epoch, 'r3')['event_id']
        env = dict(os.environ, CRC_PYTHON=sys.executable, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf8')
        base = ['cmd.exe', '/d', '/c', 'research.cmd'] if os.name == 'nt' else [sys.executable, '-B', 'research.py']
        evidence = {'fixture_only': True, 'provider_requests': 0, 'entry': base[-1], 'steps': []}
        def invoke(event_id, backend='fake', dry=False, expected=0):
            args = ['supervise', 'execute', 'offline-example', '--event-id', event_id, '--executor', backend]
            if dry: args.append('--dry-run')
            result = subprocess.run(base + args, cwd=root, env=env, capture_output=True, text=True, timeout=40)
            if result.returncode != expected: raise AssertionError((result.returncode, result.stdout, result.stderr))
            reply = json.loads(result.stdout)
            evidence['steps'].append({'args': args, 'exit_code': result.returncode, 'reply': reply})
            return reply
        before = fingerprint([root], root)
        assert invoke(event, dry=True)['status'] == 'DRY_RUN'
        assert before == fingerprint([root], root)
        assert invoke(event)['state'] == 'PROPOSED'
        assert invoke(event)['replayed']
        receipt = configuration.load_json(calls._completion_path(root, project, event))
        write(output / 'normal-completion.json', receipt)
        fault = scheduler.record_manual(root, project)['event_id']
        real = invoke(fault, backend='codex', expected=2)
        assert real['status'] == 'BLOCKED'  # Only metadata --help/--version; never exec a provider.
        assert supervision._load(root, project)['attempts_used'] == 1
        claim = scheduler.claim_event(root, project, fault)
        calls.mark_dispatched(root, project, fault, claim['claim_token'], argv=['offline-fault-injection'])
        for _ in range(2): assert invoke(fault, expected=2)['reason'] == 'UNKNOWN_EXTERNAL_OUTCOME'
        saved = supervision._load(root, project)
        assert saved['attempts_used'] == 2
        assert saved['event_reservations'][fault]['state'] == 'RUNNING'
        assert saved['seconds_used'] >= saved['event_reservations'][fault]['reserved_seconds']
        assert fingerprint([project, root / 'state/routes'], root) == protected
        evidence.update(protected_unchanged=True, attempts_used=saved['attempts_used'],
                        seconds_used=saved['seconds_used'], pending=scheduler.pending(root, project))
        write(output / 'unknown-ledger.json', saved)
        write(output / 'acceptance.json', evidence)
        print(json.dumps({'accepted': True, 'steps': len(evidence['steps']), 'provider_requests': 0,
                          'protected_unchanged': True, 'output': str(output)}, ensure_ascii=False))
    return 0


if __name__ == '__main__': sys.exit(main())
