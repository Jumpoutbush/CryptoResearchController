"""R11 native controller acceptance in isolated toy projects; no paid execution.

The source controller's personal projects and runtime directories are never copied.
The child Python process denies network and nested process execution with an audit
hook, while the commands enter through the real Windows research.cmd launcher.
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
import configuration
from research_focus import make_focus
from verify_r03_offline import fingerprint, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output.resolve()
    if any(output.is_relative_to(SOURCE / name) for name in ('projects', 'state', 'logs', 'config')):
        raise ValueError('Evidence must be outside project/runtime/config trees')
    output.mkdir(parents=True, exist_ok=True)
    receipt = {'round': 'R11', 'fixture_only': True, 'provider_requests': 0,
               'network_requests': 0, 'lean_executions': 0, 'supervision_executions': 0,
               'steps': []}
    with tempfile.TemporaryDirectory(prefix='crc r11 native fixture ') as directory:
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
        write(root / 'sitecustomize.py', """import os, sys
def guard(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo', 'subprocess.Popen',
                 'os.system', 'os.exec', 'os.posix_spawn', 'os.spawn'}:
        with open(os.environ['CRC_R11_AUDIT_LOG'], 'a', encoding='utf8') as log:
            log.write(event + '\\n')
        raise RuntimeError('R11 fixture forbids network/provider/Lean execution: ' + event)
sys.addaudithook(guard)
""")
        env = dict(os.environ, CRC_PYTHON=sys.executable, PYTHONDONTWRITEBYTECODE='1',
                   PYTHONIOENCODING='utf8', PYTHONPATH=str(root), PYTHONNOUSERSITE='1',
                   PATH=str(root) + os.pathsep + os.environ.get('PATH', ''),
                   CRC_R11_AUDIT_LOG=str(root / 'forbidden-execution.jsonl'))
        entry = (['cmd.exe', '/d', '/c', 'research.cmd'] if os.name == 'nt'
                 else [sys.executable, '-B', str(root / 'research.py')])
        receipt['entry'] = 'research.cmd' if os.name == 'nt' else 'research.py'
        receipt['child_execution_guard'] = 'Python audit hook denies network and nested process execution'

        def invoke(args, expected=0, *, cwd=root):
            result = subprocess.run(entry + args, cwd=cwd, env=env, capture_output=True,
                                    text=True, encoding='utf8', timeout=60)
            item = {'args': args, 'exit_code': result.returncode, 'expected_exit_code': expected,
                    'stdout': result.stdout, 'stderr': result.stderr}
            receipt['steps'].append(item)
            assert result.returncode == expected, item
            if expected == 0:
                return json.loads(result.stdout)
            return result.stdout + result.stderr

        # Setup uses the existing operator imports before the immutable baseline.
        projects = {}
        unreviewed_pin = None
        for key in ('alpha', 'beta'):
            project = root / 'projects' / key
            projects[key] = project
            state = {'phase': 'PROOF', 'decision': 'CONTINUE', 'research_route': 'MAIN',
                     'selected_idea': None, 'last_run': None, 'next_task': 'Resolve exact toy obligations'}
            for rel, value in {
                'PROJECT.json': {'id': key, 'name': 'Same toy research title', 'checks': []},
                'GOAL.md': 'Frozen toy security target: malicious adversary, t<n/3, exact original quantifiers.\n',
                'AGENTS.md': 'Preserve the frozen toy target; infrastructure fixture only.\n',
                'RESEARCH_PROFILE.json': {'profiles': [], 'read_order': []},
                'research/STATE.json': state,
                'proofs/argument.md': 'Unreviewed synthetic dependency, no theorem claimed.\n',
                'literature/nearest.md': 'Synthetic nearest-work check; not a publication or novelty claim.\n',
            }.items():
                write(project / rel, value)
            spec = {'schema_version': 1, 'id': 'P-1', 'title': 'Frozen toy construction',
                'statement': 'Toy map F is binding for t<n/3 under a malicious adversary',
                'quantifiers': 'For every toy parameter and every malicious adversary',
                'domain': 'Finite toy domains', 'input_contract': 'Toy input x',
                'output_contract': 'Toy output y with exact original obligations',
                'goal_connection': 'Exact frozen toy binding target',
                'nontriviality_argument': 'Infrastructure fixture only; no scientific claim',
                'assumptions': ['t<n/3', 'malicious adversary'],
                'security_model': {'corruption_threshold': 't<n/3', 'adversary': 'malicious'},
                'immutable_constraints': ['Do not weaken corruption threshold or quantifiers'],
                'baseline_exclusions': ['No theorem or novelty claim'],
                'contribution_type': 'COMPLEXITY_THEOREM', 'source_paths': [],
                'obligations': [{'id': 'O-1', 'statement': 'Toy binding for original adversary',
                                 'acceptance_criterion': 'Independent review of exact frozen toy statement'}]}
            file = root / ('problem-' + key + '.json')
            write(file, spec)
            invoke(['problem', 'import', key, '--file', str(file), '--reason', 'Register isolated toy problem'])
            if key == 'alpha':
                claim = {'schema_version': 1, 'id': 'DEP-1', 'statement': 'Unreviewed toy dependency',
                    'assumptions': spec['assumptions'], 'dependencies': [], 'proposer': 'toy-proposer',
                    'problem_id': 'P-1', 'problem_version': 1, 'obligation_ids': ['O-1'],
                    'nontriviality_argument': 'Infrastructure fixture only',
                    'contribution_type': 'COMPLEXITY_THEOREM', 'evidence_paths': ['proofs/argument.md'],
                    'verification_mode': 'INDEPENDENT_MANUAL', 'formal_applicability_reason': 'No Lean in toy fixture'}
                write(file, claim)
                imported = invoke(['claim', 'import', key, '--file', str(file), '--reason', 'Register unreviewed fixture dependency'])
                unreviewed_pin = {name: imported[name] for name in ('id', 'revision', 'spec_sha256')}
            # Nonzero historical accounting must remain untouched by registration.
            focus = make_focus(project, state)
            write(root / 'state/routes' / (key + '.json'), {'schema_version': 1, 'project_id': key,
                'epochs': [{'epoch': 1, 'route': 'MAIN', 'effective_rounds': 2, 'stagnation': 1,
                    'extensions_used': 0, 'counted_run_ids': ['toy-r1', 'toy-r2'],
                    'last_processed_run': 'toy-r2', 'review_pending': False, 'focus': focus}],
                'events': [{'type': 'RESEARCH_ROUND', 'run_id': 'toy-r1'},
                           {'type': 'RESEARCH_ROUND', 'run_id': 'toy-r2'}]})
            write(root / 'state/discovery' / (key + '.json'),
                  {'schema_version': 1, 'active_attempt': None, 'attempts': []})
            write(root / 'state/supervision' / (key + '.json'),
                  {'fixture_sentinel': True, 'attempts_used': 2, 'seconds_used': 999})
        protected_paths = [root / 'projects', root / 'state/routes', root / 'state/discovery',
                           root / 'state/supervision', root / 'config']
        protected = fingerprint(protected_paths, root)
        anchor = invoke(['candidate', 'anchor', 'alpha'])['goal_anchor_id']
        candidate = {'schema_version': 1, 'id': 'C-0001', 'title': 'Same toy candidate title',
            'goal_anchor_id': anchor, 'problem_id': 'P-1', 'problem_version': 1,
            'hypothesis': 'A masked polynomial toy construction is binding under the frozen target',
            'nontriviality_argument': 'Falsifiable structural toy hypothesis only',
            'closest_prior_work': [{'source_id': 'TOY-PAPER-1', 'check': 'Check exact theorem and assumptions in full text',
                                    'full_text_checked': False}],
            'falsification_gate': 'Find a collision for a finite toy instance under the exact frozen adversary',
            'proof_obligations': ['O-1'], 'assumptions': ['t<n/3', 'malicious adversary'],
            'immutable_constraints': ['Do not weaken corruption threshold or quantifiers'],
            'domain': 'Finite toy domains',
            'quantifiers': 'For every toy parameter and every malicious adversary',
            'security_model': {'corruption_threshold': 't<n/3', 'adversary': 'malicious'},
            'estimated_context_bytes': 2048, 'dependency_claims': [], 'evidence_refs': [],
            'failure_scope': 'Only the exact toy construction and original frozen adversary',
            'restart_conditions': 'A new independently reviewed structural assumption and explicit new revision'}
        path = root / 'candidate.json'

        def propose(value, *, revise=False, expected=0, revision=1):
            write(path, value)
            args = ['candidate', 'revise' if revise else 'propose', 'alpha', '--file', str(path),
                    '--reason', 'Register exact isolated toy candidate']
            if revise:
                args += ['--expected-revision', str(revision)]
            return invoke(args, expected=expected)

        hypotheses = [candidate['hypothesis'],
            'An extractable commitment toy construction is binding under the frozen target',
            'A coded broadcast toy construction is binding under the frozen target']
        for number, hypothesis in enumerate(hypotheses, 1):
            value = copy.deepcopy(candidate)
            value.update(id=f'C-{number:04d}', hypothesis=hypothesis)
            if number == 3:
                value['parent'] = {'id': 'C-0001', 'revision': 1}
            propose(value)
            invoke(['candidate', 'status', 'alpha', '--id', value['id'], '--status', 'SCREENING',
                    '--expected-revision', '1', '--reason', 'Screen heterogeneous toy candidate'])
        ready = invoke(['candidate', 'status', 'alpha', '--id', 'C-0002', '--status', 'READY_FOR_ATTEMPT',
                        '--expected-revision', '1', '--reason', 'Exact toy scheduling readiness; no scientific acceptance'])
        assert ready['eligible_for_attempt'] and not ready['positive_basis']
        assert ready['novelty_status'] == 'NOVELTY_PENDING'
        normal = invoke(['candidate', 'list', 'alpha'])
        assert len(normal['candidates']) == 3
        assert not any(value['positive_basis'] for value in normal['candidates'])
        assert all(value['scientific_status'] == 'UNREVIEWED_CANDIDATE' for value in normal['candidates'])
        write(output / 'normal-candidate-tree.json', normal)
        inferred = invoke(['candidate', 'list'], cwd=projects['alpha'])
        assert normal == inferred, 'Project-directory resolution changed catalog view'
        beta = invoke(['candidate', 'list', 'beta'])
        assert beta['candidates'] == [] and beta['project_id'] == 'beta'
        write(output / 'same-title-other-project.json', beta)

        # Renaming cannot evade the semantic fingerprint or create another route.
        duplicate = copy.deepcopy(candidate)
        duplicate.update(id='C-0099', title='Renamed toy candidate', hypothesis='  ' + hypotheses[0].upper() + '  ')
        duplicate_result = propose(duplicate, expected=2)
        assert 'DUPLICATE' in duplicate_result
        write(output / 'duplicate-registration.json', {'expected_exit_code': 2, 'diagnostic': duplicate_result})
        assert normal == invoke(['candidate', 'list', 'alpha'])
        fourth = copy.deepcopy(candidate)
        fourth.update(id='C-0004', hypothesis='A lattice accumulator toy construction is binding under the frozen target')
        propose(fourth)
        capacity_error = invoke(['candidate', 'status', 'alpha', '--id', 'C-0004', '--status', 'SCREENING',
            '--expected-revision', '1', '--reason', 'Fault injection: fourth active toy candidate'], expected=2)
        write(output / 'capacity-rejection.json', {'expected_exit_code': 2, 'diagnostic': capacity_error})

        # Rewriting an existing node is rejected; explicit revision preserves old bytes.
        old = invoke(['candidate', 'show', 'alpha', '--id', 'C-0001', '--revision', '1'])
        changed = copy.deepcopy(candidate)
        changed['security_model']['adversary'] = 'malicious with an extra toy constraint'
        changed['hypothesis'] += ' with an independently pending extra toy assumption'
        rejected_rewrite = propose(changed, expected=2)
        revised = propose(changed, revise=True)
        assert old == invoke(['candidate', 'show', 'alpha', '--id', 'C-0001', '--revision', '1'])
        write(output / 'immutable-revision-history.json', {'before_revision_1': old, 'revision_2': revised,
                                                        'in_place_rejection': rejected_rewrite})

        invalid = copy.deepcopy(candidate)
        invalid.update(id='C-WEAK', hypothesis='Weakened corruption threshold toy proposal')
        invalid['assumptions'] = ['t<n/4', 'malicious adversary']
        weakening = propose(invalid, expected=2)
        invalid = copy.deepcopy(candidate)
        invalid.update(id='../escape', hypothesis='Boundary escape toy proposal')
        traversal = propose(invalid, expected=2)
        invalid = copy.deepcopy(candidate)
        invalid.update(id='C-FOREIGN', hypothesis='Foreign problem proposal', problem_id='beta:P-1')
        foreign = propose(invalid, expected=2)
        write(output / 'boundary-rejections.json', {'weakening': weakening, 'invalid_id': traversal,
                                                  'foreign_problem': foreign})
        # More dependency and terminal state checks follow the same real CLI.
        claim_candidate = copy.deepcopy(candidate)
        claim_candidate.update(id='C-CLAIM', hypothesis='A toy construction relying on an unreviewed claim')
        claim_candidate['dependency_claims'] = [unreviewed_pin]
        propose(claim_candidate)
        unreviewed = invoke(['candidate', 'status', 'alpha', '--id', 'C-CLAIM', '--status', 'READY_FOR_ATTEMPT',
            '--expected-revision', '1', '--reason', 'Fault injection: unreviewed toy dependency'], expected=2)
        assert 'DEPENDENCY_NOT_INDEPENDENTLY_REVIEWED' in unreviewed
        write(output / 'unreviewed-ready-rejection.json', {'expected_exit_code': 2, 'diagnostic': unreviewed})
        # Scope/restart conditions accompany rejection, and old versions survive.
        disposition = root / 'disposition.json'
        write(disposition, {'scope': 'Only the exact toy branch, not independent candidates',
                            'restart_conditions': 'Explicit new revision with independently reviewed changed assumption',
                            'evidence_refs': ['proofs/argument.md']})
        unaffected = invoke(['candidate', 'show', 'alpha', '--id', 'C-0003'])
        invoke(['candidate', 'status', 'alpha', '--id', 'C-0001', '--status', 'REFUTED',
            '--expected-revision', '2', '--disposition', str(disposition), '--reason', 'Record scoped synthetic failure'])
        assert unaffected == invoke(['candidate', 'show', 'alpha', '--id', 'C-0003'])
        assert old == invoke(['candidate', 'show', 'alpha', '--id', 'C-0001', '--revision', '1'])
        invoke(['candidate', 'status', 'alpha', '--id', 'C-0004', '--status', 'SCREENING',
            '--expected-revision', '1', '--reason', 'Use slot freed by recorded rejected revision'])
        missing = invoke(['candidate', 'show', 'alpha', '--id', 'C-NOT-FOUND'], expected=2)
        changed['hypothesis'] += ' with a cycle in the proposed tree'
        changed['parent'] = {'id': 'C-0003', 'revision': 1}
        cycle = propose(changed, revise=True, expected=2, revision=2)
        write(output / 'history-boundary-rejections.json', {'unknown_id': missing, 'cycle': cycle})
        final = invoke(['candidate', 'list', 'alpha'])
        write(output / 'final-candidate-tree.json', final)
        assert fingerprint(protected_paths, root) == protected, 'Candidate registration changed scientific/budget authority'
        assert not (root / 'forbidden-execution.jsonl').exists(), 'A command attempted forbidden execution or network access'
        receipt.update(steps_count=len(receipt['steps']), three_heterogeneous_candidates=True,
            duplicate_rejected_or_idempotent=True, fourth_active_rejected=True,
            immutable_revision_history=True, weakened_target_rejected=True,
            unreviewed_claim_ready_rejected=True, project_auto_resolution=True,
            rejected_branch_frees_capacity=True, independent_descendant_preserved=True,
            attempts_claims_budgets_states_goals_unchanged=True, scientific_discovery=False)
        write(output / 'acceptance.json', receipt)
        print(json.dumps({key: value for key, value in receipt.items() if key != 'steps'}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
