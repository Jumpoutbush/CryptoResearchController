"""R12 native CLI acceptance using disposable fixtures and original local receipts.

No personal project is copied. Audit guards deny provider, network, Lean and
supervision execution inside the controller children. Fake run identifiers below
are settled through the existing local begin/finish APIs, never model calls.
"""
from __future__ import annotations

import argparse
import copy
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
    receipt = {'round': 'R12', 'fixture_only': True, 'provider_requests': 0, 'network_requests': 0,
               'lean_executions': 0, 'supervision_executions': 0, 'steps': []}
    with tempfile.TemporaryDirectory(prefix='crc r12 native fixture ') as directory:
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
        # Two simulated NO_PROGRESS acceptances must remain below the support
        # review threshold so the normal scheduler path can then be exercised.
        research_policy = json.loads((root / 'config/research_policy.json').read_text(encoding='utf-8-sig'))
        research_policy['max_consecutive_support_rounds'] = 3
        write(root / 'config/research_policy.json', research_policy)
        write(root / 'sitecustomize.py', """import os, sys
def guard(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo', 'subprocess.Popen',
                 'os.system', 'os.exec', 'os.posix_spawn', 'os.spawn'}:
        with open(os.environ['CRC_R12_AUDIT_LOG'], 'a', encoding='utf8') as log:
            log.write(event + '\\n')
        raise RuntimeError('R12 fixture forbids network/provider/Lean execution: ' + event)
sys.addaudithook(guard)
""")
        env = dict(os.environ, CRC_PYTHON=sys.executable, PYTHONDONTWRITEBYTECODE='1',
            PYTHONIOENCODING='utf8', PYTHONPATH=str(root), PYTHONNOUSERSITE='1',
            PATH=str(root) + os.pathsep + os.environ.get('PATH', ''),
            CRC_R12_AUDIT_LOG=str(root / 'forbidden-execution.jsonl'))
        entry = (['cmd.exe', '/d', '/c', 'research.cmd'] if os.name == 'nt'
                 else [sys.executable, '-B', str(root / 'research.py')])
        receipt['entry'] = 'research.cmd' if os.name == 'nt' else 'research.py'
        receipt['child_execution_guard'] = 'Python audit hook denies network and nested process execution'

        def record(args, result, expected):
            item = {'args': args, 'exit_code': result.returncode, 'expected_exit_code': expected,
                    'stdout': result.stdout, 'stderr': result.stderr}
            receipt['steps'].append(item)
            assert result.returncode == expected, item
            return json.loads(result.stdout) if expected == 0 else result.stdout + result.stderr

        def invoke(args, expected=0, *, cwd=root):
            result = subprocess.run(entry + args, cwd=cwd, env=env, capture_output=True,
                                    text=True, encoding='utf8', timeout=60)
            return record(args, result, expected)

        authorities = [root / 'projects', root / 'state/routes', root / 'state/route_registry',
            root / 'state/discovery', root / 'state/supervision', root / 'state/research_acceptance', root / 'config']

        def protected():
            return fingerprint(authorities, root)

        def unchanged_call(args, expected=0):
            before = protected()
            value = invoke(args, expected=expected)
            assert protected() == before, 'Candidate operation changed original research authority'
            return value

        project = root / 'projects/alpha'
        problem = {'schema_version': 1, 'id': 'P-1', 'title': 'Frozen exact integer toy problem',
            'statement': 'For every toy integer x, x*x >= 0', 'quantifiers': 'for all toy integers x',
            'domain': 'integers', 'input_contract': 'A toy integer x', 'output_contract': 'Exact toy inequality',
            'goal_connection': 'The exact frozen toy target only',
            'nontriviality_argument': 'Infrastructure fixture; no scientific or novelty claim',
            'assumptions': ['Exact integer arithmetic'], 'immutable_constraints': ['Keep all original quantifiers'],
            'baseline_exclusions': ['No new theorem claim'], 'contribution_type': 'COMPLEXITY_THEOREM',
            'source_paths': [], 'obligations': [{'id': 'O-1', 'statement': 'Exact original inequality',
                'acceptance_criterion': 'Independent toy statement and argument review'}]}

        def setup(key, *, decision='CONTINUE', consumed=0, review=False):
            target = root / 'projects' / key
            state = {'phase': 'PROOF', 'decision': decision, 'research_route': 'MAIN', 'selected_idea': None,
                'last_run': f'toy-r{consumed}' if consumed else None,
                'priority_problem': 'Frozen toy obligation', 'next_task': 'Resolve exact toy obligation'}
            for rel, value in {'PROJECT.json': {'id': key, 'checks': []},
                'GOAL.md': 'Frozen exact toy integer target; no theorem claimed.\n',
                'AGENTS.md': 'Infrastructure-only toy example; preserve exact goal and models.\n',
                'RESEARCH_PROFILE.json': {'profiles': [], 'read_order': []},
                'research/STATE.json': state, 'proofs/argument.md': 'Unreviewed exact toy argument only.\n',
                'literature/nearest.md': 'Synthetic full-text check pending.\n'}.items():
                write(target / rel, value)
            spec_file = root / ('problem-' + key + '.json')
            write(spec_file, problem)
            invoke(['problem', 'import', key, '--file', str(spec_file), '--reason', 'Register isolated toy problem'])
            runs = [f'toy-r{i}' for i in range(1, consumed + 1)]
            epoch = {'epoch': 1, 'route': 'MAIN', 'effective_rounds': consumed, 'stagnation': 0,
                'extensions_used': 0, 'counted_run_ids': runs, 'last_processed_run': runs[-1] if runs else None,
                'review_pending': review, 'review_reason': 'fixture_review' if review else None,
                'focus': make_focus(target, state)}
            route_budget.save_ledger(root / 'state/routes' / (key + '.json'),
                {'schema_version': 1, 'project_id': key, 'epochs': [epoch],
                 'events': [{'type': 'RESEARCH_ROUND', 'run_id': run} for run in runs]})
            return target

        setup('alpha')
        helper = root / 'local-receipt-fixture.py'
        write(helper, """import sys,json,contextlib,io
import configuration,runner,route_budget
from engine import discovery_scheduler as original
project=configuration.ROOT/'projects/alpha'
with route_budget.file_lock(configuration.ROOT/'locks/route-alpha.lock'), route_budget.file_lock(configuration.ROOT/'locks/alpha.lock'):
    if sys.argv[1]=='record-two':
        policy,_,_=route_budget.policy_for(configuration.ROOT,project)
        path,ledger,epoch=route_budget.load_ledger(configuration.ROOT,project,route_budget.state_read(project))
        counts=[epoch['effective_rounds']]
        for run_id in ('toy-r1','toy-r2'):
            before=route_budget.evidence_snapshot(project)
            state=route_budget.state_read(project);state['last_run']=run_id
            configuration.atomic_json(project/'research/STATE.json',state)
            configuration.atomic_json(project/'research/ROUND_REVIEW.json',{
                'schema_version':1,'run_id':run_id,'work_kind':'CORE_RESEARCH','result_status':'NO_PROGRESS',
                'core_problem':'Infrastructure acceptance of the unchanged toy obligation',
                'theoretical_obligation':'No theorem or mathematical progress claimed',
                'nontriviality_argument':'Offline controller accounting simulation only',
                'contribution_type':'NONE','evidence_paths':[]})
            configuration.atomic_json(project/'research/ROUTE_SIGNAL.json',{'run_id':run_id,
                'progress_type':'NO_PROGRESS','reason':'Synthetic controller accounting acceptance without any model or research execution.',
                'evidence_paths':[],'route_blocked':False})
            with contextlib.redirect_stdout(io.StringIO()):runner.record_round(project,ledger,epoch,policy,state,before)
            route_budget.save_ledger(path,ledger);counts.append(epoch['effective_rounds'])
        print(json.dumps({'fixture_only':True,'operation':'original_runner_record_round','effective_counts':counts,
            'counted_run_ids':epoch['counted_run_ids'],'scientific_progress':False}))
    else:
        if sys.argv[1]=='begin':original.begin_call(project,sys.argv[2])
        else:original.finish_call(project,sys.argv[2],accepted=False)
        print(json.dumps({'fixture_only':True,'operation':sys.argv[1],'run_id':sys.argv[2]}))
""")

        def original_receipt(operation, run_id='fixture-only'):
            result = subprocess.run([sys.executable, '-B', str(helper), operation, run_id], cwd=root,
                env=env, capture_output=True, text=True, encoding='utf8', timeout=60)
            return record(['python', '-B', helper.name, operation, run_id], result, 0)

        growth = original_receipt('record-two')
        assert growth['effective_counts'] == [0, 1, 2]
        assert growth['counted_run_ids'] == ['toy-r1', 'toy-r2']
        write(output / 'original-controller-route-accounting.json', growth)
        claim = {'schema_version': 1, 'id': 'TOY-PREDICATE', 'statement': problem['statement'],
            'assumptions': problem['assumptions'], 'dependencies': [], 'proposer': 'fixture-proposer',
            'problem_id': 'P-1', 'problem_version': 1, 'obligation_ids': ['O-1'],
            'nontriviality_argument': 'Toy exact computation fixture only', 'contribution_type': 'COMPLEXITY_THEOREM',
            'evidence_paths': ['proofs/argument.md'], 'verification_mode': 'INDEPENDENT_MANUAL',
            'formal_applicability_reason': 'No Lean execution in this fixture',
            'machine_statement': {'domain': 'INTEGER', 'variables': ['x'], 'preconditions': [], 'conclusion': 'x*x >= 0'}}
        file = root / 'claim.json'
        write(file, claim)
        imported = invoke(['claim', 'import', 'alpha', '--file', str(file), '--reason', 'Register unreviewed computable toy predicate'])
        claim_pin = {name: imported[name] for name in ('id', 'revision', 'spec_sha256')}
        anchor = unchanged_call(['candidate', 'anchor', 'alpha'])['goal_anchor_id']

        def card(cid, *, context=4096, dependencies=None):
            return {'schema_version': 1, 'id': cid, 'title': 'Toy construction ' + cid,
                'goal_anchor_id': anchor, 'problem_id': 'P-1', 'problem_version': 1,
                'hypothesis': 'Exact toy construction ' + cid + ' resolves the frozen integer obligation',
                'nontriviality_argument': 'A falsifiable structural toy hypothesis only',
                'closest_prior_work': [{'source_id': 'TOY-PAPER-1', 'check': 'Check exact theorem scope in original text',
                                        'full_text_checked': False}],
                'falsification_gate': 'Check the exact toy integer predicate on the original finite test range',
                'proof_obligations': ['O-1'], 'assumptions': problem['assumptions'],
                'immutable_constraints': problem['immutable_constraints'], 'domain': problem['domain'],
                'quantifiers': problem['quantifiers'], 'security_model': {}, 'estimated_context_bytes': context,
                'dependency_claims': dependencies or [], 'evidence_refs': [],
                'failure_scope': 'Only this exact toy construction',
                'restart_conditions': 'A new explicitly versioned independent structural assumption'}

        for number in range(1, 4):
            value = card(f'C-{number:04d}', context=1 if number == 1 else 8192,
                         dependencies=[claim_pin] if number == 2 else [])
            write(file, value)
            unchanged_call(['candidate', 'propose', 'alpha', '--file', str(file), '--reason', 'Register toy branch'])
            unchanged_call(['candidate', 'status', 'alpha', '--id', value['id'], '--status', 'SCREENING',
                            '--expected-revision', '1', '--reason', 'Screen exact toy branch'])
        unchanged_call(['candidate', 'status', 'alpha', '--id', 'C-0001', '--status', 'READY_FOR_ATTEMPT',
                        '--expected-revision', '1', '--reason', 'Prepare exact no-dependency toy branch for operator binding'])
        before = fingerprint([root], root)
        plan = invoke(['candidate', 'plan', 'alpha', '--dry-run'])
        assert before == fingerprint([root], root), 'Dry-run plan wrote local state'
        assert plan == invoke(['candidate', 'plan', 'alpha', '--dry-run'])
        assert plan == invoke(['candidate', 'plan', '--dry-run'], cwd=project)
        assert plan['next_candidate'] == 'C-0002', plan
        assert plan['route_budget']['effective_rounds'] == 2 and plan['route_budget']['remaining_rounds'] == 4
        write(output / 'normal-deterministic-plan.json', plan)
        plan_file = root / 'plan.json'
        write(plan_file, plan)
        args = ['candidate', 'select', 'alpha', '--id', 'C-0002', '--expected-revision', '1',
                '--plan-file', str(plan_file), '--reason', 'Select exact computable falsification task']
        # Separate OS processes compete through the real controller entry.
        before = protected()
        processes = [subprocess.Popen(entry + args, cwd=root, env=env, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True, encoding='utf8') for _ in range(2)]
        concurrent = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=60)
            item = {'args': args, 'exit_code': process.returncode, 'stdout': stdout, 'stderr': stderr}
            receipt['steps'].append(item)
            assert process.returncode in {0, 2}, item
            concurrent.append(item)
        successes = [json.loads(item['stdout']) for item in concurrent if item['exit_code'] == 0]
        assert successes, concurrent
        ids = {item['selection']['selection_id'] for item in successes}
        assert len(ids) == 1, 'Concurrent selectors created multiple grants'
        selection_id = next(iter(ids))
        assert protected() == before
        replay = unchanged_call(args)
        assert replay['selection']['selection_id'] == selection_id and replay['idempotent']
        scheduling = unchanged_call(['candidate', 'schedule-status', 'alpha'])
        assert len(scheduling['selections']) == 1
        write(output / 'concurrent-selectors.json', {'processes': concurrent, 'status': scheduling})
        write(output / 'idempotent-selection.json', replay)
        duplicate = card('C-RENAMED', context=1)
        duplicate['hypothesis'] = card('C-0001')['hypothesis']
        write(file, duplicate)
        error = unchanged_call(['candidate', 'propose', 'alpha', '--file', str(file), '--reason', 'Attempt renamed budget reset'], expected=2)
        assert 'DUPLICATE' in error
        assert unchanged_call(['candidate', 'plan', 'alpha', '--dry-run'])['route_budget'] == plan['route_budget']

        # Explicit original API calls are fixture-only fault setup, not research.
        route_before = fingerprint([root / 'state/routes', root / 'state/route_registry'], root)
        first_attempt = invoke(['attempt', 'start', 'alpha', '--problem', 'P-1', '--version', '1'])
        first_id = first_attempt['id']
        deferred = unchanged_call(['candidate', 'plan', 'alpha', '--dry-run'])
        assert deferred['status'] == 'DEFERRED_UNTIL_ATTEMPT_CLOSE', deferred
        assert unchanged_call(['attempt', 'status', 'alpha'])['active_attempt'] == first_id
        write(output / 'active-attempt-deferral.json', deferred)
        unchanged_call(args, expected=2)
        original_receipt('begin', 'fixture-unbound-failure')
        retroactive = unchanged_call(['candidate', 'bind-attempt', 'alpha', '--selection-id', selection_id,
            '--attempt-id', first_id, '--reason', 'Fault injection: bind after an original call exists'], expected=2)
        write(output / 'retroactive-owner-rejection.json', {'diagnostic': retroactive})
        original_receipt('finish', 'fixture-unbound-failure')
        invoke(['attempt', 'close', 'alpha', '--reason', 'Explicit operator close of isolated first toy attempt'])
        second_plan = unchanged_call(['candidate', 'plan', 'alpha', '--dry-run'])
        write(plan_file, second_plan)
        second_args = list(args)
        second_args[second_args.index('C-0002')] = 'C-0001'
        second_selection = unchanged_call(second_args)
        second_sid = second_selection['selection']['selection_id']
        second_attempt = invoke(['attempt', 'start', 'alpha', '--problem', 'P-1', '--version', '1'])
        second_id = second_attempt['id']
        bound = unchanged_call(['candidate', 'bind-attempt', 'alpha', '--selection-id', second_sid,
            '--attempt-id', second_id, '--reason', 'Freeze candidate ownership before any original call'])
        write(output / 'explicit-before-call-binding.json', bound)
        original_receipt('begin', 'fixture-bound-failure')
        mapping_args = ['candidate', 'map-run', 'alpha', '--selection-id', second_sid,
            '--attempt-id', second_id, '--run-id', 'fixture-bound-failure', '--reason', 'Map original synthetic failed receipt only']
        unknown = unchanged_call(mapping_args, expected=2)
        assert 'UNKNOWN' in unknown or 'PENDING' in unknown, unknown
        write(output / 'unknown-result-rejection.json', {'diagnostic': unknown})
        original_receipt('finish', 'fixture-bound-failure')
        mapped = unchanged_call(mapping_args)
        mapping_replay = unchanged_call(mapping_args)
        assert mapped['mapping'] == mapping_replay['mapping'] and mapping_replay['idempotent'], 'Mapping replay created a new receipt'
        assert mapped['mapping']['call_status'] == 'FAILED' and not mapped['mapping']['new_budget_charge']
        write(output / 'trusted-failed-run-mapping.json', mapped)
        assert route_before == fingerprint([root / 'state/routes', root / 'state/route_registry'], root)

        # Independent fault projects avoid restoring or rolling back any authority.
        blocked = {}
        for key, options in (('stopped', {'decision': 'STOP'}), ('reviewing', {'review': True}),
                             ('exhausted', {'consumed': 6})):
            target = setup(key, **options)
            anchor_value = unchanged_call(['candidate', 'anchor', key])['goal_anchor_id']
            value = card('C-0001')
            value['goal_anchor_id'] = anchor_value
            write(file, value)
            unchanged_call(['candidate', 'propose', key, '--file', str(file), '--reason', 'Register isolated blocked fixture'])
            blocked_plan = unchanged_call(['candidate', 'plan', key, '--dry-run'])
            assert blocked_plan['status'] in {'STOPPED', 'ROUTE_REVIEW_REQUIRED'}, blocked_plan
            fault_plan = root / (key + '-plan.json')
            write(fault_plan, blocked_plan)
            diagnostic = unchanged_call(['candidate', 'select', key, '--id', 'C-0001', '--expected-revision', '1',
                '--plan-file', str(fault_plan), '--reason', 'Fault injection: blocked branch selection'])
            assert diagnostic['selected'] is False and not diagnostic['execution_allowed']
            blocked[key] = {'plan': blocked_plan, 'rejection': diagnostic}
        write(output / 'stop-review-exhaustion-rejections.json', blocked)
        # A fourth PROPOSED record is retained, but cannot expand the bounded
        # scheduler window or be selected by directly naming its ID.
        setup('frontier')
        frontier_anchor = unchanged_call(['candidate', 'anchor', 'frontier'])['goal_anchor_id']
        for number in range(1, 5):
            value = card(f'F-{number:04d}')
            value['goal_anchor_id'] = frontier_anchor
            write(file, value)
            unchanged_call(['candidate', 'propose', 'frontier', '--file', str(file), '--reason', 'Bounded frontier fixture candidate'])
            if number < 4:
                unchanged_call(['candidate', 'status', 'frontier', '--id', value['id'], '--status', 'SCREENING',
                    '--expected-revision', '1', '--reason', 'Preserve an existing active frontier slot'])
        frontier_plan = unchanged_call(['candidate', 'plan', 'frontier', '--dry-run'])
        assert len(frontier_plan['rankings']) == 3
        assert {item['candidate_id'] for item in frontier_plan['rankings']} == {'F-0001', 'F-0002', 'F-0003'}
        assert [item['candidate_id'] for item in frontier_plan['deferred_candidates']] == ['F-0004']
        frontier_file = root / 'frontier-plan.json'
        write(frontier_file, frontier_plan)
        frontier_error = unchanged_call(['candidate', 'select', 'frontier', '--id', 'F-0004', '--expected-revision', '1',
            '--plan-file', str(frontier_file), '--reason', 'Fault injection: select outside the bounded frontier'], expected=2)
        assert 'OUTSIDE_SCHEDULING_FRONTIER' in frontier_error
        write(output / 'bounded-frontier-rejection.json', {'plan': frontier_plan, 'rejection': frontier_error})
        assert not (root / 'forbidden-execution.jsonl').exists(), 'Attempted forbidden network or tool execution'
        receipt.update(steps_count=len(receipt['steps']), deterministic_falsification_priority=True,
            cheap_unsafe_candidate_not_preferred=True, one_authoritative_route_budget=True,
            candidate_registration_never_resets_budget=True, concurrent_single_selection_grant=True,
            idempotent_select_and_mapping=True, active_attempt_deferred=True,
            no_automatic_attempt_start_close_or_problem_import=True, retroactive_binding_rejected=True,
            unknown_external_outcome_mapping_blocked=True, trusted_original_failed_receipt_only=True,
            stop_review_and_exhaustion_blocked=True, original_route_budget_unchanged=True,
            at_most_three_scheduled_candidates=True, outside_frontier_selection_rejected=True,
            candidate_operations_preserve_scientific_and_budget_authority=True, scientific_discovery=False)
        write(output / 'acceptance.json', receipt)
        print(json.dumps({key: value for key, value in receipt.items() if key != 'steps'}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
