"""Bounded, single-problem attempts; every actual model invocation is charged."""
from __future__ import annotations
import copy
import re
import configuration
from .common import (goal_binding, ledger, policy, save_ledger, stamp, text,
                     fresh, object_hash, identifier, ledger_path)
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
    # A closed attempt does not erase an unresolved call or make its budget
    # available again. Recovery must identify the original owner run first.
    for attempt in ledger(project)['attempts']:
        for call in attempt['calls']:
            phase = call.get('status')
            if phase in {'RESERVED', 'PENDING_WRAPPER', 'SETTLING', 'SETTLEMENT_READY'}:
                if phase == 'SETTLING' and not _settlement_path(project, attempt['id'], call['run_id']).is_file():
                    raise ValueError('UNKNOWN_LOCAL_CHECK_OUTCOME: ' + call['run_id'])
                raise ValueError('DISCOVERY_SETTLEMENT_PENDING: ' + phase + ':' + call['run_id'])
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


def _settlement_path(project, attempt_id, run_id):
    return (ledger_path(project).parent / 'settlements' / configuration.project_id(project) /
            identifier(attempt_id) / (identifier(run_id) + '.json'))


def _owned_call(data, run_id):
    matches = [(a, c) for a in data['attempts'] for c in a['calls'] if c['run_id'] == run_id]
    if len(matches) > 1: raise ValueError('DISCOVERY_SETTLEMENT_AMBIGUOUS_RUN: ' + run_id)
    return matches[0] if matches else (None, None)


def _valid_project_manifest(value):
    return isinstance(value, dict) and all(
        isinstance(path, str) and path and not path.startswith('/')
        and '\\' not in path and ':' not in path
        and all(part not in {'', '.', '..'} for part in path.split('/'))
        and isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest)
        for path, digest in value.items())


def _read_settlement(project, attempt_id, run_id):
    path = _settlement_path(project, attempt_id, run_id)
    if not path.is_file(): raise ValueError('UNKNOWN_LOCAL_CHECK_OUTCOME: ' + run_id)
    try:
        receipt = configuration.load_json(path)
        body = {k: v for k, v in receipt.items() if k != 'receipt_sha256'}
        if (set(receipt) != {'schema_version', 'phase', 'project_id', 'attempt_id', 'run_id',
                'accepted', 'before_attempt', 'before_attempt_sha256', 'after_attempt',
                'after_attempt_sha256', 'checkpoint', 'created_at', 'receipt_sha256',
                'project_before_checks', 'project_after_checks'}
                or type(receipt['schema_version']) is not int or receipt['schema_version'] != 1
                or receipt['phase'] != 'SETTLEMENT_READY'
                or receipt['project_id'] != configuration.project_id(project)
                or receipt['attempt_id'] != attempt_id or receipt['run_id'] != run_id
                or type(receipt['accepted']) is not bool
                or receipt['receipt_sha256'] != object_hash(body)
                or receipt['before_attempt_sha256'] != object_hash(receipt['before_attempt'])
                or receipt['after_attempt_sha256'] != object_hash(receipt['after_attempt'])
                or not _valid_project_manifest(receipt['project_before_checks'])
                or not _valid_project_manifest(receipt['project_after_checks'])):
            raise ValueError('Invalid settlement receipt binding')
        before, call = _owned_call({'attempts': [receipt['before_attempt']]}, run_id)
        after, final = _owned_call({'attempts': [receipt['after_attempt']]}, run_id)
        if (before['id'] != attempt_id or after['id'] != attempt_id
                or call['status'] != 'SETTLING'
                or call['settlement_accepted'] != receipt['accepted']
                or final['status'] != ('ACCEPTED' if receipt['accepted'] else 'FAILED')):
            raise ValueError('Invalid settlement owner/phase')
        started = configuration.load_json(path.with_suffix('.started.json'), {})
        if (started.get('phase') != 'SETTLING' or started.get('project_id') != receipt['project_id']
                or started.get('attempt_id') != attempt_id or started.get('run_id') != run_id
                or started.get('attempt_sha256') != receipt['before_attempt_sha256']
                or started.get('project_before_checks') != receipt['project_before_checks']):
            raise ValueError('Missing or changed independent settlement-start witness')
        return receipt
    except (AttributeError, TypeError, KeyError, OSError, ValueError) as exc:
        raise ValueError('DISCOVERY_SETTLEMENT_RECEIPT_INVALID: ' + run_id) from exc


def settlement_observation(project, attempt_id, run_id):
    """Read a completed, owner-bound before/after observation without writes.

    The wrapper may adopt an interrupted controller check only when its frozen
    expected project equals before and the actual project equals after exactly.
    """
    return copy.deepcopy(_read_settlement(project, identifier(attempt_id), identifier(run_id)))


def _apply_settlement(project, receipt):
    """Replay only local afterimages; independent checks never run here."""
    run_id = receipt['run_id']
    from research_acceptance import manifest
    if manifest(project) != receipt['project_after_checks']:
        raise ValueError('DISCOVERY_SETTLEMENT_PROJECT_CHANGED: ' + run_id)
    before = receipt['before_attempt']
    ready = copy.deepcopy(before)
    _, call = _owned_call({'attempts': [ready]}, run_id)
    call.update(status='SETTLEMENT_READY', settlement_receipt_sha256=receipt['receipt_sha256'])
    after = copy.deepcopy(receipt['after_attempt'])
    _, final = _owned_call({'attempts': [after]}, run_id)
    final['settlement_receipt_sha256'] = receipt['receipt_sha256']
    data = ledger(project)
    current, _ = _owned_call(data, run_id)
    if current == after: return
    if current not in (before, ready): raise ValueError('DISCOVERY_SETTLEMENT_CONFLICT: ' + run_id)
    if current == before:
        data['attempts'][data['attempts'].index(current)] = ready
        save_ledger(project, data)
    if receipt['accepted'] and receipt['checkpoint'] is not None:
        path = (ledger_path(project).parent / 'checkpoints' / configuration.project_id(project) /
                receipt['attempt_id'] / (run_id + '.json'))
        if path.exists():
            if configuration.load_json(path) != receipt['checkpoint']:
                raise ValueError('DISCOVERY_SETTLEMENT_CHECKPOINT_CONFLICT: ' + run_id)
        else:
            configuration.atomic_json(path, receipt['checkpoint'])
    # Preserve other attempts and the operator's current active-attempt pointer.
    if _read_settlement(project, receipt['attempt_id'], run_id) != receipt:
        raise ValueError('DISCOVERY_SETTLEMENT_RECEIPT_CHANGED: ' + run_id)
    if manifest(project) != receipt['project_after_checks']:
        raise ValueError('DISCOVERY_SETTLEMENT_PROJECT_CHANGED: ' + run_id)
    data = ledger(project)
    current, _ = _owned_call(data, run_id)
    if current == after: return
    if current != ready: raise ValueError('DISCOVERY_SETTLEMENT_CONFLICT: ' + run_id)
    data['attempts'][data['attempts'].index(current)] = after
    save_ledger(project, data)


def _verify_terminal(project, item, call, *, required=False, accepted=None):
    path = _settlement_path(project, item['id'], call['run_id'])
    if not (required or call.get('settlement_receipt_sha256') or path.exists()
            or path.with_name(path.stem + '.started.json').exists()): return
    receipt = _read_settlement(project, item['id'], call['run_id'])
    _, expected = _owned_call({'attempts': [copy.deepcopy(receipt['after_attempt'])]}, call['run_id'])
    expected['settlement_receipt_sha256'] = receipt['receipt_sha256']
    if expected != call or (required and receipt['accepted'] != accepted):
        raise ValueError('DISCOVERY_TERMINAL_RECEIPT_CHANGED: ' + call['run_id'])


def finish_call(project, run_id, *, accepted, checkpoint=None, pending_wrapper=False):
    """Caller holds the core lock. Settle one reserved owner, at most once.

    SETTLING without a completed receipt is unknown, including hard termination
    during candidate/tool checks. It cannot be converted into a free retry.
    """
    identifier(run_id)
    if type(accepted) is not bool: raise ValueError('Discovery accepted must be boolean')
    data = ledger(project)
    item, call = _owned_call(data, run_id)
    if item is None: return
    if call['status'] in {'ACCEPTED', 'FAILED'}:
        _verify_terminal(project, item, call)
        return
    receipt_path = _settlement_path(project, item['id'], run_id)
    if call['status'] in {'SETTLING', 'SETTLEMENT_READY'} or receipt_path.exists():
        receipt = _read_settlement(project, item['id'], run_id)
        if receipt['accepted'] != accepted: raise ValueError('DISCOVERY_SETTLEMENT_DECISION_CHANGED: ' + run_id)
        _apply_settlement(project, receipt)
        return
    started_path = receipt_path.with_suffix('.started.json')
    if started_path.exists():
        # The attempt ledger may have been restored from an older backup. An
        # independent started witness still forbids repeating unknown checks.
        raise ValueError('UNKNOWN_LOCAL_CHECK_OUTCOME: ' + run_id)
    if call['status'] not in {'RESERVED', 'PENDING_WRAPPER'}:
        raise ValueError('DISCOVERY_SETTLEMENT_UNKNOWN_PHASE: ' + str(call['status']))
    if call['status'] == 'PENDING_WRAPPER' and checkpoint is not None and checkpoint != call.get('proposed_checkpoint'):
        raise ValueError('DISCOVERY_PENDING_CHECKPOINT_CHANGED: ' + run_id)
    if pending_wrapper and accepted:
        if call['status'] == 'PENDING_WRAPPER': return
        call.update(status='PENDING_WRAPPER', proposed_checkpoint=copy.deepcopy(checkpoint))
        save_ledger(project, data)
        return
    checkpoint = copy.deepcopy(checkpoint if checkpoint is not None else call.get('proposed_checkpoint'))
    from research_acceptance import manifest
    project_before_checks = manifest(project)
    call.update(status='SETTLING', settlement_accepted=accepted,
                settlement_checkpoint=checkpoint, settlement_started_at=stamp())
    save_ledger(project, data)  # Durable fence BEFORE any candidate or tool check.
    before = copy.deepcopy(item)
    configuration.atomic_json(started_path, {'schema_version': 1, 'phase': 'SETTLING',
        'project_id': configuration.project_id(project), 'attempt_id': item['id'],
        'run_id': run_id, 'attempt_sha256': object_hash(before),
        'checkpoint_sha256': object_hash(checkpoint), 'accepted': accepted, 'created_at': stamp(),
        'project_before_checks': project_before_checks})
    after = copy.deepcopy(item)
    _, final = _owned_call({'attempts': [after]}, run_id)
    final.update(status='ACCEPTED' if accepted else 'FAILED', finished_at=stamp())
    for key in ('proposed_checkpoint', 'settlement_accepted', 'settlement_checkpoint', 'settlement_started_at'):
        final.pop(key, None)
    if accepted:
        from .verification_engine import process_candidates
        final['independent_checks'] = process_candidates(project, checkpoint)
    from .research_evaluator import evaluate_checkpoint
    result = evaluate_checkpoint(project, checkpoint, before.get('checkpoint')) if accepted else {
        'procedural_progress': False, 'scientific_acceptance': False}
    final['evaluation'] = result
    if accepted and checkpoint is not None: after['checkpoint'] = checkpoint
    after['stagnation'] = 0 if result['procedural_progress'] else before['stagnation'] + 1
    if after['status'] != 'CLOSED':
        if len(after['calls']) >= after['budget']: after['status'] = 'BUDGET_EXHAUSTED'
        elif after['stagnation'] >= after['policy_snapshot']['stagnation_rounds']: after['status'] = 'PAUSED_STAGNATION'
    receipt = {'schema_version': 1, 'phase': 'SETTLEMENT_READY',
        'project_id': configuration.project_id(project), 'attempt_id': item['id'], 'run_id': run_id,
        'accepted': accepted, 'before_attempt': before, 'before_attempt_sha256': object_hash(before),
        'after_attempt': after, 'after_attempt_sha256': object_hash(after),
        'checkpoint': checkpoint if accepted else None, 'created_at': stamp(),
        'project_before_checks': project_before_checks, 'project_after_checks': manifest(project)}
    receipt['receipt_sha256'] = object_hash(receipt)
    if receipt_path.exists(): raise ValueError('DISCOVERY_SETTLEMENT_RECEIPT_CONFLICT: ' + run_id)
    configuration.atomic_json(receipt_path, receipt)
    _apply_settlement(project, _read_settlement(project, item['id'], run_id))


def finalize_wrapper(project, accepted, run_id=None, *, expected_attempt_id=None):
    data = ledger(project)
    if run_id is not None:
        item, call = _owned_call(data, identifier(run_id))
        if expected_attempt_id is not None:
            identifier(expected_attempt_id)
            if item is None: raise ValueError('DISCOVERY_OWNER_MISSING: ' + run_id)
            if item['id'] != expected_attempt_id: raise ValueError('DISCOVERY_OWNER_CHANGED: ' + run_id)
        if item is None: return
        if call['status'] in {'ACCEPTED', 'FAILED'}:
            _verify_terminal(project, item, call, required=expected_attempt_id is not None, accepted=accepted)
            return
        if call['status'] == 'RESERVED':
            raise ValueError('DISCOVERY_WRAPPER_RECEIPT_MISSING: ' + run_id)
        finish_call(project, run_id, accepted=accepted)
        return
    if expected_attempt_id is not None:
        raise ValueError('DISCOVERY_SETTLEMENT_OWNER_REQUIRES_RUN_ID')
    item = next((a for a in data['attempts'] if a['id'] == data.get('active_attempt')), None)
    if item is None: return
    for call in item['calls']:
        if call['status'] in {'PENDING_WRAPPER', 'SETTLING', 'SETTLEMENT_READY'}:
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
