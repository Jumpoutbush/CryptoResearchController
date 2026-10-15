"""Bounded, single-problem attempts; every actual model invocation is charged."""
from __future__ import annotations
import copy
from .common import (goal_binding, ledger, policy, save_ledger, stamp, text,
                     fresh, object_hash, identifier)
from .problem_compiler import get_problem

DEFAULTS = {
    'schema_version': 1, 'enabled': True, 'strategy': 'single_deep_reasoner',
    'initial_round_budget': 6, 'stagnation_rounds': 3, 'extension_round_budget': 4,
    'max_extensions': 1, 'max_independent_attempts': 3,
    'automatic_falsification': True, 'falsification_every': 2,
    'require_theorem_level_novelty': True, 'require_independent_verification': True,
    'formal_verification': 'when_applicable', 'preserve_proof_obligations': True,
    'invalidate_dependent_claims': True, 'allow_unapproved_goal_changes': False,
    'counterexample_max_cases': 10000, 'counterexample_max_seconds': 3,
    'verifier_timeout_seconds': 120,
}


def validate_policy(obj):
    if not isinstance(obj, dict) or set(obj) != set(DEFAULTS): raise ValueError('Invalid discovery_policy keys')
    if obj['schema_version'] != 1 or obj['strategy'] != 'single_deep_reasoner':
        raise ValueError('Only schema 1 / single_deep_reasoner is implemented')
    for key, low, high in [('initial_round_budget', 1, 100), ('stagnation_rounds', 1, 100),
        ('extension_round_budget', 1, 100), ('max_extensions', 0, 5),
        ('max_independent_attempts', 1, 10), ('falsification_every', 1, 10),
        ('counterexample_max_cases', 1, 100000), ('counterexample_max_seconds', 1, 10),
        ('verifier_timeout_seconds', 1, 600)]:
        if type(obj[key]) is not int or not low <= obj[key] <= high: raise ValueError('Invalid discovery ' + key)
    for key in ('enabled', 'automatic_falsification'):
        if type(obj[key]) is not bool: raise ValueError('Discovery ' + key + ' must be boolean')
    for key in ('require_theorem_level_novelty', 'require_independent_verification',
                'preserve_proof_obligations', 'invalidate_dependent_claims'):
        if obj[key] is not True: raise ValueError(key + ' is a required discovery invariant')
    if obj['allow_unapproved_goal_changes'] is not False: raise ValueError('Unapproved goal changes are forbidden')
    if obj['formal_verification'] not in {'when_applicable', 'required'}:
        raise ValueError('formal_verification must be when_applicable/required')
    return obj


def active(project):
    data = ledger(project)
    return next((a for a in data['attempts'] if a['id'] == data.get('active_attempt')), None)


def start(project, problem_id, *, version=None):
    config = policy(project)
    if not config['enabled']: raise ValueError('Discovery is disabled by policy')
    import configuration
    state = configuration.load_json(project / 'research/STATE.json', {})
    if state.get('initialization_required') or state.get('initialization_status') == 'NEEDS_INPUT':
        raise ValueError('Complete idea-driven initialization and resolve blocking input gaps first')
    if (project / '.control/STOP_REQUESTED').exists(): raise ValueError('Clear the explicit stop request before starting an attempt')
    data = ledger(project)
    if data.get('active_attempt'): raise ValueError('Close the current attempt before starting another')
    problem = get_problem(project, problem_id, version)
    if problem['goal_sha256'] != goal_binding(project)['files']['GOAL.md']:
        raise ValueError('Goal changed since problem compilation; import a reviewed problem revision')
    if not fresh(project, problem['source_bindings']): raise ValueError('Problem source evidence changed')
    previous = [a for a in data['attempts'] if a['problem_id'] == problem_id]
    if len(previous) >= config['max_independent_attempts']:
        raise ValueError('Independent attempt budget exhausted for this problem ID')
    attempt = {'id': 'attempt-' + str(len(data['attempts']) + 1).zfill(4),
        'problem_id': problem_id, 'problem_version': problem['version'],
        'problem_sha256': problem['spec_sha256'], 'binding': goal_binding(project),
        'policy_snapshot': copy.deepcopy(config), 'created_at': stamp(), 'status': 'ACTIVE',
        'budget': config['initial_round_budget'], 'extensions': 0, 'calls': [],
        'stagnation': 0, 'checkpoint': None, 'close_reason': None}
    data['attempts'].append(attempt)
    data['active_attempt'] = attempt['id']
    save_ledger(project, data)
    state.update(phase='PROOF', decision='CONTINUE', priority_problem=problem['spec']['title'],
        next_task='Continue the frozen problem ' + problem_id + ' from obligation ' + problem['spec']['obligations'][0]['id'] + '; preserve its assumptions and output requirements.')
    configuration.atomic_json(project / 'research/STATE.json', state)
    return attempt


def check(project):
    item = active(project)
    if item is None: return None
    if not policy(project)['enabled']: raise ValueError('Discovery disabled with an active attempt')
    if item['binding'] != goal_binding(project):
        raise ValueError('ATTEMPT_STALE: goal, route, idea or security constraints changed; close and review')
    problem = get_problem(project, item['problem_id'], item['problem_version'])
    if problem['spec_sha256'] != item['problem_sha256'] or not fresh(project, problem['source_bindings']):
        raise ValueError('ATTEMPT_STALE: pinned problem or source changed')
    if item['status'] != 'ACTIVE': raise ValueError('ATTEMPT_PAUSED: ' + item['status'])
    if len(item['calls']) >= item['budget']: raise ValueError('ATTEMPT_BUDGET_EXHAUSTED')
    if item['checkpoint'] and not fresh(project, item['checkpoint'].get('evidence', {})):
        raise ValueError('ATTEMPT_STALE: accepted checkpoint evidence changed; review before continuing')
    return item


def slot(item):
    config = item['policy_snapshot']
    number = len(item['calls']) + 1
    if config['automatic_falsification'] and number % config['falsification_every'] == 0:
        return 'FALSIFICATION'
    return 'DEEP_PROOF'


def begin_call(project, run_id):
    item = check(project)
    if item is None: return None
    data = ledger(project)
    current = next(a for a in data['attempts'] if a['id'] == item['id'])
    if any(c['run_id'] == run_id for c in current['calls']): raise ValueError('Duplicate discovery call ID')
    current['calls'].append({'run_id': identifier(run_id), 'started_at': stamp(),
                             'mode': slot(item), 'status': 'RESERVED'})
    save_ledger(project, data)
    return current


def finish_call(project, run_id, *, accepted, checkpoint=None, pending_wrapper=False):
    data = ledger(project)
    item = next((a for a in data['attempts'] if any(c['run_id'] == run_id for c in a['calls'])), None)
    if item is None: return
    call = next(c for c in item['calls'] if c['run_id'] == run_id)
    if pending_wrapper and accepted:
        call['status'] = 'PENDING_WRAPPER'
        call['proposed_checkpoint'] = checkpoint
        save_ledger(project, data)
        return
    if call['status'] in {'ACCEPTED', 'FAILED'}: return
    checkpoint = checkpoint or call.pop('proposed_checkpoint', None)
    call['status'] = 'ACCEPTED' if accepted else 'FAILED'
    call['finished_at'] = stamp()
    if accepted:
        from .verification_engine import process_candidates
        call['independent_checks'] = process_candidates(project, checkpoint)
    from .research_evaluator import evaluate_checkpoint
    result = evaluate_checkpoint(project, checkpoint, item.get('checkpoint')) if accepted else {'procedural_progress': False, 'scientific_acceptance': False}
    call['evaluation'] = result
    if accepted and checkpoint:
        item['checkpoint'] = checkpoint
        # Archive exact accepted external state; never store hidden reasoning traces.
        import configuration
        from .common import ledger_path
        configuration.atomic_json(ledger_path(project).parent / 'checkpoints' /
            configuration.project_id(project) / item['id'] / (run_id + '.json'), checkpoint)
    item['stagnation'] = 0 if result['procedural_progress'] else item['stagnation'] + 1
    if len(item['calls']) >= item['budget']: item['status'] = 'BUDGET_EXHAUSTED'
    elif item['stagnation'] >= item['policy_snapshot']['stagnation_rounds']: item['status'] = 'PAUSED_STAGNATION'
    save_ledger(project, data)


def finalize_wrapper(project, accepted, run_id=None):
    item = active(project)
    if item is None: return
    for call in item['calls']:
        if call['status'] == 'PENDING_WRAPPER' and (run_id is None or call['run_id'] == run_id):
            finish_call(project, call['run_id'], accepted=accepted)


def extend(project, reason):
    text(reason, 'extension reason')
    data = ledger(project); item = active(project)
    if item is None: raise ValueError('No active attempt')
    target = next(a for a in data['attempts'] if a['id'] == item['id'])
    config = target['policy_snapshot']
    if target['extensions'] >= config['max_extensions']: raise ValueError('Attempt extension limit reached')
    target['extensions'] += 1
    target['budget'] += config['extension_round_budget']
    target['status'] = 'ACTIVE'; target['stagnation'] = 0
    target.setdefault('extension_reasons', []).append({'reason': reason, 'at': stamp()})
    save_ledger(project, data)
    return target


def close(project, reason):
    text(reason, 'close reason')
    data = ledger(project)
    item = next((a for a in data['attempts'] if a['id'] == data.get('active_attempt')), None)
    if item is None: raise ValueError('No active attempt')
    item['status'] = 'CLOSED'; item['closed_at'] = stamp(); item['close_reason'] = reason
    data['active_attempt'] = None
    save_ledger(project, data)
    return item
