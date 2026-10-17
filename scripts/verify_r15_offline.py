"""R15 branch-resolution acceptance through a disposable real controller.

The only nested program permitted in controller children is the fixed R13
integer data worker. All original route accounting uses the existing runner;
there are no provider requests or real scientific, Lean or supervision rounds.
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
    receipt = {'round': 'R15', 'fixture_only': True, 'provider_requests': 0,
        'network_requests': 0, 'lean_executions': 0, 'supervision_executions': 0, 'steps': []}
    with tempfile.TemporaryDirectory(prefix='crc r15 native fixture ') as directory:
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
        research_policy = json.loads((root / 'config/research_policy.json').read_text(encoding='utf-8-sig'))
        research_policy['max_consecutive_support_rounds'] = 4
        write(root / 'config/research_policy.json', research_policy)
        worker = root / 'candidate_search/verifiers/trusted_integer_worker.py'
        worker_sha = hashlib.sha256(worker.read_bytes()).hexdigest()
        write(root / 'sitecustomize.py', """import os,sys,json,hashlib,subprocess
from pathlib import Path
def guard(event,args):
    if event=='subprocess.Popen':
        expected=[sys.executable,'-I','-B',os.environ['CRC_R15_WORKER']]
        argv=args[1];source=Path(os.environ['CRC_R15_WORKER'])
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        cwd=Path(args[2]) if args[2] is not None else None
        environment=args[3]
        argv_matches=(argv==expected if isinstance(argv,list) else
            isinstance(argv,str) and argv==subprocess.list2cmdline(expected))
        if (argv_matches and args[0] in {None,sys.executable}
                and digest==os.environ['CRC_R15_WORKER_SHA'] and cwd is not None
                and cwd.name.startswith('crc trusted integer ') and not any(cwd.iterdir())
                and isinstance(environment,dict) and set(environment)<={'SYSTEMROOT','WINDIR','TEMP','TMP'}):
            with open(os.environ['CRC_R15_ALLOWED_LOG'],'a',encoding='utf8') as log:
                log.write(json.dumps({'argv':argv,'worker_sha256':digest,'empty_workdir':True,
                    'environment_keys':sorted(environment),'os_sandbox_certified':False})+'\\n')
            return
    elif event not in {'socket.connect','socket.getaddrinfo','os.system','os.exec','os.posix_spawn','os.spawn'}:
        return
    with open(os.environ['CRC_R15_DENIED_LOG'],'a',encoding='utf8') as log:log.write(event+'\\n')
    raise RuntimeError('R15 fixture forbids network or arbitrary nested execution: '+event)
sys.addaudithook(guard)
""")
        env = dict(os.environ, CRC_PYTHON=sys.executable, PYTHONDONTWRITEBYTECODE='1',
            PYTHONIOENCODING='utf8', PYTHONPATH=str(root), PYTHONNOUSERSITE='1', PATH=str(root),
            CRC_R15_WORKER=str(worker), CRC_R15_WORKER_SHA=worker_sha,
            CRC_R15_ALLOWED_LOG=str(root / 'allowed-workers.jsonl'),
            CRC_R15_DENIED_LOG=str(root / 'forbidden-execution.jsonl'))
        entry = ([os.environ.get('COMSPEC', r'C:\Windows\System32\cmd.exe'), '/d', '/c', 'research.cmd']
                 if os.name == 'nt' else [sys.executable, '-B', str(root / 'research.py')])
        receipt['entry'] = 'research.cmd' if os.name == 'nt' else 'research.py'

        def record(args, result, expected):
            item = {'args': args, 'exit_code': result.returncode, 'expected_exit_code': expected,
                    'stdout': result.stdout, 'stderr': result.stderr}
            receipt['steps'].append(item)
            write(output / 'in-progress.json', receipt)
            assert result.returncode == expected, item
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                if expected == 0:
                    raise
                return {'diagnostic': result.stdout + result.stderr}

        def invoke(args, expected=0, *, cwd=root):
            result = subprocess.run(entry + args, cwd=cwd, env=env, capture_output=True,
                                    text=True, encoding='utf8', timeout=60)
            return record(args, result, expected)

        def helper_run(operation, *arguments, expected=0):
            result = subprocess.run([sys.executable, '-B', str(helper), operation, *arguments],
                cwd=root, env=env, capture_output=True, text=True, encoding='utf8', timeout=60)
            return record(['python', '-B', helper.name, operation, *arguments], result, expected)

        project = root / 'projects/alpha'
        state = {'phase': 'PROOF', 'decision': 'CONTINUE', 'research_route': 'MAIN', 'selected_idea': None,
            'last_run': None, 'priority_problem': 'Exact integer square expansion',
            'next_task': 'Resolve exact square expansion without changing the original goal',
            'accepted_contribution': {'status': 'NOT_ESTABLISHED', 'fixture_sentinel': 'retain'}}
        for relative, value in {'PROJECT.json': {'id': 'alpha', 'checks': []},
            'GOAL.md': 'Find the exact integer polynomial expansion of (x+1)*(x+1); preserve all integer inputs.\n',
            'AGENTS.md': 'Synthetic infrastructure acceptance only; never claim novelty or a new theorem.\n',
            'RESEARCH_PROFILE.json': {'profiles': [], 'read_order': []}, 'research/STATE.json': state,
            'proofs/branch-a.md': 'Candidate A proposes (x+1)*(x+1) == x*x+1 for every integer x.\n',
            'proofs/branch-b.md': 'Candidate B retains the middle term: x*x+2*x+1; proof pending.\n',
            'proofs/support.md': 'For every integer x, x*(x+1)=x*x+x by distributivity and x*1=x.\n',
            'research/support-review.md': 'Independent toy operator check: distribute the left factor and use x*1=x; the exact integer domain and universal quantifier are unchanged. This is not a novelty review.\n',
            'literature/nearest.md': 'Original synthetic arithmetic note. Squaring a sum requires checking its middle term.\n',
            'research/GATES.json': {'G8': 'INDEPENDENT_REVIEW_REQUIRED', 'fixture_sentinel': 'retain'},
            'research/accepted_contribution.json': {'accepted': False, 'fixture_sentinel': 'retain'}}.items():
            write(project / relative, value)
        epoch = {'epoch': 1, 'route': 'MAIN', 'effective_rounds': 0, 'stagnation': 0, 'extensions_used': 0,
            'counted_run_ids': [], 'last_processed_run': None, 'review_pending': False,
            'focus': make_focus(project, state)}
        route_budget.save_ledger(root / 'state/routes/alpha.json', {'schema_version': 1, 'project_id': 'alpha',
            'epochs': [epoch], 'events': []})
        problem = {'schema_version': 1, 'id': 'P-1', 'title': 'Exact integer square expansion',
            'statement': 'Find the exact expansion of (x+1)*(x+1) for every integer x',
            'quantifiers': 'for every integer x', 'domain': 'integers',
            'input_contract': 'An arbitrary original integer x', 'output_contract': 'The exact polynomial identity',
            'goal_connection': 'The original frozen integer square target',
            'nontriviality_argument': 'Controller fixture only; no mathematical novelty assertion',
            'assumptions': ['Exact integer arithmetic'], 'immutable_constraints': ['Keep every integer input'],
            'baseline_exclusions': ['No novelty or cryptographic security assertion'],
            'contribution_type': 'COMPLEXITY_THEOREM', 'source_paths': ['literature/nearest.md'],
            'obligations': [{'id': 'O-1', 'statement': 'Exact original square expansion identity',
                'acceptance_criterion': 'Independent statement and proof correspondence review'}]}
        input_file = root / 'input.json'
        write(input_file, problem)
        invoke(['problem', 'import', 'alpha', '--file', str(input_file), '--reason', 'Register original synthetic problem'])
        claims = {}
        for cid, text, evidence, machine in (
            ('CLAIM-A', 'For every integer x, (x+1)*(x+1) == x*x+1', 'proofs/branch-a.md',
             {'domain': 'INTEGER', 'variables': ['x'], 'preconditions': [], 'conclusion': '(x+1)*(x+1) == x*x+1'}),
            ('SUPPORT', 'For every integer x, x*(x+1) == x*x+x', 'proofs/support.md',
             {'domain': 'INTEGER', 'variables': ['x'], 'preconditions': [], 'conclusion': 'x*(x+1) == x*x+x'})):
            claim = {'schema_version': 1, 'id': cid, 'statement': text, 'assumptions': problem['assumptions'],
                'dependencies': [], 'proposer': 'fixture-proposer', 'problem_id': 'P-1', 'problem_version': 1,
                'obligation_ids': ['O-1'], 'nontriviality_argument': 'Synthetic candidate-scope fixture only',
                'contribution_type': 'COMPLEXITY_THEOREM', 'evidence_paths': [evidence],
                'verification_mode': 'INDEPENDENT_MANUAL', 'formal_applicability_reason': 'No real Lean execution',
                'machine_statement': machine}
            write(input_file, claim)
            imported = invoke(['claim', 'import', 'alpha', '--file', str(input_file), '--reason', 'Import unreviewed toy claim'])
            claims[cid] = {name: imported[name] for name in ('id', 'revision', 'spec_sha256')}
        reviewed_support = invoke(['claim', 'review', 'alpha', '--id', 'SUPPORT', '--kind', 'proof_and_statement',
            '--evidence', 'research/support-review.md', '--reviewer', 'fixture-independent-operator',
            '--reason', 'Check exact elementary distributivity lemma; no novelty assertion'])
        support_status = next(value for value in reviewed_support['claims'] if value['id'] == 'SUPPORT')
        assert support_status['proof_status'] == 'INDEPENDENTLY_REVIEWED' and not support_status['accepted_contribution']
        anchor = invoke(['candidate', 'anchor', 'alpha'])['goal_anchor_id']
        candidates = {}
        for cid, hypothesis in [('C-A', 'For every integer x, (x+1)*(x+1) == x*x+1'),
                                ('C-B', 'For every integer x, (x+1)*(x+1) == x*x+2*x+1'),
                                ('C-RETIRED', 'Use an abandoned coefficient-table construction for the exact integer square target')]:
            candidate = {'schema_version': 1, 'id': cid, 'title': 'Synthetic square-expansion branch ' + cid,
                'goal_anchor_id': anchor, 'problem_id': 'P-1', 'problem_version': 1,
                'hypothesis': hypothesis, 'nontriviality_argument': 'Test of scoped branch management only',
                'closest_prior_work': [{'source_id': 'TOY-NOTE', 'check': 'Check the middle term in original toy note',
                                        'full_text_checked': False}],
                'falsification_gate': 'Find the smallest absolute integer contradicting the exact proposed identity',
                'proof_obligations': ['O-1'], 'assumptions': problem['assumptions'],
                'immutable_constraints': problem['immutable_constraints'], 'domain': problem['domain'],
                'quantifiers': problem['quantifiers'], 'security_model': {}, 'estimated_context_bytes': 2048,
                'dependency_claims': [claims['SUPPORT']] if cid == 'C-B' else [],
                'evidence_refs': [], 'failure_scope': 'This exact local construction only',
                'restart_conditions': 'Changed hypothesis and a fresh independent scope review'}
            candidates[cid] = candidate
            write(input_file, candidate)
            invoke(['candidate', 'propose', 'alpha', '--file', str(input_file), '--reason', 'Register distinct synthetic branch'])
            if cid != 'C-RETIRED':
                invoke(['candidate', 'status', 'alpha', '--id', cid, '--status', 'READY_FOR_ATTEMPT',
                        '--expected-revision', '1', '--reason', 'Structurally complete exact toy candidate; no scientific acceptance'])

        helper = root / 'original-engine-fixture.py'
        write(helper, """import sys,json,contextlib,io
import configuration,runner,route_budget
from engine import discovery_scheduler as original
from engine.common import ledger
project=configuration.ROOT/'projects/alpha'
with route_budget.file_lock(configuration.ROOT/'locks/route-alpha.lock'), route_budget.file_lock(configuration.ROOT/'locks/alpha.lock'):
    operation=sys.argv[1]
    if operation=='record-round':
        policy,_,_=route_budget.policy_for(configuration.ROOT,project)
        path,data,epoch=route_budget.load_ledger(configuration.ROOT,project,route_budget.state_read(project))
        before=route_budget.evidence_snapshot(project);prior=epoch['effective_rounds'];run_id=sys.argv[2]
        state=route_budget.state_read(project);state['last_run']=run_id
        configuration.atomic_json(project/'research/STATE.json',state)
        configuration.atomic_json(project/'research/ROUND_REVIEW.json',{
            'schema_version':1,'run_id':run_id,'work_kind':'CORE_RESEARCH','result_status':'NO_PROGRESS',
            'core_problem':'Exact original toy square expansion',
            'theoretical_obligation':'Offline controller accounting only; no scientific round or theorem is claimed',
            'nontriviality_argument':'The original runner and route ledger must retain continuous consumption',
            'contribution_type':'NONE','evidence_paths':[]})
        configuration.atomic_json(project/'research/ROUTE_SIGNAL.json',{'run_id':run_id,
            'progress_type':'NO_PROGRESS','reason':'Synthetic controller accounting acceptance without any provider or research execution.',
            'evidence_paths':[],'route_blocked':False})
        with contextlib.redirect_stdout(io.StringIO()):runner.record_round(project,data,epoch,policy,state,before)
        route_budget.save_ledger(path,data)
        print(json.dumps({'fixture_only':True,'operation':'original_runner_record_round','before':prior,
            'after':epoch['effective_rounds'],'counted_run_ids':epoch['counted_run_ids'],'scientific_progress':False}))
    elif operation in {'begin','finish-failed'}:
        if operation=='begin':original.begin_call(project,sys.argv[2])
        else:original.finish_call(project,sys.argv[2],accepted=False)
        print(json.dumps({'fixture_only':True,'operation':operation,'run_id':sys.argv[2]}))
    elif operation=='projection':
        from knowledge.build import derive
        graph=derive(configuration.ROOT,project)
        print(json.dumps({'failed_branches':[node for node in graph['nodes'] if node['kind']=='FAILED_BRANCH'],
            'exploration_nodes':[node for node in graph['nodes'] if node['kind']=='EXPLORATION_NODE'],
            'reference_edges':[edge for edge in graph['edges'] if edge.get('provenance_kind')=='SCOPED_LEMMA_REUSE_SUGGESTION']}))
    elif operation in {'fail-close','crash-before-commit'}:
        from candidate_search import resolution
        from unittest import mock
        request=configuration.load_json(sys.argv[2])
        def fault(*args,**kwargs):
            if operation=='crash-before-commit':
                import os
                os._exit(86)
            raise OSError('Injected local close commit failure before any original afterimage')
        try:
            with mock.patch.object(resolution.discovery,'commit_prepared',side_effect=fault):
                resolution.apply_switch(project,request,locks_held=True)
        except OSError as exc:
            print(json.dumps({'fixture_only':True,'status':'INJECTED_LOCAL_CLOSE_FAILURE','reason':str(exc),
                'active_attempt':ledger(project)['active_attempt'],'research_execution_started':False}))
        else:raise AssertionError('Injected fixture fault did not occur')
    else:raise ValueError('Unknown trusted fixture operation')
""")

        budget_locations = [root / 'state/routes', root / 'state/route_registry', root / 'state/supervision']
        protected_locations = [project, root / 'state/discovery', root / 'state/discovery_registry',
                               root / 'state/discovery_registration', root / 'state/research_acceptance',
                               *budget_locations, root / 'config']
        frozen_goal = (project / 'GOAL.md').read_bytes()
        frozen_g8 = (project / 'research/GATES.json').read_bytes()
        frozen_accepted = (project / 'research/accepted_contribution.json').read_bytes()

        def unchanged(args, expected=0):
            before = fingerprint(protected_locations, root)
            result = invoke(args, expected)
            assert fingerprint(protected_locations, root) == before, 'R15 operation changed original research authority'
            return result

        # The local original note is only a lookup input. It is not an original
        # cryptographic paper, and no novelty success is invented for this toy.
        novelty = unchanged(['knowledge', 'context', 'alpha', '--claim', 'CLAIM-A',
            '--task', 'Check the exact middle term against literature/nearest.md; novelty remains pending', '--dry-run'])
        comparison = unchanged(['candidate', 'compare', 'alpha', '--id', 'C-A', '--id', 'C-B'])
        write(output / 'A-local-novelty-pending.json', {'context': novelty, 'comparison': comparison,
            'novelty_status': 'NOVELTY_PENDING', 'scientific_acceptance': False})
        first_count = helper_run('record-round', 'toy-r1')
        assert first_count['before'] == 0 and first_count['after'] == 1
        selected_plan = unchanged(['candidate', 'plan', 'alpha', '--dry-run'])
        plan_file = root / 'plan.json'
        write(plan_file, selected_plan)
        selected = unchanged(['candidate', 'select', 'alpha', '--id', 'C-A', '--expected-revision', '1',
            '--plan-file', str(plan_file), '--reason', 'Explicit original toy branch ownership before any call'])
        selection_id = selected['selection']['selection_id']
        attempt_a = invoke(['attempt', 'start', 'alpha', '--problem', 'P-1', '--version', '1'])
        discovery_file = root / 'state/discovery/alpha.json'
        before_failed_call = discovery_file.read_bytes()
        unchanged(['candidate', 'bind-attempt', 'alpha', '--selection-id', selection_id,
                   '--attempt-id', attempt_a['id'], '--reason', 'Freeze exact C-A revision before dispatch'])
        # No provider is called. The old begin/finish APIs produce an honest
        # failed local-call receipt and retain the charge to this original owner.
        helper_run('begin', 'toy-a-failed-call')
        helper_run('finish-failed', 'toy-a-failed-call')
        consumed_call = discovery_file.read_bytes()
        authority_status = unchanged(['attempt', 'authority-status', 'alpha'])
        assert authority_status['actual_ledger_sha256'] == hashlib.sha256(consumed_call).hexdigest()
        discovery_file.write_bytes(before_failed_call)
        rollback = unchanged(['attempt', 'run', 'alpha', '--dry-run'], expected=2)
        unchanged(['candidate', 'plan', 'alpha', '--dry-run'], expected=2)
        discovery_file.write_bytes(consumed_call)
        discovery_file.unlink()
        missing = unchanged(['attempt', 'run', 'alpha', '--dry-run'], expected=2)
        discovery_file.write_bytes(consumed_call)
        write(output / 'review-N01-discovery-rollback-and-loss.json', {
            'rollback_blocked': rollback, 'missing_blocked': missing, 'authority_status': authority_status,
            'consumed_run_preserved': 'toy-a-failed-call', 'automatic_retry_allowed': False})
        unchanged(['candidate', 'map-run', 'alpha', '--selection-id', selection_id,
            '--attempt-id', attempt_a['id'], '--run-id', 'toy-a-failed-call', '--reason', 'Map original failed fixture receipt'])
        second_count = helper_run('record-round', 'toy-r2')
        assert second_count['before'] == 1 and second_count['after'] == 2
        write(output / 'original-controller-route-accounting.json', {'counts': [0, 1, 2],
            'receipts': [first_count, second_count], 'provider_requests': 0, 'scientific_progress': False})

        verification_request = unchanged(['candidate', 'verify-prepare', 'alpha', '--id', 'C-A',
            '--claim', 'CLAIM-A', '--bounds', '0', '1'])
        write(input_file, verification_request)
        certificate = unchanged(['candidate', 'verify', 'alpha', '--request', str(input_file)])
        assert certificate['result_status'] == 'COUNTEREXAMPLE_FOUND'
        assert certificate['result']['witness']['assignment'] == {'x': 1} and certificate['result']['tested_cases'] == 2
        checked = unchanged(['candidate', 'verification-recheck', 'alpha', '--request-id', verification_request['request_id']])
        assert checked['certificate_valid'] and checked['fresh'] and not checked['recheck_execution_started']
        write(output / 'minimal-counterexample.json', {'certificate': certificate, 'recheck': checked,
            'minimality_scope': 'Smallest absolute integer magnitude: zero satisfies the equality, and x=1 violates it.',
            'parent_or_family_refuted': False})

        scope = 'Only candidate C-A revision 1 requires the false equality for every integer; the original square-expansion target and other constructions remain open.'

        def card(status='REFUTED', **updates):
            value = {'schema_version': 1, 'requested_status': status, 'scope': scope,
                'restart_conditions': 'A changed construction hypothesis and a new independent review of its assumptions and scope',
                'reason': 'Exact synthetic local construction review; no family-wide conclusion',
                'verification_request_id': None, 'semantic_review_file': None,
                'source_dependencies': [], 'reusable_lemmas': []}
            value.update(updates)
            return value

        def prepare_resolution(candidate_id, value, claim_id='CLAIM-A'):
            write(input_file, value)
            args = ['candidate', 'resolve-prepare', 'alpha', '--id', candidate_id, '--card', str(input_file)]
            if claim_id:
                args += ['--claim', claim_id]
            return unchanged(args)

        def resolve(value, expected=0):
            write(input_file, value)
            return unchanged(['candidate', 'resolve', 'alpha', '--request', str(input_file)], expected)

        certificate_only = prepare_resolution('C-A', card(verification_request_id=verification_request['request_id']))
        conditional = resolve(certificate_only)
        assert conditional['status'] == 'CONDITIONAL' and not conditional['parent_or_family_refuted']
        write(output / 'machine-certificate-alone-insufficient.json', conditional)
        semantic = unchanged(['candidate', 'resolution-review-template', 'alpha', '--id', 'C-A',
            '--claim', 'CLAIM-A', '--status', 'REFUTED', '--scope', scope,
            '--verification-request-id', verification_request['request_id']])
        semantic.update(reviewer='fixture-independent-operator',
            necessity_argument='The frozen C-A hypothesis is exactly this universal equality. At x=1 its two sides are 4 and 2, so this candidate fails O-1. The frozen goal asks for an exact square expansion, not this erroneous equality, and C-B retains the missing middle term.')
        semantic_path = project / 'research/branch_reviews/A.json'
        write(semantic_path, semantic)

        def attest_scope(reason):
            return invoke(['claim', 'review', 'alpha', '--id', 'CLAIM-A', '--kind', 'statement',
                '--evidence', 'research/branch_reviews/A.json', '--reviewer', 'fixture-independent-operator', '--reason', reason])

        attest_scope('Attest exact negative candidate correspondence; no positive proof or novelty review')
        scoped_card = card(verification_request_id=verification_request['request_id'],
            semantic_review_file='research/branch_reviews/A.json',
            reusable_lemmas=[{**claims['SUPPORT'], 'scope': 'SUPPORT', 'consumer_claim': None,
                'dependency_argument': 'The independently checked distributivity lemma may support B; it does not rescue the false equality in A.'}])
        stale_request = prepare_resolution('C-A', scoped_card)
        write(semantic_path, {**semantic, 'necessity_argument': 'Changed after the input was frozen; the old review must fail.'})
        stale = resolve(stale_request, expected=2)
        assert stale['status'] == 'FAILED'
        write(output / 'fault-evidence-changed.json', stale)
        # Restoring bytes does not silently revive an observed stale review.
        # A new independent scope record and original review receipt are required.
        semantic['necessity_argument'] += ' Fresh independent review performed after the injected input change.'
        write(semantic_path, semantic)
        attest_scope('Fresh independent scope re-review after detected source alteration')
        resolution_request = prepare_resolution('C-A', scoped_card)
        write(output / 'frozen-scoped-resolution.json', resolution_request)
        refuted = resolve(resolution_request)
        assert refuted['status'] == 'REFUTED' and refuted['scope_type'] == 'EXACT_CANDIDATE_REVISION'
        assert not refuted['parent_or_family_refuted'] and not refuted['scientific_acceptance']
        assert refuted['route_effective_rounds'] == 2 and refuted['open_obligations']
        history_before = unchanged(['candidate', 'history', 'alpha', '--id', 'C-A'])
        replay = resolve(resolution_request)
        assert replay == refuted and unchanged(['candidate', 'history', 'alpha', '--id', 'C-A']) == history_before
        branch_b = unchanged(['candidate', 'show', 'alpha', '--id', 'C-B'])
        assert branch_b['status'] == 'READY_FOR_ATTEMPT' and branch_b['eligible_for_attempt']
        write(output / 'normal-scoped-refutation.json', refuted)
        write(output / 'independent-scope-review.json', semantic)
        projected = helper_run('projection')
        failed_a = [node for node in projected['failed_branches'] if node.get('candidate_id') == 'C-A']
        assert failed_a and all(not node['family_refuted'] and not node['scientific_acceptance'] for node in failed_a)
        assert any(edge['classification'] == 'SUPPORT' for edge in projected['reference_edges'])
        write(output / 'failed-branch-knowledge-node.json', projected)
        receipt_relative = next(path for path in resolution_request['controller_bindings'] if path.endswith('.receipt.json'))
        machine_receipt_path = root / receipt_relative
        assert machine_receipt_path.resolve().is_relative_to(root.resolve())
        machine_receipt_bytes = machine_receipt_path.read_bytes()
        machine_receipt_path.unlink()
        missing_machine_receipt = helper_run('projection')
        affected = next(node for node in missing_machine_receipt['failed_branches']
                        if node.get('resolution_id') == refuted['resolution_id'])
        assert affected['validity'] == 'PENDING_REVALIDATION' and any('CONTROLLER:' in value for value in affected['stale_sources'])
        write(output / 'fault-archived-machine-receipt-missing.json', missing_machine_receipt)
        machine_receipt_path.write_bytes(machine_receipt_bytes)
        unchanged(['candidate', 'verification-recheck', 'alpha', '--request-id', verification_request['request_id']])

        covered = resolve(prepare_resolution('C-RETIRED', card('COVERED')))
        assert covered['status'] == 'CONDITIONAL' and covered['gaps']
        retired = unchanged(['candidate', 'retire', 'alpha', '--id', 'C-RETIRED', '--expected-revision', '1',
            '--reason', 'Cancel synthetic direction while retaining all mathematical inputs',
            '--scope', 'Only the abandoned synthetic coefficient-table construction',
            '--restart-conditions', 'Fresh reviewed construction and original budget history retained'])
        assert retired['status'] == 'RETIRED' and not retired['scientific_acceptance']
        retired_history = unchanged(['candidate', 'history', 'alpha', '--id', 'C-RETIRED'])
        assert any(record['status'] == 'RETIRED' for record in retired_history['records'])
        write(output / 'retired-evidence-retained.json', retired_history)

        unchanged(['candidate', 'status', 'alpha', '--id', 'C-A', '--status', 'READY_FOR_ATTEMPT',
            '--expected-revision', '1', '--reason', 'Rejected revision cannot become active again'], expected=2)
        stop_path = project / '.control/STOP_REQUESTED'
        write(stop_path, 'Synthetic explicit stop request\n')
        stop = unchanged(['candidate', 'switch-prepare', 'alpha', '--id', 'C-A', '--expected-revision', '1',
            '--phase', 'CLOSE', '--from-attempt-id', attempt_a['id'], '--reason', 'STOP must block a candidate switch'], expected=2)
        write(output / 'fault-stop-blocked.json', stop)
        stop_path.unlink()
        route_path = root / 'state/routes/alpha.json'
        saved_route = json.loads(route_path.read_text(encoding='utf8'))
        pending_route = copy.deepcopy(saved_route)
        pending_route['epochs'][-1].update(review_pending=True, review_reason='Synthetic explicit pending route review')
        route_budget.save_ledger(route_path, pending_route)
        pending = unchanged(['candidate', 'switch-prepare', 'alpha', '--id', 'C-A', '--expected-revision', '1',
            '--phase', 'CLOSE', '--reason', 'Pending original route review must block switching'], expected=2)
        write(output / 'fault-route-review-blocked.json', pending)
        route_budget.save_ledger(route_path, saved_route)
        budgets_before_switch = fingerprint(budget_locations, root)

        def prepare_switch(candidate, phase, reason, expected=0, revision=1, owner=None):
            args = ['candidate', 'switch-prepare', 'alpha', '--id', candidate,
                    '--expected-revision', str(revision), '--phase', phase, '--reason', reason]
            if owner:
                args += ['--from-attempt-id', owner]
            return unchanged(args, expected)

        def apply_switch(request, expected=0):
            write(input_file, request)
            return invoke(['candidate', 'switch-apply', 'alpha', '--request', str(input_file)], expected)

        close_a = prepare_switch('C-A', 'CLOSE', 'Explicitly close only the rejected local construction', owner=attempt_a['id'])
        close_file = root / 'close-a.json'
        write(close_file, close_a)
        close_failure = helper_run('fail-close', str(close_file))
        assert close_failure['active_attempt'] == attempt_a['id']
        close_status = unchanged(['candidate', 'switch-status', 'alpha', '--request-id', close_a['request_id']])
        assert close_status['phase'] == 'PREPARED' and not close_status['automatic_retry_allowed']
        write(output / 'fault-close-failed-old-owner-retained.json', {'failure': close_failure, 'status': close_status})
        closed = invoke(['candidate', 'switch-recover', 'alpha', '--request-id', close_a['request_id']])
        assert closed['status'] == 'APPLIED' and closed['attempt_id'] == attempt_a['id']
        original = json.loads((root / 'state/discovery/alpha.json').read_text(encoding='utf8'))
        assert original['active_attempt'] is None and len(original['attempts']) == 1
        assert original['attempts'][0]['status'] == 'CLOSED' and len(original['attempts'][0]['calls']) == 1
        replay_close = invoke(['candidate', 'switch-recover', 'alpha', '--request-id', close_a['request_id']])
        assert replay_close == closed
        assert fingerprint(budget_locations, root) == budgets_before_switch

        start_b = prepare_switch('C-B', 'START', 'Explicitly prepare the alternative with its independently reviewed exact lemma')
        # Dependency freshness must be checked again when a frozen START is
        # applied, not only when that plan is produced.
        support_path = project / 'proofs/support.md'
        support_bytes = support_path.read_bytes()
        write(support_path, 'Changed required distributivity lemma after the START request was frozen.\n')
        stale_start = apply_switch(start_b, expected=2)
        assert json.loads((root / 'state/discovery/alpha.json').read_text(encoding='utf8'))['active_attempt'] is None
        write(output / 'fault-start-dependency-changed.json', stale_start)
        support_path.write_bytes(support_bytes)
        support_review_path = project / 'research/support-review.md'
        write(support_review_path, support_review_path.read_text(encoding='utf8') + 'Fresh independent re-review after the injected evidence change.\n')
        invoke(['claim', 'review', 'alpha', '--id', 'SUPPORT', '--kind', 'proof_and_statement',
            '--evidence', 'research/support-review.md', '--reviewer', 'fixture-independent-operator',
            '--reason', 'Fresh independent distributivity review after detected dependency source change'])
        start_b = prepare_switch('C-B', 'START', 'Explicit B start after fresh independent lemma review')
        start_file = root / 'start-b.json'
        write(start_file, start_b)
        helper_run('crash-before-commit', str(start_file), expected=86)
        crash_status = unchanged(['candidate', 'switch-status', 'alpha', '--request-id', start_b['request_id']])
        assert crash_status['phase'] == 'PREPARED' and not crash_status['research_execution_started']
        assert json.loads((root / 'state/discovery/alpha.json').read_text(encoding='utf8'))['active_attempt'] is None
        write(output / 'fault-crash-before-start.json', crash_status)
        pending_old_entry = unchanged(['attempt', 'start', 'alpha', '--problem', 'P-1', '--version', '1'], expected=2)
        write(output / 'fault-pending-switch-blocks-old-start.json', pending_old_entry)
        intent_path = root / 'state/candidates/alpha/switches' / (start_b['request_id'] + '.json')
        witness_path = root / 'state/candidates/alpha/operation_witnesses' / (start_b['request_id'] + '.json')
        assert witness_path.is_file() and intent_path.resolve().is_relative_to(root.resolve())
        frozen_intent = intent_path.read_bytes()
        intent_path.unlink()
        lost_intent_start = unchanged(['attempt', 'start', 'alpha', '--problem', 'P-1', '--version', '1'], expected=2)
        lost_intent_run = unchanged(['attempt', 'run', 'alpha', '--dry-run'], expected=2)
        lost_diagnostic = json.dumps([lost_intent_start, lost_intent_run]).upper()
        assert any(word in lost_diagnostic for word in ('WITNESS', 'INTENT', 'BRANCH', 'RECOVERY'))
        assert json.loads((root / 'state/discovery/alpha.json').read_text(encoding='utf8'))['active_attempt'] is None
        write(output / 'fault-single-intent-missing-old-entries-stop.json',
              {'start': lost_intent_start, 'run_dry_run': lost_intent_run, 'witness_retained': True})
        intent_path.write_bytes(frozen_intent)
        started = invoke(['candidate', 'switch-recover', 'alpha', '--request-id', start_b['request_id']])
        assert started['status'] == 'APPLIED' and not started['research_execution_started']
        assert started['next_required_action'] == 'EXPLICIT_ORIGINAL_RUN_COMMAND'
        original = json.loads((root / 'state/discovery/alpha.json').read_text(encoding='utf8'))
        assert len(original['attempts']) == 2 and original['active_attempt'] == started['attempt_id']
        assert sum(item['status'] == 'ACTIVE' for item in original['attempts']) == 1
        assert original['attempts'][0]['status'] == 'CLOSED' and original['attempts'][1]['problem_id'] == 'P-1'
        before_replay = fingerprint(protected_locations, root)
        assert invoke(['candidate', 'switch-recover', 'alpha', '--request-id', start_b['request_id']]) == started
        assert fingerprint(protected_locations, root) == before_replay
        assert fingerprint(budget_locations, root) == budgets_before_switch
        write(output / 'normal-explicit-A-to-B.json', {'close': closed, 'start': started, 'original_attempts': original,
            'route_ledger': json.loads(route_path.read_text(encoding='utf8')), 'same_goal_anchor': anchor,
            'new_budget_authority_created': False, 'provider_requests': 0})

        # An unresolved original call blocks closing B, regardless of the
        # rejected A history. It is settled only by the explicit old local API.
        helper_run('begin', 'toy-b-unknown-call')
        unknown = prepare_switch('C-B', 'CLOSE', 'Unknown result must block automatic retries or switching', expected=2,
                                 owner=started['attempt_id'])
        write(output / 'fault-unknown-original-result-blocked.json', unknown)
        original_unknown = json.loads((root / 'state/discovery/alpha.json').read_text(encoding='utf8'))
        assert original_unknown['active_attempt'] == started['attempt_id'] and len(original_unknown['attempts']) == 2
        helper_run('finish-failed', 'toy-b-unknown-call')
        assert fingerprint(budget_locations, root) == budgets_before_switch

        close_b = prepare_switch('C-B', 'CLOSE', 'Explicitly close B before testing reviewed restart gates',
                                 owner=started['attempt_id'])
        assert apply_switch(close_b)['status'] == 'APPLIED'
        metadata_revision = copy.deepcopy(candidates['C-A'])
        metadata_revision['falsification_gate'] += '; explicitly record the unchanged scientific hypothesis'
        write(input_file, metadata_revision)
        unchanged(['candidate', 'revise', 'alpha', '--file', str(input_file), '--expected-revision', '1',
            '--reason', 'Metadata revision cannot erase an exact archived counterexample'])
        unchanged(['candidate', 'status', 'alpha', '--id', 'C-A', '--status', 'READY_FOR_ATTEMPT',
            '--expected-revision', '2', '--reason', 'Exercise original structural gate; R15 must still reject scientific restart'])
        unchanged_hypothesis = prepare_switch('C-A', 'START', 'Metadata change must not restart a refuted branch',
                                             expected=2, revision=2)
        write(output / 'fault-restart-unchanged-hypothesis.json', unchanged_hypothesis)
        changed_revision = copy.deepcopy(metadata_revision)
        changed_revision['hypothesis'] = 'Introduce an explicit residual r=x and propose x*x+1+2*r as the exact square expansion'
        write(input_file, changed_revision)
        unchanged(['candidate', 'revise', 'alpha', '--file', str(input_file), '--expected-revision', '2',
            '--reason', 'Record a distinct construction hypothesis without silently changing original problem assumptions'])
        unchanged(['candidate', 'status', 'alpha', '--id', 'C-A', '--status', 'READY_FOR_ATTEMPT',
            '--expected-revision', '3', '--reason', 'Structural readiness does not replace a new independent restart review'])
        missing_review = prepare_switch('C-A', 'START', 'Changed construction without fresh independent review must stop',
                                       expected=2, revision=3)
        write(output / 'fault-restart-missing-independent-review.json', missing_review)
        assert json.loads((root / 'state/discovery/alpha.json').read_text(encoding='utf8'))['active_attempt'] is None
        restart_review = unchanged(['candidate', 'restart-review-template', 'alpha', '--id', 'C-A', '--claim', 'CLAIM-A'])
        restart_review.update(reviewer='fixture-independent-operator',
            why_old_evidence_not_applicable='The old witness disproves the equality missing its 2*x term. Revision 3 explicitly introduces residual r=x and includes 2*r, so that old witness no longer contradicts this changed construction hypothesis. The frozen integer domain and global assumptions are preserved; this review authorizes reconsideration only, not a proof or novelty result.')
        write(project / 'research/branch_reviews/A-restart.json', restart_review)
        invoke(['claim', 'review', 'alpha', '--id', 'CLAIM-A', '--kind', 'statement',
            '--evidence', 'research/branch_reviews/A-restart.json', '--reviewer', 'fixture-independent-operator',
            '--reason', 'Attest precise changed construction and retained old negative evidence; no positive proof'])
        reviewed_restart = prepare_switch('C-A', 'START', 'Explicit independently reviewed changed construction under the same frozen problem',
                                          revision=3)
        restarted = apply_switch(reviewed_restart)
        assert restarted['status'] == 'APPLIED' and not restarted['research_execution_started']
        restarted_ledger = json.loads((root / 'state/discovery/alpha.json').read_text(encoding='utf8'))
        assert len(restarted_ledger['attempts']) == 3 and restarted_ledger['active_attempt'] == restarted['attempt_id']
        assert sum(item['status'] == 'ACTIVE' for item in restarted_ledger['attempts']) == 1
        assert all(item['problem_id'] == 'P-1' for item in restarted_ledger['attempts'])
        assert len(restarted_ledger['attempts'][0]['calls']) == 1 and len(restarted_ledger['attempts'][1]['calls']) == 1
        assert fingerprint(budget_locations, root) == budgets_before_switch
        write(output / 'normal-reviewed-restart-inherits-budget.json', {'review': restart_review,
            'start': restarted, 'original_attempts': restarted_ledger,
            'route_effective_rounds': 2, 'same_route_epoch': 1, 'new_budget_authority_created': False})

        assert (project / 'GOAL.md').read_bytes() == frozen_goal
        assert (project / 'research/GATES.json').read_bytes() == frozen_g8
        assert (project / 'research/accepted_contribution.json').read_bytes() == frozen_accepted
        final_state = json.loads((project / 'research/STATE.json').read_text(encoding='utf8'))
        assert final_state['accepted_contribution'] == state['accepted_contribution'] and final_state['selected_idea'] is None
        final_claims = unchanged(['claim', 'status', 'alpha'])
        assert all(not item['accepted_contribution'] for item in final_claims['claims'])
        assert next(item for item in final_claims['claims'] if item['id'] == 'CLAIM-A')['proof_status'] != 'INDEPENDENTLY_REVIEWED'
        assert (project / 'proofs/branch-a.md').read_text(encoding='utf8').startswith('Candidate A proposes')
        final_history = unchanged(['candidate', 'history', 'alpha'])
        assert any(record['status'] == 'REFUTED' and record['candidate_id'] == 'C-A' for record in final_history['records'])
        assert any(record['status'] == 'RETIRED' for record in final_history['records'])
        write(output / 'final-history.json', final_history)

        allowed = (root / 'allowed-workers.jsonl')
        audit = [json.loads(line) for line in allowed.read_text(encoding='utf8').splitlines()] if allowed.exists() else []
        assert len(audit) == 1 and audit[0]['worker_sha256'] == worker_sha, 'Unexpected verifier dispatch or replay'
        assert not (root / 'forbidden-execution.jsonl').exists(), 'Forbidden network or program attempted'
        receipt['trusted_integer_worker_executions'] = len(audit)
        receipt['status'] = 'PASS'
        write(output / 'execution-audit.json', {'allowed_workers': audit, 'forbidden_events': [],
            'provider_requests': 0, 'lean_executions': 0, 'supervision_executions': 0, 'network_requests': 0,
            'os_sandbox_certified': False})
        write(output / 'native-entry.json', receipt)
    print(json.dumps({'round': 'R15', 'status': 'PASS', 'steps': len(receipt['steps']),
                      'trusted_integer_worker_executions': receipt['trusted_integer_worker_executions'],
                      'output': str(output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
