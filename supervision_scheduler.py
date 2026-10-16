"""R02 queue-only supervision scheduling, using authoritative route receipts.

The new protocol is opt-in; the existing per-project supervision policy remains
the activation and budget authority. No function here invokes a model or writes
research state, routes, claims, attempts, or guidance.
"""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
import copy
import math
from pathlib import Path
import secrets

import configuration
import supervision
import supervision_ledger as queue
from supervision_contracts import canonical_hash, load_defaults, make_event
from supervision_snapshot import build_snapshot, _path
from route_budget import file_lock, stamp


def enabled(controller, project):
    return load_defaults(controller)['enabled'] and supervision.policy_for(controller, project)['enabled']


@contextmanager
def _locks(controller, project, *, route_lock_held=False, execution=False):
    controller = Path(controller)
    key = configuration.project_id(project)
    with ExitStack() as stack:
        if not route_lock_held: stack.enter_context(file_lock(_path(controller, 'locks/route-' + key + '.lock')))
        if execution: stack.enter_context(file_lock(_path(controller, 'locks/' + key + '.lock')))
        stack.enter_context(file_lock(_path(controller, 'locks/supervision-queue-' + key + '.lock')))
        yield


def restrictions(controller, project):
    state = configuration.load_json(supervision._safe(project, 'research/STATE.json'), {})
    reasons, blocked = [], False
    if supervision._safe(project, '.control/STOP_REQUESTED').exists(): reasons.append('STOP_REQUESTED'); blocked = True
    if state.get('decision') in {'STOP', 'PAUSE', 'NEEDS_INPUT', 'NEEDS_REVIEW'} or state.get('phase') == 'DONE':
        reasons.append('RESEARCH_STATE_' + str(state.get('decision'))); blocked = True
    data = supervision._load(controller, project)
    if data:
        if data.get('pending_transaction'): reasons.append('INCOMPLETE_SUPERVISION_TRANSACTION'); blocked = True
        active = data['records'].get(data.get('active_review'), {})
        if active.get('decision') in {'PAUSE', 'RECOMMEND_STOP'}:
            reasons.append('OPERATOR_REVIEW_REQUIRED'); blocked = True
    attempt = configuration.load_json(_path(controller, 'state/discovery/' + configuration.project_id(project) + '.json'), {})
    if attempt.get('active_attempt'): reasons.append('ACTIVE_ATTEMPT_READONLY')
    return {'claim_allowed': not blocked, 'can_apply_guidance': False, 'can_change_route': False, 'restrictions': reasons}


def pending(controller, project):
    """Read-only: missing files remain missing, including locks and ledgers."""
    guard = restrictions(controller, project)
    result = queue.view(controller, project)
    for event in result['events']:
        event_guard = _event_guard(controller, project, queue.read_event(controller, project, event['event_id']))
        event.update(event_guard)
        event['claim_allowed'] = event_guard['claim_allowed'] and event['state'] == 'QUEUED' and enabled(controller, project)
    result['deferred'] = [d for d in result['deferred'] if d['status'] == 'DEFERRED_TO_ROUTE_REVIEW']
    return {'enabled': enabled(controller, project), 'protocol': 'R02_QUEUE_ONLY', **result}


def _receipt(controller, project, ledger, epoch, run_id, reviewed):
    path = _path(controller, 'state/routes/' + configuration.project_id(project) + '.json')
    if configuration.load_json(path) != ledger: raise ValueError('Queue requires the committed route receipt ledger')
    if not ledger.get('epochs') or epoch != ledger['epochs'][-1]:
        raise ValueError('Queue epoch differs from the authoritative current epoch')
    state = configuration.load_json(supervision._safe(project, 'research/STATE.json'), {})
    review_path = supervision._safe(project, 'research/ROUND_REVIEW.json')
    review = configuration.load_json(review_path)
    if (state.get('last_run') != run_id or epoch.get('last_processed_run') != run_id
            or not isinstance(review, dict) or type(review.get('schema_version')) is not int
            or review['schema_version'] != 1 or review.get('run_id') != run_id
            or not isinstance(review.get('evidence_paths'), list) or not review['evidence_paths']):
        raise ValueError('Queue requires a matching accepted ROUND_REVIEW and STATE')
    kind = 'ROUTE_REVIEW' if reviewed else 'RESEARCH_ROUND'
    if not any(e.get('type') == kind and e.get('run_id') == run_id for e in ledger.get('events', [])):
        raise ValueError('Run has no committed acceptance event')
    if not reviewed and run_id not in epoch.get('counted_run_ids', []): raise ValueError('Run was not charged by the route controller')
    return state, supervision._hash(review_path.read_bytes())


def _identity(project, epoch, run_id):
    focus = epoch['focus']
    return {'project_id': configuration.project_id(project), 'route_epoch': epoch['epoch'],
            'trigger_run_id': run_id, 'focus': {'goal_sha256': focus['binding']['goal_sha256'],
                'anchor_id': focus['anchor_id'], 'selected_idea': copy.deepcopy(focus['binding'].get('selected_idea'))}}


def record_postaccept(controller, project, ledger, epoch, run_id, *, reviewed=False,
                      review_required=False, accepted=True, dry_run=False, route_lock_held=False,
                      effective_route_policy=None):
    if dry_run or not accepted: return {'status': 'ignored', 'proceed': True}
    if not enabled(controller, project): return {'status': 'disabled', 'proceed': True}
    with _locks(controller, project, route_lock_held=route_lock_held):
        state, receipt_sha = _receipt(controller, project, ledger, epoch, run_id, reviewed)
        from route_budget import needs_review, policy_for
        policy = effective_route_policy if effective_route_policy is not None else policy_for(Path(controller), Path(project))[0]
        review_required = bool(review_required or needs_review(epoch, policy))
        count = epoch.get('effective_rounds')
        if type(count) is not int or count < 0: raise ValueError('Invalid authoritative effective round count')
        periodic = bool(count and count % load_defaults(controller)['periodic_accepted_rounds'] == 0)
        if not reviewed and not periodic and not review_required: return {'status': 'not_due', 'proceed': True}
        if not reviewed and review_required:
            reasons = (['PERIODIC'] if periodic else []) + ['ROUTE_REVIEW']
            key = queue.defer(controller, project, _identity(project, epoch, run_id),
                {'trigger_reasons': reasons, 'effective_rounds': count, 'round_review_sha256': receipt_sha})
            return {'status': 'deferred', 'proceed': True, 'deferred_id': key}
        deferred = [d for d in queue.deferrals(controller, project) if d['status'] == 'DEFERRED_TO_ROUTE_REVIEW']
        if reviewed:
            # ROUTE_REVIEW alone is also emitted for invalid/halted verdicts.
            verdict = configuration.load_json(supervision._safe(project, 'research/ROUTE_VERDICT.json'), {})
            history = [e for e in ledger.get('events', []) if e.get('run_id') == run_id]
            if (any(e.get('type') in {'ROUTE_REVIEW_INVALID', 'NATIVE_REVIEW_HALT'} for e in history)
                    or verdict.get('run_id') != run_id or not any(e.get('type') == 'ROUTE_VERDICT_RECORDED'
                        and e.get('outcome') == verdict.get('outcome') for e in history)):
                return {'status': 'deferred', 'proceed': True, 'reason': 'VALID_ROUTE_VERDICT_REQUIRED'}
            from research_focus import binding
            matching = [d for d in deferred if d['identity']['route_epoch'] == epoch['epoch']]
            expected_focus = _identity(project, epoch, run_id)['focus']
            if (epoch['focus']['binding'] != binding(project, state)
                    or any(d['identity']['focus'] != expected_focus for d in matching)):
                for item in matching:
                    queue.append(controller, project, 'DEFERRAL_CONFLICT', item['id'],
                                 review_run_id=run_id, reason='ROUTE_GOAL_OR_IDEA_BINDING_CHANGED')
                return {'status': 'conflict', 'proceed': True, 'reason': 'Route/goal binding changed; old triggers preserved'}
            if not epoch.get('counted_run_ids'): return {'status': 'not_due', 'proceed': True}
            origins = {d['identity']['trigger_run_id'] for d in matching}
            ordered = [rid for rid in epoch['counted_run_ids'] if rid in origins]
            if len(ordered) != len(origins): raise ValueError('Deferred trigger has no authoritative counted run')
            trigger_run = ordered[-1] if ordered else epoch['counted_run_ids'][-1]
            trigger_type = 'POST_ROUTE_REVIEW'
            reasons = sorted({'ROUTE_REVIEW'} | {r for item in matching for r in item['context']['trigger_reasons']})
        else:
            matching, trigger_run, trigger_type, reasons = [], run_id, 'PERIODIC', ['PERIODIC']
        snapshot = build_snapshot(project)
        event = make_event(snapshot, trigger_type, run_id=trigger_run)
        event_id = queue.enqueue(controller, project, event, snapshot,
            {'review_run_id': run_id if reviewed else None, 'trigger_reasons': reasons,
             'effective_rounds': count, 'round_review_sha256': receipt_sha,
             'origin_run_ids': [d['identity']['trigger_run_id'] for d in matching] or [trigger_run]})
        for item in matching:
            queue.append(controller, project, 'DEFERRAL_RESOLVED', item['id'], resolved_event_id=event_id, review_run_id=run_id)
        return {'status': 'queued', 'proceed': True, 'event_id': event_id}


def before_run(controller, project, ledger, epoch, *, review_required=False, route_lock_held=False,
               effective_route_policy=None):
    """Recover an accepted boundary before another call; never execute a model."""
    if not enabled(controller, project): return {'status': 'disabled', 'proceed': True}
    guard = restrictions(controller, project)
    if not guard['claim_allowed']: return {'status': 'blocked', 'proceed': False, **guard}
    state = configuration.load_json(supervision._safe(project, 'research/STATE.json'), {})
    rid = state.get('last_run')
    if rid:
        latest = next((e for e in reversed(ledger.get('events', [])) if e.get('run_id') == rid
                       and e.get('type') in {'RESEARCH_ROUND', 'ROUTE_REVIEW'}), None)
        if latest:
            record_postaccept(controller, project, ledger, epoch, rid,
                reviewed=latest['type'] == 'ROUTE_REVIEW', review_required=review_required,
                route_lock_held=route_lock_held, effective_route_policy=effective_route_policy)
    return {'status': 'queue_only', 'proceed': True}


def _event_guard(controller, project, record):
    guard = restrictions(controller, project)
    route = configuration.load_json(_path(controller, 'state/routes/' + configuration.project_id(project) + '.json'), {})
    epoch = route.get('epochs', [])[-1] if route.get('epochs') else None
    state = configuration.load_json(supervision._safe(project, 'research/STATE.json'), {})
    from research_focus import binding
    if (epoch is None or epoch.get('epoch') != record['event']['route_epoch']
            or (epoch.get('focus') or {}).get('anchor_id') != record['event']['focus']['anchor_id']
            or binding(project, state) != record['snapshot']['focus']['binding']):
        guard['restrictions'].append('STALE_ROUTE_OR_GOAL_BINDING'); guard['claim_allowed'] = False
    else:
        from route_budget import needs_review, policy_for
        if needs_review(epoch, policy_for(Path(controller), Path(project))[0]):
            guard['restrictions'].append('ROUTE_REVIEW_PENDING'); guard['claim_allowed'] = False
    return guard


def record_manual(controller, project, *, route_lock_held=False):
    if not enabled(controller, project): return {'status': 'disabled', 'proceed': True}
    with _locks(controller, project, route_lock_held=route_lock_held):
        guard = restrictions(controller, project)
        if not guard['claim_allowed']: return {'status': 'blocked', 'proceed': False, **guard}
        snapshot = build_snapshot(project)
        from route_budget import needs_review, policy_for
        route = configuration.load_json(_path(controller, 'state/routes/' + configuration.project_id(project) + '.json'))
        epoch = route['epochs'][-1]
        if needs_review(epoch, policy_for(Path(controller), Path(project))[0]):
            runs = epoch.get('counted_run_ids', [])
            if not runs: return {'status': 'blocked', 'proceed': False, 'reason': 'NO_ACCEPTED_SCIENTIFIC_RUN'}
            identity = {**_identity(project, epoch, runs[-1]), 'request_kind': 'MANUAL'}
            key = queue.defer(controller, project, identity,
                {'trigger_reasons': ['MANUAL', 'ROUTE_REVIEW'], 'effective_rounds': epoch['effective_rounds']})
            return {'status': 'deferred', 'proceed': True, 'deferred_id': key, 'reason': 'ROUTE_REVIEW_PENDING'}
        event = make_event(snapshot, 'MANUAL')
        event_id = queue.enqueue(controller, project, event, snapshot,
            {'review_run_id': None, 'trigger_reasons': ['MANUAL'], 'origin_run_ids': [event['trigger_run_id']]})
        return {'status': 'queued', 'proceed': True, 'event_id': event_id}


def claim_event(controller, project, event_id):
    if not enabled(controller, project): return {'claimed': False, 'reason': 'DISABLED'}
    try:
        with _locks(controller, project, execution=True):
            record = queue.read_event(controller, project, event_id)
            queue.view(controller, project)  # Validate costs/journal before any reservation.
            guard = _event_guard(controller, project, record)
            if not guard['claim_allowed']:
                queue.append(controller, project, 'CLAIM_BLOCKED', event_id, restrictions=guard['restrictions'])
                return {'claimed': False, 'reason': 'RESTRICTED', **guard}
            data, reserved = queue.reservations(controller, project)
            if event_id in reserved:
                _ack_reservation(controller, project, reserved[event_id])
                return {'claimed': False, 'reason': 'ALREADY_RESERVED', 'state': reserved[event_id]['state']}
            policy = supervision.policy_for(controller, project)
            if data is None: data = supervision._enroll(controller, project)
            remaining = int(policy['max_total_seconds'] - data['seconds_used'])
            if data['attempts_used'] >= policy['max_reviews'] or remaining < 1:
                return {'claimed': False, 'reason': 'BUDGET_EXHAUSTED'}
            token, seconds = secrets.token_hex(32), min(policy['max_seconds'], remaining)
            reservation = {'event_id': event_id, 'state': 'RUNNING', 'claim_token': token,
                'reserved_seconds': seconds, 'started_utc': stamp(), 'call_count': 1}
            data.setdefault('event_reservations', {})[event_id] = reservation
            data['attempts_used'] += 1; data['seconds_used'] += seconds
            data['events'].append({'type': 'CALL_RESERVED', 'event_id': event_id, 'at': stamp(), 'reserved_seconds': seconds})
            supervision._save(controller, project, data)  # First cost, then acknowledgement.
            queue.append(controller, project, 'CALL_RESERVED', event_id, reserved_seconds=seconds)
            return {'claimed': True, 'event_id': event_id, 'claim_token': token, 'max_seconds': seconds, **guard}
    except RuntimeError as exc:
        if not str(exc).startswith('Another route controller instance is running:'): raise
        # A losing claimant must not seize the winner's queue lock just to
        # log contention. Store a separate immutable diagnostic instead.
        queue._event_path(controller, project, event_id)
        try:
            configuration.atomic_json(_path(queue.home(controller, project),
                'lock-conflicts/' + event_id + '-' + secrets.token_hex(8) + '.json'),
                {'event_id': event_id, 'operation': 'LOCK_CONFLICT', 'reason': str(exc), 'at': stamp()})
        except OSError: pass
        return {'claimed': False, 'reason': 'LOCKED', 'recovery_required': True}


def _ack_reservation(controller, project, reservation):
    event_id = reservation['event_id']
    log = queue.operations(controller, project)
    if not any(op['id'] == event_id and op['type'] == 'CALL_RESERVED' for op in log):
        queue.append(controller, project, 'CALL_RESERVED', event_id, reserved_seconds=reservation['reserved_seconds'])
    if reservation['state'] != 'RUNNING' and not any(op['id'] == event_id and op['type'] == 'CLAIM_FINISHED' for op in log):
        queue.append(controller, project, 'CLAIM_FINISHED', event_id,
            state=reservation['state'], elapsed_seconds=reservation['elapsed_seconds'])


def finish_claim(controller, project, event_id, claim_token, *, state, elapsed_seconds):
    if state not in {'PROPOSED', 'FAILED', 'REJECTED', 'CONFLICT'}: raise ValueError('R02 cannot apply guidance')
    if type(elapsed_seconds) not in {float, int} or not math.isfinite(elapsed_seconds) or elapsed_seconds < 0:
        raise ValueError('Invalid supervision elapsed seconds')
    with _locks(controller, project, execution=True):
        queue.view(controller, project)
        data, reservations = queue.reservations(controller, project)
        reservation = reservations.get(event_id)
        if reservation is None or reservation['claim_token'] != claim_token: raise ValueError('No matching event claim token')
        if reservation['state'] != 'RUNNING':
            if reservation['state'] != state: raise ValueError('Claim already completed with another outcome')
            if reservation['elapsed_seconds'] != elapsed_seconds: raise ValueError('Completed cost receipt differs')
            _ack_reservation(controller, project, reservation)
            return {'state': state, 'event_id': event_id}
        _ack_reservation(controller, project, reservation)
        data['seconds_used'] += elapsed_seconds - reservation['reserved_seconds']
        data['event_reservations'][event_id].update(state=state, elapsed_seconds=elapsed_seconds, finished_utc=stamp())
        data['events'].append({'type': 'EVENT_CALL_FINISHED', 'event_id': event_id, 'state': state, 'at': stamp()})
        supervision._save(controller, project, data)
        queue.append(controller, project, 'CLAIM_FINISHED', event_id, state=state, elapsed_seconds=elapsed_seconds)
        return {'state': state, 'event_id': event_id}
