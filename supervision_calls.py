"""R02 local call recovery fences. No executor, subprocess, or provider API.

Costs remain solely in the existing supervision ledger. R01 event/snapshot
contracts are unchanged. A dispatch fence grants permission once, before I/O;
an interrupted caller must treat the remote outcome as unknown, never retry.
"""
from __future__ import annotations

import math
import os

import configuration
import supervision
import supervision_ledger as queue
from supervision_contracts import canonical_hash, load_defaults
from route_budget import stamp


def _completion_path(controller, project, event_id):
    return queue._event_path(controller, project, event_id, 'completions')


def _read_completion(controller, project, event_id, reservation):
    path = _completion_path(controller, project, event_id)
    acknowledged = [op for op in queue.operations(controller, project)
                    if op['id'] == event_id and op['type'] == 'CALL_COMPLETED']
    if not path.exists():
        if acknowledged: raise ValueError('Acknowledged completion receipt is missing; do not redispatch')
        return None
    if path.stat().st_size > load_defaults(controller)['max_snapshot_bytes']:
        raise ValueError('Completion receipt exceeds its byte bound')
    data = configuration.load_json(path)
    fields = {'schema_version', 'event_id', 'claim_token_sha256', 'event_payload_sha256',
              'input_snapshot_sha256', 'dispatch_sha256', 'state', 'elapsed_seconds',
              'raw_output', 'log', 'trust', 'payload_sha256'}
    if (not isinstance(data, dict) or set(data) != fields
            or type(data['schema_version']) is not int or data['schema_version'] != 1
            or data['trust'] != 'UNVERIFIED_EXTERNAL_OUTPUT'
            or not isinstance(data['raw_output'], str) or not isinstance(data['log'], str)
            or data['state'] not in {'PROPOSED', 'FAILED', 'REJECTED', 'CONFLICT'}
            or type(data['elapsed_seconds']) not in {float, int}
            or not math.isfinite(data['elapsed_seconds']) or data['elapsed_seconds'] < 0):
        raise ValueError('Invalid bounded, untrusted completion receipt')
    payload = {k: v for k, v in data.items() if k != 'payload_sha256'}
    if (data.get('payload_sha256') != canonical_hash(payload)
            or data.get('event_id') != event_id
            or data.get('claim_token_sha256') != canonical_hash(reservation['claim_token'])
            or data.get('input_snapshot_sha256') != reservation.get('input_snapshot_sha256')
            or data.get('event_payload_sha256') != reservation.get('event_payload_sha256')
            or data.get('dispatch_sha256') != canonical_hash(reservation.get('dispatch'))
            or any(op['details'].get('payload_sha256') != data['payload_sha256'] for op in acknowledged)):
        raise ValueError('Invalid completion receipt; preserve for operator audit')
    return data


def recovery_info(controller, project, event_id, reservation):
    if not reservation: return {'call_phase': 'QUEUED', 'operator_audit_required': False}
    receipt = _read_completion(controller, project, event_id, reservation)
    if receipt:
        return {'call_phase': 'CALL_COMPLETED', 'operator_audit_required': False,
                'completion_replay_required': reservation['state'] == 'RUNNING', 'automatic_retry_allowed': False}
    if reservation.get('dispatch'):
        return {'call_phase': 'UNKNOWN_EXTERNAL_OUTCOME', 'operator_audit_required': True,
                'automatic_retry_allowed': False}
    phase = ('RESERVED_NOT_DISPATCHED' if reservation.get('call_generation') == 1 else 'LEGACY_DISPATCH_UNRECORDED')
    if reservation['state'] != 'RUNNING': phase = 'LOCAL_COMPLETED'
    return {'call_phase': phase, 'operator_audit_required': phase == 'LEGACY_DISPATCH_UNRECORDED',
            'automatic_retry_allowed': False}


def _bound(controller, project, event_id, token):
    record = queue.read_for_claim(controller, project, event_id)
    data, reservations = queue.reservations(controller, project)
    saved = reservations.get(event_id)
    if not saved or saved['claim_token'] != token: raise ValueError('No matching event claim token')
    if (saved.get('call_generation') != 1 or saved.get('event_payload_sha256') != record['payload_sha256']
            or saved.get('input_snapshot_sha256') != record['snapshot']['input_snapshot_sha256']):
        raise ValueError('Unbound or legacy reservation requires operator audit')
    return record, data, saved


def mark_dispatched(controller, project, event_id, claim_token, *, argv):
    """Write-ahead fence only. The caller, never this function, performs I/O.

    argv is frozen by exact canonical digest; raw arguments (possibly secrets)
    are deliberately not logged. Model/effort are pinned at reservation time.
    """
    from supervision_scheduler import _locks, _event_guard, enabled
    if not isinstance(argv, list) or not argv or len(argv) > 100 or any(
            not isinstance(arg, str) or len(arg) > 4096 or '\x00' in arg for arg in argv):
        raise ValueError('Invalid invocation argument vector')
    with _locks(controller, project, execution=True):
        if not enabled(controller, project): return {'dispatch_allowed': False, 'reason': 'DISABLED'}
        queue.view(controller, project)
        record, data, saved = _bound(controller, project, event_id, claim_token)
        phase = recovery_info(controller, project, event_id, saved)['call_phase']
        if saved.get('dispatch') or saved['state'] != 'RUNNING':
            return {'dispatch_allowed': False, 'reason': phase}
        guard = _event_guard(controller, project, record)
        if not guard['claim_allowed']: return {'dispatch_allowed': False, 'reason': 'RESTRICTED', **guard}
        saved['dispatch'] = {'at': stamp(), 'owner_pid': os.getpid(), 'argv_sha256': canonical_hash(argv),
                             'argv_count': len(argv), 'model_route': saved['model_route']}
        supervision._save(controller, project, data)  # Fence precedes any permission to invoke.
        queue.append(controller, project, 'CALL_DISPATCHED', event_id, dispatch_sha256=canonical_hash(saved['dispatch']))
        return {'dispatch_allowed': True, 'event_id': event_id, 'model_route': saved['model_route']}


def save_completion(controller, project, event_id, claim_token, *, state, elapsed_seconds, raw_output, log,
                    acceptance_guard=None):
    """Persist bounded, untrusted result bytes before settling local costs."""
    from supervision_scheduler import _locks
    if state not in {'PROPOSED', 'FAILED', 'REJECTED', 'CONFLICT'}:
        raise ValueError('R02 completion cannot apply a guide or approve a theorem')
    if type(elapsed_seconds) not in {int, float} or not math.isfinite(elapsed_seconds) or elapsed_seconds < 0:
        raise ValueError('Invalid completion elapsed seconds')
    if not isinstance(raw_output, str) or not isinstance(log, str): raise ValueError('Completion bytes must be UTF-8 text')
    with _locks(controller, project, execution=True):
        queue.view(controller, project)
        _, _, saved = _bound(controller, project, event_id, claim_token)
        if not saved.get('dispatch'): raise ValueError('No durable dispatch fence')
        # R03 advisory acceptance is checked under the same original locks as
        # the durable receipt. Existing R02 callers keep identical semantics.
        if state == 'PROPOSED' and acceptance_guard is not None and not acceptance_guard():
            state = 'CONFLICT'
        payload = {'schema_version': 1, 'event_id': event_id, 'claim_token_sha256': canonical_hash(claim_token),
            'event_payload_sha256': saved['event_payload_sha256'], 'input_snapshot_sha256': saved['input_snapshot_sha256'],
            'dispatch_sha256': canonical_hash(saved['dispatch']), 'state': state, 'elapsed_seconds': elapsed_seconds,
            'raw_output': raw_output, 'log': log, 'trust': 'UNVERIFIED_EXTERNAL_OUTPUT'}
        if len(supervision._json_bytes({**payload, 'payload_sha256': canonical_hash(payload)})) > load_defaults(controller)['max_snapshot_bytes']:
            raise ValueError('Completion exceeds bounded local receipt size')
        existing = _read_completion(controller, project, event_id, saved)
        if existing and canonical_hash(payload) != existing['payload_sha256']:
            raise ValueError('A different completion already exists; do not replace it')
        queue._write_immutable(_completion_path(controller, project, event_id), payload)
    return recover_completion(controller, project, event_id, claim_token)


def recover_completion(controller, project, event_id, claim_token):
    """Replay an original receipt, never invoke a provider or create a new call."""
    from supervision_scheduler import _locks, finish_claim
    with _locks(controller, project, execution=True):
        queue.view(controller, project)
        _, _, saved = _bound(controller, project, event_id, claim_token)
        receipt = _read_completion(controller, project, event_id, saved)
        if receipt is None: raise ValueError('UNKNOWN_EXTERNAL_OUTCOME: operator audit required; automatic retry is forbidden')
        if not any(op['id'] == event_id and op['type'] == 'CALL_COMPLETED' for op in queue.operations(controller, project)):
            queue.append(controller, project, 'CALL_COMPLETED', event_id, payload_sha256=receipt['payload_sha256'])
    # finish_claim owns the same locks; do not nest a non-reentrant OS lock.
    return finish_claim(controller, project, event_id, claim_token,
                        state=receipt['state'], elapsed_seconds=receipt['elapsed_seconds'])
