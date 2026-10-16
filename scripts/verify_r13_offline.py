"""R13 real controller acceptance with data-only integer workers and blocked Lean.

Only public controller files enter temporary synthetic projects. The audit hook
allows exactly the pinned trusted worker argv and source hash; it refuses every
other nested command and all network activity. No personal research is executed.
"""
from __future__ import annotations

import argparse
import copy
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
import route_budget
from research_focus import make_focus
from verify_r03_offline import fingerprint, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output.resolve()
    if any(output.is_relative_to(SOURCE / name) for name in ('projects', 'state', 'logs', 'config')):
        raise ValueError('Evidence must be outside project/runtime/config trees')
    output.mkdir(parents=True, exist_ok=True)
    receipt = {'round': 'R13', 'fixture_only': True, 'provider_requests': 0, 'network_requests': 0,
               'lean_executions': 0, 'supervision_executions': 0, 'steps': []}
    with tempfile.TemporaryDirectory(prefix='crc r13 native fixture ') as directory:
        root = Path(directory)
        for file in SOURCE.glob('*.py'):
            shutil.copy2(file, root / file.name)
        for name in ('research.cmd', 'VERSION'):
            shutil.copy2(SOURCE / name, root / name)
        for name in ('engine', 'candidate_search', 'knowledge', 'method', 'profiles'):
            shutil.copytree(SOURCE / name, root / name, ignore=shutil.ignore_patterns('__pycache__'))
        (root / 'config').mkdir()
        for file in (SOURCE / 'config').glob('*.json'):
            shutil.copy2(file, root / 'config' / file.name)
        worker = root / 'candidate_search/verifiers/trusted_integer_worker.py'
        worker_sha = hashlib.sha256(worker.read_bytes()).hexdigest()
        write(root / 'sitecustomize.py', """import os, sys, json, hashlib, subprocess
from pathlib import Path
def guard(event, args):
    if event == 'subprocess.Popen':
        argv=args[1]
        expected=[sys.executable,'-I','-B',os.environ['CRC_R13_WORKER']]
        source=Path(os.environ['CRC_R13_WORKER'])
        current=hashlib.sha256(source.read_bytes()).hexdigest()
        cwd=Path(args[2]) if args[2] is not None else None
        environment=args[3]
        # Windows audits the exact serialized command line and executable=None;
        # POSIX audits the original argv list. Both comparisons are exact.
        argv_matches=(argv==expected if isinstance(argv,list) else
            isinstance(argv,str) and argv==subprocess.list2cmdline(expected))
        valid=(argv_matches and args[0] in {None,sys.executable}
            and current==os.environ['CRC_R13_WORKER_SHA'] and cwd is not None
            and cwd.name.startswith('crc trusted integer ') and not any(cwd.iterdir())
            and isinstance(environment,dict) and set(environment)<={'SYSTEMROOT','WINDIR','TEMP','TMP'})
        if valid:
            with open(os.environ['CRC_R13_ALLOWED_LOG'],'a',encoding='utf8') as log:
                log.write(json.dumps({'argv':argv,'worker_sha256':current,'empty_workdir':True,
                    'environment_keys':sorted(environment),'os_sandbox_certified':False})+'\\n')
            return
    elif event not in {'socket.connect','socket.getaddrinfo','os.system','os.exec','os.posix_spawn','os.spawn'}:
        return
    with open(os.environ['CRC_R13_DENIED_LOG'],'a',encoding='utf8') as log:
        log.write(event+'\\n')
    raise RuntimeError('R13 fixture forbids network or arbitrary nested execution: '+event)
sys.addaudithook(guard)
""")
        # PATH is fixture-only, making missing-elan status deterministic without
        # probing, executing, downloading or modifying any host toolchain.
        env = dict(os.environ, CRC_PYTHON=sys.executable, PYTHONDONTWRITEBYTECODE='1',
            PYTHONIOENCODING='utf8', PYTHONPATH=str(root), PYTHONNOUSERSITE='1', PATH=str(root),
            CRC_R13_WORKER=str(worker), CRC_R13_WORKER_SHA=worker_sha,
            CRC_R13_ALLOWED_LOG=str(root / 'allowed-workers.jsonl'),
            CRC_R13_DENIED_LOG=str(root / 'forbidden-execution.jsonl'))
        entry = ([os.environ.get('COMSPEC', r'C:\Windows\System32\cmd.exe'), '/d', '/c', 'research.cmd']
                 if os.name == 'nt' else [sys.executable, '-B', str(root / 'research.py')])
        receipt['entry'] = 'research.cmd' if os.name == 'nt' else 'research.py'

        def invoke(args, expected=0, *, environment=None, cwd=root):
            result = subprocess.run(entry + args, cwd=cwd, env=environment or env,
                capture_output=True, text=True, encoding='utf8', timeout=60)
            item = {'args': args, 'exit_code': result.returncode, 'expected_exit_code': expected,
                    'stdout': result.stdout, 'stderr': result.stderr}
            receipt['steps'].append(item)
            assert result.returncode == expected, item
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                if expected == 0:
                    raise
                return {'diagnostic': result.stdout + result.stderr}

        authorities = [root / 'projects', root / 'config', root / 'state/routes', root / 'state/route_registry',
            root / 'state/discovery', root / 'state/supervision', root / 'state/research_acceptance',
            root / 'state/candidate_selection_registry']

        def protected():
            result = fingerprint(authorities, root)
            for path in (root / 'state/candidates').glob('*/catalog.json'):
                result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
            return result

        def unchanged(args, expected=0, **kwargs):
            before = protected()
            result = invoke(args, expected=expected, **kwargs)
            assert protected() == before, 'Verifier changed canonical research, candidates or original budget'
            return result

        project = root / 'projects/alpha'
        state = {'phase': 'PROOF', 'decision': 'CONTINUE', 'research_route': 'MAIN', 'selected_idea': None,
            'last_run': 'toy-r2', 'priority_problem': 'Frozen toy predicate', 'next_task': 'Check exact toy statements'}
        for relative, value in {'PROJECT.json': {'id': 'alpha', 'checks': []},
            'GOAL.md': 'Frozen exact integer toy target; never certify a different formal statement.\n',
            'AGENTS.md': 'Infrastructure fixtures only; preserve all original proof and model gates.\n',
            'RESEARCH_PROFILE.json': {'profiles': [], 'read_order': []}, 'research/STATE.json': state,
            'proofs/polynomial.md': 'Exact toy polynomial identity to be falsified, not a proof.\n',
            'proofs/nonnegative.md': 'Toy nonnegativity predicate; bounded search is not universal proof.\n',
            'proofs/formal.md': 'The required natural statement has original nontrivial quantifiers.\n',
            'proofs/lean/Weak.lean': 'theorem weak_target : True := by\n  trivial\n',
            'proofs/lean/lean-toolchain': 'leanprover/lean4:v4.29.1\n',
            'proofs/lean/lake-manifest.json': {'version': '1.1.0', 'packages': []},
            'proofs/lean/lakefile.toml': 'name = "r13_toy_fixture"\nversion = "0.0.0"\n'}.items():
            write(project / relative, value)
        epoch = {'epoch': 1, 'route': 'MAIN', 'effective_rounds': 2, 'stagnation': 0, 'extensions_used': 0,
            'counted_run_ids': ['toy-r1', 'toy-r2'], 'last_processed_run': 'toy-r2', 'review_pending': False,
            'focus': make_focus(project, state)}
        route_budget.save_ledger(root / 'state/routes/alpha.json', {'schema_version': 1, 'project_id': 'alpha',
            'epochs': [epoch], 'events': [{'type': 'RESEARCH_ROUND', 'run_id': run} for run in ('toy-r1', 'toy-r2')]})
        problem = {'schema_version': 1, 'id': 'P-1', 'title': 'Frozen exact integer toy predicates',
            'statement': 'Check the exact original toy arithmetic statements without weakening their quantifiers',
            'quantifiers': 'for every original toy integer assignment', 'domain': 'integers',
            'input_contract': 'Exact toy integer assignments', 'output_contract': 'Scoped statement evidence only',
            'goal_connection': 'Original frozen toy target', 'nontriviality_argument': 'Infrastructure test, no research claim',
            'assumptions': ['Exact integer arithmetic'], 'immutable_constraints': ['Preserve original quantifiers'],
            'baseline_exclusions': ['No novelty or cryptographic proof claim'], 'contribution_type': 'COMPLEXITY_THEOREM',
            'source_paths': [], 'obligations': [{'id': 'O-1', 'statement': 'Original exact toy predicate',
                'acceptance_criterion': 'Independent statement and proof correspondence review'}]}
        file = root / 'input.json'
        write(file, problem)
        invoke(['problem', 'import', 'alpha', '--file', str(file), '--reason', 'Register isolated exact toy problem'])
        claims = {}
        for cid, text, evidence, machine in (
            ('POLY', '(x+1)*(x+1) == x*x+1 for every integer x', 'proofs/polynomial.md',
             {'domain': 'INTEGER', 'variables': ['x'], 'preconditions': [], 'conclusion': '(x+1)*(x+1) == x*x+1'}),
            ('NONNEG', 'x*x+y*y >= 0 for every integer x,y', 'proofs/nonnegative.md',
             {'domain': 'INTEGER', 'variables': ['x', 'y'], 'preconditions': [], 'conclusion': 'x*x+y*y >= 0'}),
            ('LEAN-TARGET', 'Original quantified toy safety statement, not the proposition True', 'proofs/formal.md', None),
            ('LEAN-MISSING', 'Another original quantified toy safety statement', 'proofs/formal.md', None)):
            spec = {'schema_version': 1, 'id': cid, 'statement': text, 'assumptions': problem['assumptions'],
                'dependencies': [], 'proposer': 'fixture-proposer', 'problem_id': 'P-1', 'problem_version': 1,
                'obligation_ids': ['O-1'], 'nontriviality_argument': 'Infrastructure exact-verifier fixture only',
                'contribution_type': 'COMPLEXITY_THEOREM', 'evidence_paths': [evidence],
                'verification_mode': 'FORMAL_REQUIRED' if machine is None else 'INDEPENDENT_MANUAL',
                'formal_applicability_reason': 'Verify exact toy scope; no theorem acceptance from execution'}
            if machine:
                spec['machine_statement'] = machine
            else:
                spec['formal_target'] = {'file': 'proofs/lean/Weak.lean', 'declaration': 'weak_target'}
            write(file, spec)
            imported = invoke(['claim', 'import', 'alpha', '--file', str(file), '--reason', 'Register exact unreviewed toy claim'])
            claims[cid] = {'spec': spec, 'pin': {name: imported[name] for name in ('id', 'revision', 'spec_sha256')}}
        anchor = invoke(['candidate', 'anchor', 'alpha'])['goal_anchor_id']
        for claim_id, value in claims.items():
            candidate = {'schema_version': 1, 'id': 'C-' + claim_id, 'title': 'Exact toy candidate ' + claim_id,
                'goal_anchor_id': anchor, 'problem_id': 'P-1', 'problem_version': 1,
                'hypothesis': 'Exact toy construction relying on ' + claim_id + ' under original quantifiers',
                'nontriviality_argument': 'A test of scoped verification only',
                'closest_prior_work': [{'source_id': 'TOY-PAPER-1', 'check': 'Check exact source theorem and assumptions',
                                        'full_text_checked': False}],
                'falsification_gate': 'Find an exact scoped assignment contradicting this candidate dependency',
                'proof_obligations': ['O-1'], 'assumptions': problem['assumptions'],
                'immutable_constraints': problem['immutable_constraints'], 'domain': problem['domain'],
                'quantifiers': problem['quantifiers'], 'security_model': {}, 'estimated_context_bytes': 2048,
                'dependency_claims': [value['pin']], 'evidence_refs': [],
                'failure_scope': 'Only this exact toy predicate and original quantifiers',
                'restart_conditions': 'Explicit new version with independent review'}
            write(file, candidate)
            invoke(['candidate', 'propose', 'alpha', '--file', str(file), '--reason', 'Register unreviewed verifier fixture'])
        fixed_budget_paths = [root / 'state/routes', root / 'state/route_registry',
                              root / 'state/discovery', root / 'state/supervision']
        fixed_budgets = fingerprint(fixed_budget_paths, root)
        fixed_state, fixed_goal = (project / 'research/STATE.json').read_bytes(), (project / 'GOAL.md').read_bytes()

        def prepare(claim_id, adapter='integer-v1', extras=(), *, environment=None):
            return unchanged(['candidate', 'verify-prepare', 'alpha', '--id', 'C-' + claim_id,
                '--claim', claim_id, '--adapter', adapter, *extras], environment=environment)

        def execute(request, expected=0, *, environment=None):
            write(file, request)
            return unchanged(['candidate', 'verify', 'alpha', '--request', str(file)], expected,
                             environment=environment)

        false_request = prepare('POLY', extras=['--bounds', '-2', '2'])
        write(output / 'frozen-polynomial-request.json', false_request)
        false_result = execute(false_request)
        assert false_result['result_status'] == 'COUNTEREXAMPLE_FOUND', false_result
        write(output / 'normal-polynomial-counterexample.json', false_result)
        false_id = false_request['request_id']
        checked = unchanged(['candidate', 'verification-recheck', 'alpha', '--request-id', false_id])
        assert checked['fresh'] and checked['certificate_valid'] and not checked['recheck_execution_started'], checked
        assert checked['certificate_scope'] == 'EXACT_FROZEN_MACHINE_PREDICATE_ONLY'
        write(output / 'rechecked-machine-certificate.json', checked)
        before_allowed = (root / 'allowed-workers.jsonl').read_bytes()
        replay = execute(false_request)
        assert replay['result_status'] == 'COUNTEREXAMPLE_FOUND'
        assert before_allowed == (root / 'allowed-workers.jsonl').read_bytes(), 'Receipt replay reran a tool'

        true_request = prepare('NONNEG', extras=['--bounds', '-50', '49', '--max-cases', '10000'])
        write(output / 'frozen-bounded-request.json', true_request)
        true_result = execute(true_request)
        assert true_result['result_status'] == 'NO_COUNTEREXAMPLE_WITHIN_BOUND', true_result
        assert true_result['result']['tested_cases'] == 10000 and true_result['result']['witness'] is None, true_result
        assert not true_result['positive_basis'] and not true_result['scientific_acceptance']
        write(output / 'bounded-10000-not-proof.json', true_result)
        unchanged(['candidate', 'verification-recheck', 'alpha', '--request-id', true_request['request_id']])

        # A nonexecuted marker only controls shutil.which; arbitrary subprocess
        # guards would reject running it, and no Lean/Lake/version probe occurs.
        marker = root / 'tool-marker'
        marker.mkdir()
        if os.name == 'nt':
            write(marker / 'elan.cmd', '@echo off\nexit /b 99\n')
        else:
            write(marker / 'elan', '#!/bin/sh\nexit 99\n')
            (marker / 'elan').chmod(0o700)
        marker_env = dict(env, PATH=str(marker) + os.pathsep + str(root))
        lean_request = prepare('LEAN-TARGET', adapter='lean-v1',
            extras=['--proof-file', 'proofs/lean/Weak.lean', '--declaration', 'weak_target'], environment=marker_env)
        write(output / 'frozen-lean-request.json', lean_request)
        write(output / 'weak-target-not-executed.lean', (project / 'proofs/lean/Weak.lean').read_text(encoding='utf8'))
        lean_result = execute(lean_request, expected=2, environment=marker_env)
        assert lean_result['result_status'] == 'UNSUPPORTED', lean_result
        assert lean_result['tool_status'] == 'ISOLATION_UNCERTIFIED' and not lean_result['execution_started'], lean_result
        assert 'TRIVIAL_TRUE_DECLARATION' in lean_result['diagnostics']
        assert lean_result['statement_match'] == 'REQUIRES_INDEPENDENT_REVIEW'
        write(output / 'lean-blocked-weak-statement.json', lean_result)
        missing_request = prepare('LEAN-MISSING', adapter='lean-v1',
            extras=['--proof-file', 'proofs/lean/Weak.lean', '--declaration', 'weak_target'])
        missing = execute(missing_request, expected=2)
        assert missing['result_status'] == 'UNSUPPORTED', missing
        assert missing['tool_status'] == 'UNAVAILABLE' and not missing['execution_started'], missing
        assert missing['result']['preflight']['status'] == 'UNAVAILABLE'
        write(output / 'lean-unavailable-simulation.json', missing)

        unknown_request = prepare('NONNEG', adapter='not-supported-v1')
        unknown = execute(unknown_request, expected=2)
        assert unknown['result_status'] == 'UNSUPPORTED'
        write(output / 'unknown-adapter-rejection.json', unknown)
        # Explicit fixture evidence change; the adapter must preserve this state.
        write(project / 'proofs/polynomial.md', 'Changed exact toy source after the frozen verification request.\n')
        stale_source = unchanged(['candidate', 'verification-recheck', 'alpha', '--request-id', false_id], expected=2)
        assert stale_source['result_status'] == 'FAILED'
        stale_execution = execute(false_request, expected=2)
        assert stale_execution['result_status'] == 'FAILED'
        write(output / 'source-sha-expiration.json', {'recheck': stale_source, 'old_request': stale_execution})
        # Only the old explicit claim import changes the authority revision.
        changed_claim = copy.deepcopy(claims['NONNEG']['spec'])
        changed_claim['statement'] += ' Revised operator-owned statement.'
        write(file, changed_claim)
        invoke(['claim', 'import', 'alpha', '--file', str(file), '--reason', 'Explicit exact toy statement revision'])
        stale_revision = unchanged(['candidate', 'verification-recheck', 'alpha',
            '--request-id', true_request['request_id']], expected=2)
        assert stale_revision['result_status'] == 'FAILED'
        write(output / 'claim-revision-expiration.json', stale_revision)
        historical = unchanged(['candidate', 'verification-show', 'alpha', '--request-id', true_request['request_id']])
        assert not historical['fresh'] and not historical['positive_basis']
        write(output / 'historical-stale-receipt.json', historical)
        audit = [json.loads(line) for line in (root / 'allowed-workers.jsonl').read_text(encoding='utf8').splitlines()]
        assert len(audit) == 2, audit
        assert fixed_budgets == fingerprint(fixed_budget_paths, root)
        assert (project / 'research/STATE.json').read_bytes() == fixed_state
        assert (project / 'GOAL.md').read_bytes() == fixed_goal
        assert not (root / 'forbidden-execution.jsonl').exists(), 'A forbidden process or network operation was attempted'
        write(output / 'execution-audit.json', {'allowed_integer_workers': audit, 'denied_operations': [],
            'provider_requests': 0, 'network_requests': 0, 'lean_executions': 0, 'supervision_executions': 0})
        receipt.update(steps_count=len(receipt['steps']), trusted_integer_worker_processes=len(audit),
            exact_counterexample_rechecked=True, bounded_no_counterexample_is_not_proof=True,
            lean_and_semantic_acceptance_blocked=True, missing_tool_recorded_without_execution=True,
            source_sha_and_claim_revision_expire_receipts=True, receipt_replay_never_reexecutes=True,
            no_canonical_verifier_writes=True, original_budgets_and_state_preserved=True, scientific_discovery=False)
        write(output / 'acceptance.json', receipt)
        print(json.dumps({key: value for key, value in receipt.items() if key != 'steps'}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
