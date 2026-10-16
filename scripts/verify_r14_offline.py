"""R14 protocol review acceptance through real commands in synthetic projects.

All checks are bounded declared data and metadata. No reviewer model, network,
Lean, supervisor, attack program or nested command is permitted by the fixture.
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
from engine.common import object_hash
from candidate_search import security_model as security_schema
from verify_r03_offline import fingerprint, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output.resolve()
    if any(output.is_relative_to(SOURCE / name) for name in ('projects', 'state', 'logs', 'config')):
        raise ValueError('Evidence must be outside project/runtime/config trees')
    output.mkdir(parents=True, exist_ok=True)
    receipt = {'round': 'R14', 'fixture_only': True, 'provider_requests': 0, 'network_requests': 0,
               'lean_executions': 0, 'supervision_executions': 0, 'nested_program_executions': 0, 'steps': []}
    with tempfile.TemporaryDirectory(prefix='crc r14 native fixture ') as directory:
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
def guard(event,args):
    if event in {'subprocess.Popen','socket.connect','socket.getaddrinfo','os.system','os.exec','os.posix_spawn','os.spawn'}:
        with open(os.environ['CRC_R14_DENIED_LOG'],'a',encoding='utf8') as log:log.write(event+'\\n')
        raise RuntimeError('R14 fixture forbids all network and nested execution: '+event)
sys.addaudithook(guard)
""")
        env = dict(os.environ, CRC_PYTHON=sys.executable, PYTHONDONTWRITEBYTECODE='1',
            PYTHONIOENCODING='utf8', PYTHONPATH=str(root), PYTHONNOUSERSITE='1',
            PATH=str(root) + os.pathsep + os.environ.get('PATH', ''),
            CRC_R14_DENIED_LOG=str(root / 'forbidden-execution.jsonl'))
        entry = (['cmd.exe', '/d', '/c', 'research.cmd'] if os.name == 'nt'
                 else [sys.executable, '-B', str(root / 'research.py')])
        receipt['entry'] = 'research.cmd' if os.name == 'nt' else 'research.py'

        def invoke(args, expected=0, *, cwd=root):
            result = subprocess.run(entry + args, cwd=cwd, env=env, capture_output=True,
                                    text=True, encoding='utf8', timeout=60)
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

        project = root / 'projects/alpha'
        state = {'phase': 'PROOF', 'decision': 'CONTINUE', 'research_route': 'MAIN', 'selected_idea': None,
            'last_run': 'toy-r2', 'priority_problem': 'Original toy protocol obligation',
            'next_task': 'Check original simulator interface without weakening the model',
            'accepted_contribution': {'status': 'NOT_ESTABLISHED', 'fixture_sentinel': 'retain'}}
        for relative, value in {'PROJECT.json': {'id': 'alpha', 'checks': []},
            'GOAL.md': 'Frozen toy protocol: static malicious corruption of at most one of three parties.\n',
            'AGENTS.md': 'Infrastructure fixtures only; no mathematical security acceptance from reports.\n',
            'RESEARCH_PROFILE.json': {'profiles': [], 'read_order': []}, 'research/STATE.json': state,
            'proofs/security.md': 'Pending toy simulator and game correspondence; no security theorem is claimed.\n',
            'proofs/auxiliary.md': 'Independent toy proof input for source SHA expiration only.\n',
            'research/GATES.json': {'G8': 'INDEPENDENT_REVIEW_REQUIRED', 'fixture_sentinel': 'retain'},
            'research/accepted_contribution.json': {'accepted': False, 'fixture_sentinel': 'retain'}}.items():
            write(project / relative, value)
        assumptions = ['Static malicious corruption', 'Authenticated channels']
        template_file = SOURCE / 'templates/project/research/SECURITY_OBLIGATION_TEMPLATE.json'
        template = json.loads(template_file.read_text(encoding='utf-8-sig'))
        card = copy.deepcopy(template)
        card['proof_paths'] = ['proofs/security.md']
        card['security_game'].update(definition='A frozen declared toy game; no security theorem is certified.',
                                     rounds=1, public_outputs=['output'])
        card['parties'] = ['client', 'server', 'auditor']
        card['corruption_model'].update(timing='STATIC', claimed_timing='STATIC', threshold=1,
            claimed_threshold=1, corrupted_parties=['server'], dropout_model='NONE')
        card['leakage_function'].update(name='L-main', real_observable=['output'], ideal_leakage=['output'],
                                         cross_round_linkage='NONE')
        card['setup_assumptions'] = copy.deepcopy(assumptions)
        card['abort_behavior'] = {key: False for key in card['abort_behavior']}
        card['simulator_interface'].update(ideal_inputs=['output'], required_inputs=['output'],
                                            output_dependencies={'output': ['output']})
        card['reduction_loss'].update(parameters=['n'], bit_widths={'n': 32}, rounds=1, failure_events=['abort'],
            loss_bound='Declared symbolic loss; exact reduction still requires independent review')
        card['composition_scope'].update(sessions=1, rounds=1, cross_round_collusion='NONE',
                                          end_to_end_reduction='Explicit pending end-to-end simulator obligation')
        for row in card['baseline_comparison']:
            row.update(assumptions='Exact setup still needs theorem-level comparison', functionality='Frozen toy output',
                       cost='UNASSESSED', difference='No independently reviewed novelty or complexity assertion')

        model = {'corruption_timing': 'STATIC', 'corruption_threshold': 1, 'leakage_function': 'L-main', 'party_count': 3}
        model['ideal_interface_sha256'] = object_hash(security_schema.ideal_interface_binding(card))
        problem = {'schema_version': 1, 'id': 'P-1', 'title': 'Frozen toy protocol game',
            'statement': 'Preserve the exact toy functionality, simulator inputs and declared leakage',
            'quantifiers': 'For every original static malicious toy adversary with at most one corruption',
            'domain': 'Finite declared toy transcripts', 'input_contract': 'Original toy public and private inputs',
            'output_contract': 'Exact toy public outputs and explicitly declared rejection leakage',
            'goal_connection': 'Original frozen toy security model only',
            'nontriviality_argument': 'Infrastructure-only protocol review fixture',
            'assumptions': assumptions,
            'immutable_constraints': ['Do not weaken original corruption timing, threshold or leakage'],
            'baseline_exclusions': ['No new security theorem or novelty assertion'],
            'contribution_type': 'SECURITY_THEOREM', 'security_model': model, 'source_paths': [],
            'obligations': [{'id': 'O-1', 'statement': 'Original game and simulator correspondence',
                'acceptance_criterion': 'Independent full statement and security argument review'}]}
        file = root / 'input.json'
        write(file, problem)
        invoke(['problem', 'import', 'alpha', '--file', str(file), '--reason', 'Register frozen synthetic protocol game'])
        claim = {'schema_version': 1, 'id': 'SECURITY-1', 'statement': problem['statement'],
            'assumptions': problem['assumptions'], 'dependencies': [], 'proposer': 'fixture-proposer',
            'problem_id': 'P-1', 'problem_version': 1, 'obligation_ids': ['O-1'],
            'nontriviality_argument': 'Unreviewed toy protocol claim only', 'contribution_type': 'SECURITY_THEOREM',
            'evidence_paths': ['proofs/security.md'], 'verification_mode': 'INDEPENDENT_MANUAL',
            'formal_applicability_reason': 'Protocol-level independent review is still necessary; no real Lean execution'}
        write(file, claim)
        imported = invoke(['claim', 'import', 'alpha', '--file', str(file), '--reason', 'Register unreviewed toy security claim'])
        epoch = {'epoch': 1, 'route': 'MAIN', 'effective_rounds': 2, 'stagnation': 0, 'extensions_used': 0,
            'counted_run_ids': ['toy-r1', 'toy-r2'], 'last_processed_run': 'toy-r2', 'review_pending': False,
            'focus': make_focus(project, state)}
        route_budget.save_ledger(root / 'state/routes/alpha.json', {'schema_version': 1, 'project_id': 'alpha',
            'epochs': [epoch], 'events': [{'type': 'RESEARCH_ROUND', 'run_id': run} for run in ('toy-r1', 'toy-r2')]})
        anchor = invoke(['candidate', 'anchor', 'alpha'])['goal_anchor_id']
        candidate = {'schema_version': 1, 'id': 'C-0001', 'title': 'Frozen synthetic protocol candidate',
            'goal_anchor_id': anchor, 'problem_id': 'P-1', 'problem_version': 1,
            'hypothesis': 'An exact toy construction may realize the original frozen functionality',
            'nontriviality_argument': 'A falsifiable simulator hypothesis, not an accepted security statement',
            'closest_prior_work': [{'source_id': 'TOY-PAPER-1', 'check': 'Check the original theorem and all premises',
                                    'full_text_checked': False}],
            'falsification_gate': 'Exhibit a scoped view difference under the original toy corruption and leakage model',
            'proof_obligations': ['O-1'], 'assumptions': problem['assumptions'],
            'immutable_constraints': problem['immutable_constraints'], 'domain': problem['domain'],
            'quantifiers': problem['quantifiers'], 'security_model': model, 'estimated_context_bytes': 4096,
            'dependency_claims': [{name: imported[name] for name in ('id', 'revision', 'spec_sha256')}],
            'evidence_refs': [], 'failure_scope': 'Only explicitly declared toy transcripts under the frozen model',
            'restart_conditions': 'An explicit new candidate revision and independent model review'}
        write(file, candidate)
        invoke(['candidate', 'propose', 'alpha', '--file', str(file), '--reason', 'Register unreviewed protocol candidate'])
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
            result = invoke(args, expected, **kwargs)
            assert protected() == before, 'Security review changed original scientific or budget authority'
            return result

        fixed_paths = [root / 'state/routes', root / 'state/route_registry', root / 'state/discovery', root / 'state/supervision']
        fixed_budgets = fingerprint(fixed_paths, root)
        fixed_state, fixed_goal = (project / 'research/STATE.json').read_bytes(), (project / 'GOAL.md').read_bytes()
        fixed_gates = (project / 'research/GATES.json').read_bytes()
        def prepare(value):
            write(file, value)
            return unchanged(['candidate', 'security-prepare', 'alpha', '--id', 'C-0001',
                '--claim', 'SECURITY-1', '--card', str(file)])

        def review(request, expected=0):
            write(file, request)
            return unchanged(['candidate', 'security-review', 'alpha', '--request', str(file)], expected)

        def codes(report):
            return {finding['code'] for finding in report['findings']}

        normal_request = prepare(card)
        normal = review(normal_request)
        assert normal['decision'] == 'NEEDS_REVIEW' and normal['finding_level'] == 'REVIEW_FINDING', normal
        assert not normal['scientific_acceptance'] and not normal['claim_status_changed'] and not normal['candidate_status_changed']
        assert len(normal['framework_comparison']) == 3
        write(output / 'normal-obligation-request.json', normal_request)
        write(output / 'normal-obligation-review.json', normal)
        before = fingerprint([root / 'state'], root)
        assert normal == review(normal_request), 'Identical frozen review was not idempotent'
        assert before == fingerprint([root / 'state'], root)
        unchanged(['candidate', 'security-show', 'alpha', '--request-id', normal_request['request_id']])
        unchanged(['candidate', 'security-recheck', 'alpha', '--request-id', normal_request['request_id']])
        inferred = unchanged(['candidate', 'security-show', '--request-id', normal_request['request_id']], cwd=project)
        assert inferred['fresh']
        missing = review(prepare(copy.deepcopy(template)), expected=2)
        assert missing['decision'] == 'NEEDS_INPUT' and not missing['threat_model_complete']
        write(output / 'missing-model-needs-input.json', missing)

        def step(**updates):
            value = {'round': 1, 'corrupted_parties': ['server'], 'public_inputs': {'query': 'q'},
                'secret_assignment': {'secret': 0}, 'ideal_leakage': {'output': 'same'}, 'public_output': {'output': 'same'}}
            value.update(updates)
            return value

        def trace(kind, steps):
            return {'id': 'A-1', 'kind': kind, 'game': 'GAME-main', 'proof_step': 'hybrid-1',
                'affected_obligations': ['O-1'], 'execution': steps, 'scope': 'Explicit toy inputs only; no protocol execution',
                'restart_conditions': 'A new explicitly reviewed model and candidate revision'}

        threshold = copy.deepcopy(card)
        threshold['corruption_model']['claimed_threshold'] = 2
        threshold['attack_traces'] = [trace('CORRUPTION_THRESHOLD', [step(corrupted_parties=['server', 'auditor'])])]
        threshold_report = review(prepare(threshold), expected=2)
        assert threshold_report['decision'] == 'NEEDS_INPUT'
        assert 'MODEL_SCOPE_MISMATCH' in codes(threshold_report)
        assert threshold_report['attack_plans'][0]['status'] == 'OUT_OF_SCOPE'
        assert threshold_report['attack_plans'][0]['counterexample_to_frozen_goal'] is False
        write(output / 'out-of-scope-corruption-trace.json', threshold_report)
        rejection = copy.deepcopy(card)
        rejection['abort_behavior'].update(public_reject_bit=True, ideal_reject_bit=False)
        rejection['leakage_function']['real_observable'].append('reject_bit')
        rejection['attack_traces'] = [trace('SELECTIVE_REJECTION', [
            step(public_output={'output': 'same', 'reject_bit': False}),
            step(secret_assignment={'secret': 1}, public_output={'output': 'same', 'reject_bit': True})])]
        rejection_report = review(prepare(rejection), expected=2)
        assert 'REJECTION_BIT_OMITTED_FROM_IDEAL_LEAKAGE' in codes(rejection_report)
        assert rejection_report['attack_plans'][0]['status'] == 'FINITE_TRACE_DIFFERENCE_REQUIRES_REVIEW'
        write(output / 'selective-rejection-visible-bit.json', rejection_report)
        simulator = copy.deepcopy(card)
        simulator['simulator_interface']['required_inputs'].append('secret_key')
        simulator['simulator_interface']['required_programming'] = ['random_oracle']
        simulator['simulator_interface']['output_dependencies']['output'] = ['secret_key']
        simulator['attack_traces'] = [trace('SIMULATOR_PUBLIC_OUTPUT', [
            step(public_output={'output': 0}), step(secret_assignment={'secret': 1}, public_output={'output': 1})])]
        simulator_report = review(prepare(simulator))
        assert {'SIMULATOR_INPUT_UNAVAILABLE', 'UNAUTHORIZED_SIMULATOR_PROGRAMMING'} <= codes(simulator_report)
        write(output / 'simulator-missing-ideal-input.json', simulator_report)
        self_authorized = copy.deepcopy(simulator)
        self_authorized['simulator_interface']['ideal_inputs'].append('secret_key')
        self_authorized['simulator_interface']['authorized_programming'].append('random_oracle')
        unauthorized_report = review(prepare(self_authorized), expected=2)
        assert unauthorized_report['decision'] == 'NEEDS_INPUT' and 'MODEL_SCOPE_MISMATCH' in codes(unauthorized_report)
        write(output / 'card-cannot-authorize-own-secrets.json', unauthorized_report)
        adaptive = copy.deepcopy(card)
        adaptive['corruption_model']['claimed_timing'] = 'ADAPTIVE'
        adaptive_report = review(prepare(adaptive), expected=2)
        assert adaptive_report['decision'] == 'NEEDS_INPUT'
        assert 'MODEL_SCOPE_MISMATCH' in codes(adaptive_report)
        write(output / 'static-does-not-imply-adaptive.json', adaptive_report)
        cross_round = copy.deepcopy(card)
        cross_round['composition_scope'].update(rounds=2, cross_round_collusion=None)
        cross_round['leakage_function']['cross_round_linkage'] = 'UNDEFINED'
        cross_round_report = review(prepare(cross_round), expected=2)
        assert cross_round_report['decision'] == 'NEEDS_INPUT' and 'CROSS_ROUND_COLLUSION_UNDEFINED' in codes(cross_round_report)
        write(output / 'cross-round-scope-needs-input.json', cross_round_report)
        source = copy.deepcopy(card)
        source['dependencies'] = [{'span_id': None, 'source_file': None, 'version': None, 'sha256': None,
            'location': None, 'required_assumptions': ['Authenticated channels'], 'used_assumptions': [],
            'proof_step': 'hybrid-1'}]
        source_report = review(prepare(source), expected=2)
        assert source_report['decision'] == 'NEEDS_SOURCE' and source_report['source_checks'][0]['status'] == 'UNVERIFIED'
        assert 'THEOREM_PREMISES_OMITTED' in codes(source_report)
        write(output / 'missing-original-theorem-location.json', source_report)
        omitted = copy.deepcopy(card)
        omitted['setup_assumptions'] = []
        omitted_report = review(prepare(omitted))
        assert 'FROZEN_PREMISES_OMITTED' in codes(omitted_report)
        write(output / 'omitted-frozen-premises.json', omitted_report)
        cheap = copy.deepcopy(card)
        cheap['baseline_comparison'][0]['cost'] = 'O(1) claimed without any verified decomposition'
        cheap_request = prepare(cheap)
        cheap_report = review(cheap_request)
        assert cheap_report['cost_assessment']['status'] == 'UNASSESSED'
        write(output / 'cheap-without-breakdown-unassessed.json', cheap_report)
        covered = copy.deepcopy(card)
        covered['baseline_comparison'][0]['relation'] = 'DIRECT_COMPOSITION'
        covered_request = prepare(covered)
        covered_report = review(covered_request)
        assert 'POTENTIALLY_COVERED' in codes(covered_report) and not covered_report['candidate_status_changed']
        write(output / 'standard-framework-comparison.json', covered_report)
        auxiliary = copy.deepcopy(card)
        auxiliary['proof_paths'].append('proofs/auxiliary.md')
        auxiliary_request = prepare(auxiliary)
        review(auxiliary_request)
        write(project / 'proofs/auxiliary.md', 'Changed after the exact security review source SHA was frozen.\n')
        expired_source = unchanged(['candidate', 'security-recheck', 'alpha', '--request-id', auxiliary_request['request_id']], expected=2)
        assert expired_source['decision'] == 'FAILED'
        assert review(auxiliary_request, expected=2)['decision'] == 'FAILED'
        write(output / 'source-sha-expiration.json', expired_source)
        for key, value in (('G8', 'PASS'), ('accepted_contribution', True), ('reviewer_attestation', 'independent')):
            forbidden = copy.deepcopy(card)
            forbidden[key] = value
            write(file, forbidden)
            unchanged(['candidate', 'security-prepare', 'alpha', '--id', 'C-0001', '--claim', 'SECURITY-1',
                       '--card', str(file)], expected=2)

        # A missing original request may not be reconstructed from the caller's
        # live copy while its dispatch and completion records still exist.
        metadata_root = (root / 'state/candidates/alpha/security_review').resolve()
        missing_request_path = (metadata_root / (cheap_request['request_id'] + '.request.json')).resolve()
        assert missing_request_path.is_relative_to(metadata_root) and missing_request_path.is_file()
        missing_request_path.unlink()
        before = fingerprint([root / 'state'], root)
        missing_request_result = review(cheap_request, expected=2)
        assert 'UNKNOWN_LOCAL_SECURITY_REVIEW_OUTCOME' in json.dumps(missing_request_result)
        assert before == fingerprint([root / 'state'], root)
        write(output / 'missing-frozen-input-blocks-reconstruction.json', missing_request_result)

        # Remove one complete metadata afterimage only inside this fixture. The
        # frozen request and STARTED witness must prevent a silent second review.
        report_files = []
        for path in (root / 'state/candidates/alpha').rglob('*.json'):
            if json.loads(path.read_text(encoding='utf-8-sig')) == covered_report:
                report_files.append(path)
        assert len(report_files) == 1, report_files
        lost = report_files[0].resolve()
        assert lost.is_relative_to((root / 'state/candidates/alpha').resolve())
        lost.unlink()
        before = fingerprint([root / 'state'], root)
        unknown = review(covered_request, expected=2)
        assert unknown['decision'] == 'FAILED' and 'UNKNOWN_LOCAL_SECURITY_REVIEW_OUTCOME' in json.dumps(unknown)
        assert before == fingerprint([root / 'state'], root), 'Unknown outcome caused automatic re-review'
        assert unknown == review(covered_request, expected=2)
        write(output / 'unknown-local-review-outcome.json', unknown)
        revised = copy.deepcopy(claim)
        revised['statement'] += ' Explicit revised operator-owned toy statement.'
        write(file, revised)
        invoke(['claim', 'import', 'alpha', '--file', str(file), '--reason', 'Explicit toy claim revision for expiration test'])
        stale = unchanged(['candidate', 'security-recheck', 'alpha', '--request-id', normal_request['request_id']], expected=2)
        assert stale['decision'] == 'FAILED'
        write(output / 'claim-revision-expiration.json', stale)
        historical = unchanged(['candidate', 'security-show', 'alpha', '--request-id', normal_request['request_id']])
        assert historical['fresh'] is False
        write(output / 'historical-stale-report.json', historical)
        assert fixed_budgets == fingerprint(fixed_paths, root)
        assert (project / 'research/STATE.json').read_bytes() == fixed_state
        assert (project / 'GOAL.md').read_bytes() == fixed_goal
        assert (project / 'research/GATES.json').read_bytes() == fixed_gates
        assert not (root / 'forbidden-execution.jsonl').exists(), 'Attempted forbidden program or network execution'
        write(output / 'execution-audit.json', {'nested_program_executions': 0, 'provider_requests': 0,
            'network_requests': 0, 'lean_executions': 0, 'supervision_executions': 0, 'denied_operations': []})
        receipt.update(steps_count=len(receipt['steps']), normal_obligations_are_review_findings_only=True,
            three_scoped_attack_gap_plans=True, threshold_outside_frozen_game_is_not_a_protocol_break=True,
            static_not_upgraded_to_adaptive=True, missing_model_needs_input=True,
            card_cannot_self_authorize_simulator_secrets=True, undefined_cross_round_model_needs_input=True,
            missing_theorem_location_unverified=True, omitted_frozen_premises_reported=True,
            missing_cost_breakdown_unassessed=True, three_standard_frameworks_compared=True,
            authoritative_fields_rejected=True, idempotent_review=True, unknown_outcome_blocks_retry=True,
            source_sha_expires_review=True, missing_frozen_input_blocks_reconstruction=True,
            old_claim_revision_expires_report=True, no_canonical_review_writes=True,
            original_budgets_states_goals_gates_preserved=True, scientific_discovery=False)
        write(output / 'acceptance.json', receipt)
        print(json.dumps({key: value for key, value in receipt.items() if key != 'steps'}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
