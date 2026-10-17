"""R16 real Windows entry calibration in temporary public/private fixtures.

This is evaluator calibration, never a model benchmark or OS isolation claim.
Controller children may not start nested processes, network, Lean or supervisors.
All gold data remains in an evaluator directory outside the public agent bundle.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from verify_r03_offline import fingerprint, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    output = parser.parse_args().output.resolve()
    if any(output.is_relative_to(SOURCE / name) for name in ('projects', 'state', 'logs', 'config')):
        raise ValueError('Evidence must be outside project/runtime/config trees')
    output.mkdir(parents=True, exist_ok=True)
    receipt = {'round': 'R16', 'fixture_only': True, 'model_executions': 0,
        'network_requests': 0, 'lean_executions': 0, 'supervision_executions': 0,
        'os_isolation_probes': 0, 'formal_benchmark_counted': 0, 'steps': []}
    with tempfile.TemporaryDirectory(prefix='crc r16 native fixture ') as temporary:
        workspace = Path(temporary)
        root = workspace / 'controller'
        root.mkdir()
        private = workspace / 'evaluator-private'
        private.mkdir()
        bundles = workspace / 'agent-public'
        bundles.mkdir()
        for file in SOURCE.glob('*.py'):
            shutil.copy2(file, root / file.name)
        for name in ('research.cmd', 'VERSION'):
            shutil.copy2(SOURCE / name, root / name)
        for name in ('engine', 'candidate_search', 'evaluation', 'knowledge', 'method', 'profiles'):
            shutil.copytree(SOURCE / name, root / name, ignore=shutil.ignore_patterns('__pycache__'))
        (root / 'config').mkdir()
        for file in (SOURCE / 'config').glob('*.json'):
            shutil.copy2(file, root / 'config' / file.name)
        # These are synthetic sentinels only. Benchmark commands have no
        # authority to alter even this temporary research state or its history.
        for relative, value in {'projects/alpha/GOAL.md': 'Frozen synthetic target; no benchmark alters the goal.\n',
            'projects/alpha/PROJECT.json': {'id': 'alpha', 'checks': []},
            'projects/alpha/research/STATE.json': {'decision': 'NEEDS_REVIEW', 'last_run': 'retained-toy-run',
                'accepted_contribution': False},
            'projects/alpha/research/GATES.json': {'G8': 'INDEPENDENT_REVIEW_REQUIRED'},
            'state/routes/alpha.json': {'fixture_only': True, 'effective_rounds': 2, 'budget': 6,
                'counted_run_ids': ['toy-r1', 'toy-r2']},
            'state/discovery/alpha.json': {'fixture_only': True, 'history': 'retain exact original synthetic bytes'}}.items():
            write(root / relative, value)
        write(root / 'sitecustomize.py', """import os,sys
def guard(event,args):
    if event in {'subprocess.Popen','socket.connect','socket.getaddrinfo','os.system','os.exec','os.posix_spawn','os.spawn'}:
        with open(os.environ['CRC_R16_DENIED_LOG'],'a',encoding='utf8') as log:log.write(event+'\\n')
        raise RuntimeError('R16 calibration forbids all network and nested execution: '+event)
sys.addaudithook(guard)
""")
        env = dict(os.environ, CRC_PYTHON=sys.executable, PYTHONDONTWRITEBYTECODE='1',
            PYTHONIOENCODING='utf8', PYTHONPATH=str(root), PYTHONNOUSERSITE='1',
            PATH=str(root) + os.pathsep + os.environ.get('PATH', ''),
            CRC_R16_DENIED_LOG=str(root / 'forbidden-execution.jsonl'))
        entry = ([os.environ.get('COMSPEC', r'C:\Windows\System32\cmd.exe'), '/d', '/c', 'research.cmd']
                 if os.name == 'nt' else [sys.executable, '-B', str(root / 'research.py')])
        receipt['entry'] = 'research.cmd' if os.name == 'nt' else 'research.py'
        protected = fingerprint([root / 'projects', root / 'state', root / 'config'], root)

        def invoke(arguments, expected=0):
            result = subprocess.run(entry + ['benchmark', *arguments], cwd=root, env=env,
                capture_output=True, text=True, encoding='utf8', timeout=60)
            item = {'args': ['benchmark', *arguments], 'exit_code': result.returncode,
                'expected_exit_code': expected, 'stdout': result.stdout, 'stderr': result.stderr}
            receipt['steps'].append(item)
            write(output / 'in-progress.json', receipt)
            assert result.returncode == expected, item
            assert fingerprint([root / 'projects', root / 'state', root / 'config'], root) == protected, \
                'Benchmark mutated original project, budgets, history or configuration'
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                if expected == 0:
                    raise
                return {'diagnostic': result.stdout + result.stderr}

        def private_fingerprint():
            # Existing file_lock uses a persistent coordination file. Its
            # bytes are not oracle or registration authority and may change
            # on another legitimate lock acquisition.
            return {key: value for key, value in fingerprint([private], workspace).items()
                    if not key.endswith('.lock')}

        # Gold material is generated from test-side helpers on the host. The
        # tests directory is never copied into controller/ or agent-public/.
        spec = importlib.util.spec_from_file_location('r16_host_fixture_helpers', SOURCE / 'tests/test_benchmark_cases.py')
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)
        listing = invoke(['list'])
        rows = listing['cases']
        assert len(rows) == 6 and len({row['category'] for row in rows}) == 6
        assert not listing['formal_counted'] and listing['quality_gain'] == 'NOT_MEASURED'
        default_validation = invoke(['validate'])
        assert default_validation['status'] == 'PENDING_CURATION'
        assert all(row['status'] == 'PENDING_CURATION' for row in default_validation['cases'])
        isolation = invoke(['isolation-status'])
        assert isolation['isolation_status'] == 'NOT_ISOLATED'
        assert not isolation['formal_counted'] and not isolation['agent_execution_allowed']
        assert not isolation['real_supervision_enabled'] and not isolation['lean_enabled']
        write(output / 'default-no-formal-isolation.json', isolation)

        def assert_calibration(value, status):
            assert value['status'] == status, value
            assert value['isolation_status'] == 'NOT_ISOLATED' and not value['formal_counted']
            assert not value['scientific_acceptance'] and not value['agent_execution_allowed']
            assert value['quality_gain'] == 'NOT_MEASURED'

        def score(case_id, response, expected=0, version=1):
            path = private / ('response-' + case_id + '.json')
            write(path, response)
            return invoke(['score-fixture', '--case', case_id, '--version', str(version),
                           '--response', str(path), '--private-root', str(private)], expected)

        def negative(task, response):
            value = copy.deepcopy(response)
            category = task['category']
            if category == 'THEOREM_COVERAGE':
                value['coverage_mapping']['domain'] = 'An undeclared different domain'
            elif category == 'COUNTEREXAMPLE':
                value['witness'] = {'a': 2, 'q': 2}
            elif category == 'SECURITY_FLAW':
                value['worlds'][1] = copy.deepcopy(value['worlds'][0])
                value['recovered_expression'] = 'y2-y1'
            elif category == 'OPEN_BOUNDARY':
                value['proof_status'] = 'PROVED'
            elif category == 'RESEARCH_DRIFT':
                value['finding_codes'] = []
            elif category == 'STATE_RECOVERY':
                value['redispatch'] = True
            else:
                raise AssertionError('Unregistered calibration category')
            return value

        views, positives, registrations = {}, {}, {}
        normal_rows = []
        for row in rows:
            case_id = row['case_id']
            view = invoke(['show', '--case', case_id])
            task = view['task']
            views[case_id] = view
            serialized = json.dumps(view, ensure_ascii=False)
            assert 'oracle_sha256' not in serialized and 'oracle_file' not in serialized and str(private) not in serialized
            assert task['budget']['model_calls'] == 0
            response = fixture.fixture_response(task)
            positives[case_id] = response
            missing = score(case_id, response, expected=2)
            assert_calibration(missing, 'STALE_OR_INVALID')
            oracle_path = private / ('input-oracle-' + case_id + '.json')
            write(oracle_path, fixture.fixture_oracle(task))
            reason = 'Independently curate exact synthetic source and the positive/negative evidence boundaries for ' + case_id
            registration = invoke(['register-oracle', '--case', case_id, '--version', '1',
                '--oracle-file', str(oracle_path), '--private-root', str(private),
                '--reviewer', 'fixture-independent-curator', '--reason', reason])
            assert registration['status'] == 'REGISTERED_PRIVATE_CALIBRATION' and not registration['formal_counted']
            registrations[case_id] = (oracle_path, reason, registration)
            before_private = private_fingerprint()
            good = score(case_id, response)
            bad = score(case_id, negative(task, response))
            assert_calibration(good, 'PASS')
            assert_calibration(bad, 'FAIL')
            assert all(check['passed'] for check in good['checks']) and any(not check['passed'] for check in bad['checks'])
            # Response files are the only explicit evaluator-side inputs changed
            # between scores; the frozen registry, oracle and revision stay put.
            after_private = private_fingerprint()
            response_key = (private / ('response-' + case_id + '.json')).relative_to(workspace).as_posix()
            assert {k:v for k,v in before_private.items() if k != response_key} == {
                    k:v for k,v in after_private.items() if k != response_key}
            destination = bundles / case_id
            bundle = invoke(['bundle', '--case', case_id, '--destination', str(destination)])
            expected_files = sorted(['task.json', 'PUBLIC_BINDING.json', *[document['file'] for document in view['source_documents']]])
            actual_files = sorted(file.relative_to(destination).as_posix() for file in destination.rglob('*') if file.is_file())
            assert bundle['files'] == expected_files == actual_files
            assert not bundle['formal_counted'] and not bundle['agent_execution_allowed']
            assert json.loads((destination / 'task.json').read_text(encoding='utf8')) == task
            binding = json.loads((destination / 'PUBLIC_BINDING.json').read_text(encoding='utf8'))
            assert 'oracle_sha256' not in binding and 'oracle_file' not in binding
            for document in view['source_documents']:
                assert hashlib.sha256((destination / document['file']).read_bytes()).hexdigest() == document['sha256']
            assert not any('oracle' in name.casefold() or 'tests/' in name for name in actual_files)
            assert not private.is_relative_to(destination) and not destination.is_relative_to(private)
            normal_rows.append({'case_id': case_id, 'category': task['category'], 'positive': good, 'negative': bad,
                'public_bundle_files': actual_files, 'formal_counted': False})
            write(output / ('case-' + case_id + '.json'), normal_rows[-1])
        write(output / 'six-category-calibration.json', {'cases': normal_rows, 'formal_counted': 0,
            'quality_gain': 'NOT_MEASURED', 'oracle_excluded_from_all_public_bundles': True})
        curated_validation = invoke(['validate', '--private-root', str(private)])
        assert curated_validation['status'] == 'CALIBRATION_READY'
        assert all(row['status'] == 'CALIBRATION_READY' for row in curated_validation['cases'])
        assert not curated_validation['formal_counted'] and not curated_validation['formal_benchmark_available']
        assert curated_validation['benchmark_agent_isolation'] == 'NOT_ISOLATED'
        write(output / 'curated-six-cases-not-formal-benchmark.json', curated_validation)

        case_id = 'BENCH-CE-001'
        oracle_path, reason, first = registrations[case_id]
        before = private_fingerprint()
        repeated = invoke(['register-oracle', '--case', case_id, '--version', '1',
            '--oracle-file', str(oracle_path), '--private-root', str(private),
            '--reviewer', 'fixture-independent-curator', '--reason', reason])
        assert repeated['status'] == 'ALREADY_REGISTERED' and repeated['entry'] == first['entry']
        assert private_fingerprint() == before
        history_before = invoke(['history', '--case', case_id, '--private-root', str(private)])
        assert len(history_before['entries']) == 1
        source = root / 'evaluation/benchmarks' / views[case_id]['public_binding']['task_file']
        frozen_task = source.read_bytes()
        changed = json.loads(frozen_task)
        changed['frozen_goal'] += ' Unreviewed goal mutation after independent curation.'
        write(source, changed)
        stale = score(case_id, positives[case_id], expected=2)
        assert_calibration(stale, 'STALE_OR_INVALID')
        write(output / 'fault-task-mutation-stale.json', stale)
        source.write_bytes(frozen_task)
        assert_calibration(score(case_id, positives[case_id]), 'PASS')
        assert invoke(['history', '--case', case_id, '--private-root', str(private)]) == history_before
        self_asserted = copy.deepcopy(positives[case_id])
        self_asserted['isolation_verified'] = True
        false_isolation = score(case_id, self_asserted)
        assert_calibration(false_isolation, 'FAIL')
        write(output / 'fault-self-asserted-isolation-not-accepted.json', false_isolation)

        # A reviewed new public version creates another private revision;
        # neither the old gold record nor its responsibility is overwritten.
        dataset = root / 'evaluation/benchmarks'
        manifest_path = dataset / 'manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf8'))
        task_v2 = copy.deepcopy(views[case_id]['task'])
        task_v2['version'] = 2
        task_v2['frozen_goal'] += ' Reviewed wording revision retains the exact original integer predicate.'
        relative_v2 = 'public/' + case_id + '/v2/task.json'
        task_v2_path = dataset / relative_v2
        write(task_v2_path, task_v2)
        row_v2 = copy.deepcopy(next(row for row in rows if row['case_id'] == case_id))
        row_v2.update(version=2, task_file=relative_v2, task_sha256=hashlib.sha256(task_v2_path.read_bytes()).hexdigest())
        manifest['cases'].append(row_v2)
        write(manifest_path, manifest)
        view_v2 = invoke(['show', '--case', case_id, '--version', '2'])
        v2_oracle_file = private / 'input-oracle-ce-v2.json'
        write(v2_oracle_file, fixture.fixture_oracle(view_v2['task']))
        v2_registration = invoke(['register-oracle', '--case', case_id, '--version', '2',
            '--oracle-file', str(v2_oracle_file), '--private-root', str(private), '--reviewer', 'fixture-second-curator',
            '--reason', 'Independent second-version review preserves exact inputs and documents the public goal wording revision'])
        assert v2_registration['status'] == 'REGISTERED_PRIVATE_CALIBRATION'
        assert_calibration(score(case_id, fixture.fixture_response(view_v2['task']), version=2), 'PASS')
        history_after = invoke(['history', '--case', case_id, '--private-root', str(private)])
        assert len(history_after['entries']) == 2 and history_after['entries'][0] == history_before['entries'][0]
        difference = invoke(['diff', '--case', case_id, '--private-root', str(private), '--from-version', '1', '--to-version', '2'])
        assert 'task_sha256' in difference['changed_fields'] and difference['responsibility']['after']['reviewer'] == 'fixture-second-curator'
        write(output / 'normal-version-history-diff.json', {'history': history_after, 'difference': difference})
        assert_calibration(score(case_id, positives[case_id], version=1), 'PASS')
        assert not (root / 'forbidden-execution.jsonl').exists(), 'Unexpected nested process or network access'
        receipt.update(status='PASS', calibrated_categories=len(normal_rows),
            positive_responses=6, negative_responses=6, oracle_excluded_from_public_bundles=True,
            os_isolation_scope='Not executed here; fixed local token probe has separate evidence and cannot certify a research agent.')
        write(output / 'execution-audit.json', {'forbidden_events': [], 'nested_program_executions': 0,
            'model_executions': 0, 'network_requests': 0, 'lean_executions': 0, 'supervision_executions': 0,
            'os_isolation_probes': 0, 'formal_benchmark_counted': 0})
        write(output / 'native-entry.json', receipt)
    print(json.dumps({'round': 'R16', 'status': 'PASS', 'steps': len(receipt['steps']),
                      'calibrated_categories': 6, 'formal_counted': 0, 'output': str(output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
