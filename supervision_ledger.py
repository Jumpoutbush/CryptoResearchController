"""R02 immutable review inputs and an atomic append-only operation journal.

Call costs stay in the original supervision ledger. The queue contains no
research counter and never edits route/discovery ledgers or scientific files.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import re

import configuration
import supervision
from supervision_contracts import canonical_hash, validate_event, _snapshot_check
from supervision_snapshot import _path
from route_budget import stamp

HEX = re.compile(r'^[0-9a-f]{64}$')
OPS = {'EVENT_QUEUED', 'EVENT_RECOVERED', 'DEFERRED_TO_ROUTE_REVIEW', 'DEFERRAL_RESOLVED',
       'DEFERRAL_CONFLICT', 'CALL_RESERVED', 'CLAIM_FINISHED', 'CLAIM_BLOCKED', 'LOCK_CONFLICT',
       'RESERVATION_INTENT', 'CALL_DISPATCHED', 'CALL_COMPLETED', 'BLOCKED_MISSING_FROZEN_INPUT'}


def home(controller, project):
    _path(project, 'PROJECT.json')
    key = configuration.project_id(project)
    if Path(project).resolve() != Path(controller).resolve() / 'projects' / key:
        raise ValueError('Queue project must match its registered controller path')
    return _path(Path(controller), 'state/supervision/' + key + '/event_queue')


def _event_path(controller, project, event_id, directory='events'):
    if not isinstance(event_id, str) or not HEX.fullmatch(event_id): raise ValueError('Invalid queue event ID')
    return _path(home(controller, project), directory + '/' + event_id + '.json')


def operations(controller, project):
    path = _path(home(controller, project), 'events.jsonl')
    if not path.exists(): return []
    raw = path.read_text(encoding='utf8')
    if raw and not raw.endswith('\n'): raise ValueError('Incomplete supervision operation journal; preserve for recovery')
    result, previous = [], None
    for index, line in enumerate(raw.splitlines(), 1):
        try: item = json.loads(line)
        except ValueError as exc: raise ValueError('Corrupt supervision operation journal') from exc
        if (not isinstance(item, dict) or type(item.get('schema_version')) is not int or item['schema_version'] != 1
                or type(item.get('seq')) is not int or item['seq'] != index
                or item.get('previous_sha256') != previous or item.get('type') not in OPS
                or not isinstance(item.get('id'), str) or not HEX.fullmatch(item['id'])
                or item.get('sha256') != canonical_hash({k: v for k, v in item.items() if k != 'sha256'})):
            raise ValueError('Invalid supervision journal identity or hash chain')
        result.append(item); previous = item['sha256']
    return result


def append(controller, project, kind, event_id, **details):
    """Caller holds the queue lock. Atomic replacement retains the full prefix."""
    if kind not in OPS or not HEX.fullmatch(event_id): raise ValueError('Invalid queue operation')
    log = operations(controller, project)
    item = {'schema_version': 1, 'seq': len(log) + 1, 'previous_sha256': log[-1]['sha256'] if log else None,
            'type': kind, 'id': event_id, 'at': stamp(), 'details': details}
    item['sha256'] = canonical_hash(item)
    path = _path(home(controller, project), 'events.jsonl')
    raw = path.read_bytes() if path.exists() else b''
    line = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf8') + b'\n'
    supervision._write(path, raw + line)
    return item


def _write_immutable(path, payload):
    wrapped = {**payload, 'payload_sha256': canonical_hash(payload)}
    if path.exists():
        old = configuration.load_json(path)
        if old.get('payload_sha256') != canonical_hash({k: v for k, v in old.items() if k != 'payload_sha256'}):
            raise ValueError('Corrupt immutable supervision input')
        return old
    configuration.atomic_json(path, wrapped)
    return wrapped


def read_event(controller, project, event_id):
    path = _event_path(controller, project, event_id)
    data = configuration.load_json(path)
    if (not isinstance(data, dict) or set(data) != {'schema_version', 'event', 'snapshot', 'context', 'payload_sha256'}
            or type(data['schema_version']) is not int or data['schema_version'] != 1
            or data['payload_sha256'] != canonical_hash({k: v for k, v in data.items() if k != 'payload_sha256'})):
        raise ValueError('Invalid immutable supervision event')
    _snapshot_check(data['snapshot']); validate_event(data['event'], data['snapshot'])
    if (data['event']['event_id'] != event_id or data['event']['state'] != 'QUEUED'
            or data['event']['project_id'] != configuration.project_id(project)):
        raise ValueError('Queue event belongs to a different trigger or project')
    return data


def enqueue(controller, project, event, snapshot, context):
    event_id = event['event_id']
    _snapshot_check(snapshot); validate_event(event, snapshot)
    # An acknowledged input is never rebuilt from newer scientific sources.
    log = operations(controller, project)
    acknowledged = [op for op in log if op['id'] == event_id and op['type'] in {'EVENT_QUEUED', 'EVENT_RECOVERED'}]
    if acknowledged: read_for_claim(controller, project, event_id)
    _write_immutable(_event_path(controller, project, event_id),
        {'schema_version': 1, 'event': event, 'snapshot': snapshot, 'context': context})
    saved = read_event(controller, project, event_id)
    if any(op['details'].get('payload_sha256') != saved['payload_sha256'] for op in acknowledged):
        raise ValueError('Immutable event input differs from its journal receipt')
    if not any(op['id'] == event_id and op['type'] in {'EVENT_QUEUED', 'EVENT_RECOVERED'} for op in log):
        append(controller, project, 'EVENT_QUEUED', event_id, payload_sha256=saved['payload_sha256'])
    return event_id


def defer(controller, project, identity, context):
    key = canonical_hash(identity)
    deferrals(controller, project)  # Validate acknowledged inputs before recovering an orphan.
    data = _write_immutable(_event_path(controller, project, key, 'deferrals'),
        {'schema_version': 1, 'identity': identity, 'context': context})
    if not any(op['id'] == key and op['type'] == 'DEFERRED_TO_ROUTE_REVIEW' for op in operations(controller, project)):
        append(controller, project, 'DEFERRED_TO_ROUTE_REVIEW', key, identity=data['identity'], payload_sha256=data['payload_sha256'])
    return key


def deferrals(controller, project):
    path = _path(home(controller, project), 'deferrals')
    log = operations(controller, project)
    result = []
    for item in log:
        if item['type'] == 'DEFERRED_TO_ROUTE_REVIEW' and not _event_path(controller, project, item['id'], 'deferrals').exists():
            raise ValueError('Acknowledged deferred supervision input is missing')
    for source in sorted(path.glob('*.json')) if path.exists() else []:
        data = configuration.load_json(_event_path(controller, project, source.stem, 'deferrals'))
        if (not isinstance(data, dict) or data.get('payload_sha256') != canonical_hash({k: v for k, v in data.items() if k != 'payload_sha256'})
                or canonical_hash(data.get('identity')) != source.stem
                or data['identity'].get('project_id') != configuration.project_id(project)):
            raise ValueError('Corrupt deferred supervision trigger')
        if any(op['details'].get('payload_sha256') != data['payload_sha256'] for op in log
               if op['id'] == source.stem and op['type'] == 'DEFERRED_TO_ROUTE_REVIEW'):
            raise ValueError('Deferred supervision input differs from its journal receipt')
        status = next((op['type'] for op in reversed(log) if op['id'] == source.stem
                       and op['type'] in {'DEFERRAL_RESOLVED', 'DEFERRAL_CONFLICT'}), 'DEFERRED_TO_ROUTE_REVIEW')
        result.append({'id': source.stem, 'status': status, **data})
    return result


def reservations(controller, project):
    data = supervision._load(controller, project)
    result = data.get('event_reservations', {}) if data else {}
    if not isinstance(result, dict): raise ValueError('Invalid shared supervision reservation ledger')
    # This is a write-ahead witness, not another balance. Missing cost evidence
    # must never be interpreted as a fresh zero-cost enrollment.
    for op in operations(controller, project):
        if op['type'] == 'RESERVATION_INTENT' and op['id'] in result:
            initial = op['details']['reservation']
            if any(result[op['id']].get(k) != v for k, v in initial.items() if k != 'state'):
                raise ValueError('Reservation identity or frozen model route differs from its intent')
        if op['type'] == 'RESERVATION_INTENT' and op['id'] not in result:
            if data is None or canonical_hash(data) != op['details']['baseline_sha256']:
                raise ValueError('Missing or ambiguous shared cost ledger; restore the original ledger before recovery')
        if op['type'] == 'CALL_DISPATCHED':
            dispatch = result.get(op['id'], {}).get('dispatch')
            if dispatch is None or canonical_hash(dispatch) != op['details'].get('dispatch_sha256'):
                raise ValueError('Dispatch witness conflicts with the shared ledger; automatic redispatch is forbidden')
    for key, record in result.items():
        if (not HEX.fullmatch(key) or not isinstance(record, dict) or record.get('event_id') != key
                or record.get('state') not in {'RUNNING', 'PROPOSED', 'FAILED', 'REJECTED', 'CONFLICT'}
                or not isinstance(record.get('claim_token'), str) or not HEX.fullmatch(record['claim_token'])
                or type(record.get('call_count')) is not int or record['call_count'] != 1
                or type(record.get('reserved_seconds')) is not int or record['reserved_seconds'] < 1):
            raise ValueError('Invalid persistent event call reservation')
        if record['state'] != 'RUNNING' and (type(record.get('elapsed_seconds')) not in {int, float}
                or not math.isfinite(record['elapsed_seconds']) or record['elapsed_seconds'] < 0):
            raise ValueError('Invalid completed call cost receipt')
    if data:
        for item in data['events']:
            if item.get('type') == 'CALL_RESERVED' and item.get('event_id') not in result:
                raise ValueError('Call reservation disappeared from the shared budget receipt')
        total = sum(r['reserved_seconds'] if r['state'] == 'RUNNING' else r['elapsed_seconds'] for r in result.values())
        if (data['attempts_used'] < len(result) or type(data['seconds_used']) not in {int, float}
                or not math.isfinite(data['seconds_used']) or data['seconds_used'] + 1e-6 < total):
            raise ValueError('Shared supervision costs conflict with event reservations')
    return data, result


def read_for_claim(controller, project, event_id):
    """Mutating caller holds queue lock; queries still use read_event only."""
    required = {'GOAL.md', 'PROJECT.json', 'research/STATE.json'}
    try:
        record = read_event(controller, project, event_id)
        if record['event']['focus']['selected_idea'] is not None:
            required |= {s['path'] for s in record['snapshot']['source_manifest'] if s['path'].startswith('ideas/')}
        for relative in sorted(required):
            source = next((s for s in record['snapshot']['source_manifest']
                           if s['scope'] == 'PROJECT' and s['path'] == relative), None)
            if source is None or source['truncated'] or not source['captured_bytes']:
                raise ValueError('Required frozen source is unavailable: ' + relative)
        return record
    except (ValueError, OSError) as exc:
        prior = next((op for op in operations(controller, project) if op['id'] == event_id
                      and op['type'] in {'EVENT_QUEUED', 'EVENT_RECOVERED'}), None)
        diagnostic = {'path': 'event_queue/events/' + event_id + '.json',
            'expected_sha256': prior['details'].get('payload_sha256') if prior else None,
            'hash_scope': 'immutable_payload', 'reason': type(exc).__name__}
        try:
            raw = configuration.load_json(_event_path(controller, project, event_id))
            snapshot = raw['snapshot']
            if raw['event']['focus']['selected_idea'] is not None:
                required |= {s['path'] for s in snapshot['source_manifest'] if s['scope'] == 'PROJECT' and s['path'].startswith('ideas/')}
            for source in snapshot['source_manifest']:
                if source['scope'] != 'PROJECT' or source['path'] not in required: continue
                body = next((b for b in snapshot['sources'] if b['scope'] == 'PROJECT' and b['path'] == source['path']), None)
                if (source['truncated'] or body is None
                        or supervision._hash(body['content'].encode('utf8')) != source['sha256']):
                    diagnostic.update(path=source['path'], expected_sha256=source['sha256'], hash_scope='frozen_source')
                    break
        except (ValueError, OSError, KeyError, TypeError): pass  # Never rebuild or read live project evidence.
        append(controller, project, 'BLOCKED_MISSING_FROZEN_INPUT', event_id, **diagnostic)
        raise


def view(controller, project):
    log = operations(controller, project)
    data, reserved = reservations(controller, project)
    for item in log:
        if item['type'] == 'CALL_RESERVED' and item['id'] not in reserved:
            raise ValueError('Call reservation disappeared from the shared budget ledger')
        if item['type'] in {'EVENT_QUEUED', 'EVENT_RECOVERED'}:
            if not _event_path(controller, project, item['id']).exists():
                raise ValueError('Acknowledged immutable event input is missing')
            if read_event(controller, project, item['id'])['payload_sha256'] != item['details'].get('payload_sha256'):
                raise ValueError('Immutable event input differs from its journal receipt')
    folder = _path(home(controller, project), 'events')
    result = []
    for path in sorted(folder.glob('*.json')) if folder.exists() else []:
        record = read_event(controller, project, path.stem)
        saved = reserved.get(path.stem)
        acknowledged = any(op['id'] == path.stem and op['type'] in {'EVENT_QUEUED', 'EVENT_RECOVERED'} for op in log)
        state = saved['state'] if saved else 'QUEUED'
        result.append({**copy.deepcopy(record['event']), 'state': state,
            'recovery_required': not acknowledged or bool(saved and not any(
                op['id'] == path.stem and op['type'] == 'CALL_RESERVED' for op in log)) or bool(
                saved and saved['state'] != 'RUNNING' and not any(
                    op['id'] == path.stem and op['type'] == 'CLAIM_FINISHED' for op in log)),
            'context': copy.deepcopy(record['context'])})
        from supervision_calls import recovery_info
        result[-1].update(recovery_info(controller, project, path.stem, saved))
        result[-1]['recovery_required'] |= bool(result[-1].get('completion_replay_required') or result[-1].get('operator_audit_required'))
    for key in reserved:
        if not any(item['event_id'] == key for item in result):
            raise ValueError('Reserved event input is missing; refusing to recreate a free call')
    return {'events': result, 'deferred': deferrals(controller, project),
            'attempts_used': data['attempts_used'] if data else 0,
            'seconds_used': data['seconds_used'] if data else 0}
