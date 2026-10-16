"""R01 wire contracts. Pure validation; no scheduling, model calls or writes.

These contracts are staged alongside the existing supervision protocol. Runtime
integration belongs to later roadmap rounds, so old policies remain untouched.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import configuration

STATES = {'QUEUED', 'RUNNING', 'PROPOSED', 'APPLIED', 'FAILED', 'REJECTED', 'CONFLICT'}
TRIGGERS = {'PERIODIC', 'POST_ROUTE_REVIEW', 'MANUAL'}
TRUST = {'USER_FROZEN', 'INDEPENDENTLY_REVIEWED', 'TOOL_CHECKED_AUDIT_PENDING',
         'MODEL_CANDIDATE', 'UNVERIFIED'}
ACTIONS = {'KEEP_GUIDE', 'REFOCUS_RECOMMENDED', 'PAUSE_RECOMMENDED', 'ESCALATE'}
TRANSITIONS = {'QUEUED': {'RUNNING', 'FAILED', 'REJECTED', 'CONFLICT'},
               'RUNNING': {'PROPOSED', 'FAILED', 'REJECTED', 'CONFLICT'},
               'PROPOSED': {'APPLIED', 'FAILED', 'REJECTED', 'CONFLICT'}}


def canonical_hash(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(',', ':'), allow_nan=False).encode('utf8')
    return hashlib.sha256(raw).hexdigest()


def _object(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties),
            'additionalProperties': False}


def _string(maximum=12000, **extra):
    return {'type': 'string', 'minLength': 1, 'maxLength': maximum, **extra}


def _sha():
    return _string(64, pattern=r'^[0-9a-f]{64}$')


def _id():
    return _string(64, pattern=r'^[a-z0-9][a-z0-9_-]{0,63}$')


def event_schema():
    idea = _object({'id': _string(80), 'version': {'type': 'integer', 'minimum': 1}})
    focus = _object({'goal_sha256': _sha(), 'anchor_id': _sha(),
                     'selected_idea': {'anyOf': [{'type': 'null'}, idea]}})
    return _object({'schema_version': {'type': 'integer', 'enum': [1]}, 'event_id': _sha(),
        'project_id': _id(), 'route_epoch': {'type': 'integer', 'minimum': 1},
        'trigger_type': {'type': 'string', 'enum': sorted(TRIGGERS)},
        'trigger_run_id': _string(160, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,159}$'),
        'focus': focus, 'source_manifest_sha256': _sha(),
        'state': {'type': 'string', 'enum': sorted(STATES)},
        'review_precedence': {'type': 'string', 'enum': ['ROUTE_REVIEW_PENDING', 'ROUTE_REVIEW_NOT_PENDING']},
        'created_utc': _string(40)})


def proposal_schema():
    citation = _object({'path': _string(1024), 'sha256': _sha(),
                        'scope': {'type': 'string', 'enum': ['CORE', 'DIRECT_DEPENDENCY', 'SUPPORT']}})
    return _object({'schema_version': {'type': 'integer', 'enum': [1]},
        'event_id': _sha(), 'project_id': _id(), 'goal_anchor_id': _sha(),
        'input_snapshot_sha256': _sha(), 'action': {'type': 'string', 'enum': sorted(ACTIONS)},
        'evidence_refs': {'type': 'array', 'minItems': 1, 'maxItems': 50, 'items': citation},
        'reason': _string(), 'next_obligation_id': {'anyOf': [{'type': 'null'}, _string(160)]},
        'next_task': _string(), 'success_criterion': _string(), 'falsification_criterion': _string(),
        'requires_operator_approval': {'type': 'boolean'},
        'guide_notes': {'type': 'array', 'maxItems': 3, 'items': _string(2000)}})


def defaults_schema():
    return _object({'schema_version': {'type': 'integer', 'enum': [1]},
        'enabled': {'type': 'boolean'},
        'periodic_accepted_rounds': {'type': 'integer', 'minimum': 1, 'maximum': 100},
        'calls_per_event': {'type': 'integer', 'enum': [1]},
        'max_snapshot_bytes': {'type': 'integer', 'minimum': 1024, 'maximum': 262144},
        'max_guide_bytes': {'type': 'integer', 'minimum': 256, 'maximum': 12288},
        'model_tier': {'type': 'string', 'enum': ['critical']}})


def _validate(value, schema, location='$'):
    """Evaluate the small JSON Schema subset emitted by this module."""
    if 'anyOf' in schema:
        for candidate in schema['anyOf']:
            try: _validate(value, candidate, location); return
            except ValueError: pass
        raise ValueError(location + ': no allowed schema matches')
    kind = schema.get('type')
    types = {'object': dict, 'array': list, 'string': str, 'integer': int,
             'boolean': bool, 'null': type(None)}
    if kind in types and type(value) is not types[kind]: raise ValueError(location + ': wrong type')
    if 'enum' in schema and value not in schema['enum']: raise ValueError(location + ': invalid enum')
    if kind == 'object':
        if not set(schema['required']) <= set(value) or set(value) - set(schema['properties']):
            raise ValueError(location + ': missing or unknown fields')
        for key, item in value.items(): _validate(item, schema['properties'][key], location + '.' + key)
    elif kind == 'array':
        if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', 1000):
            raise ValueError(location + ': array size outside bounds')
        for index, item in enumerate(value): _validate(item, schema['items'], location + '[' + str(index) + ']')
    elif kind == 'string':
        if (not value.strip() or '\x00' in value or not schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', 12000)
                or ('pattern' in schema and not re.fullmatch(schema['pattern'], value))):
            raise ValueError(location + ': invalid string')
    elif kind == 'integer':
        if not schema.get('minimum', 0) <= value <= schema.get('maximum', 2**63 - 1):
            raise ValueError(location + ': integer outside bounds')


def validate_defaults(value):
    _validate(value, defaults_schema())
    return copy.deepcopy(value)


def load_defaults(controller=None):
    controller = Path(controller) if controller is not None else configuration.ROOT
    return validate_defaults(configuration.load_json(controller / 'config/supervision_defaults.json'))


def _snapshot_check(snapshot):
    if not isinstance(snapshot, dict): raise ValueError('Missing bound snapshot')
    defaults = validate_defaults(snapshot.get('defaults'))
    manifest = snapshot.get('source_manifest')
    if not isinstance(manifest, list) or len(manifest) > 600: raise ValueError('Invalid source manifest')
    scoped_review = _object({'claim_id': _string(80), 'revision': {'type': 'integer', 'minimum': 1},
        'status': {'type': 'string', 'enum': sorted(TRUST)}, 'scope': _string(1000)})
    item_schema = _object({'scope': {'type': 'string', 'enum': ['PROJECT', 'CONTROLLER']},
        'path': _string(1024), 'size_bytes': {'type': 'integer', 'minimum': 0},
        'sha256': _sha(), 'trust': {'type': 'string', 'enum': sorted(TRUST)},
        'evidence_eligible': {'type': 'boolean'},
        'verification_scopes': {'type': 'array', 'maxItems': 500, 'items': scoped_review},
        'captured_bytes': {'type': 'integer', 'minimum': 0},
        'omitted_bytes': {'type': 'integer', 'minimum': 0}, 'truncated': {'type': 'boolean'},
        'omission_reason': {'anyOf': [{'type': 'null'}, _string(200)]}})
    seen = {}
    for item in manifest:
        _validate(item, item_schema)
        relative = item['path']
        if (relative.startswith('/') or '\\' in relative or ':' in relative
                or any(p in {'', '.', '..'} for p in relative.split('/'))):
            raise ValueError('Unsafe manifest source path')
        key = (item['scope'], relative)
        if key in seen: raise ValueError('Duplicate manifest source')
        seen[key] = item
        if (item['captured_bytes'] + item['omitted_bytes'] != item['size_bytes']
                or item['truncated'] != (item['omitted_bytes'] > 0)
                or (item['truncated'] and not item['omission_reason'])):
            raise ValueError('Manifest byte accounting is inconsistent')
        if item['evidence_eligible'] and (item['scope'] != 'PROJECT'
                or relative.split('/')[0] not in {'proofs', 'research', 'literature', 'experiments', 'reports', 'inputs', 'ideas'}
                or relative.casefold().startswith(('research/discovery/', 'research/supervision/'))
                or Path(relative).name.casefold() in {'state.json', 'round_review.json', 'route_signal.json',
                    'route_verdict.json', 'run_result.json', 'supervision_report.md', 'checkpoint.json', 'theory_readiness.json'}):
            raise ValueError('Control records cannot become scientific snapshot evidence')
        if item['trust'] in {'INDEPENDENTLY_REVIEWED', 'TOOL_CHECKED_AUDIT_PENDING'} and not item['verification_scopes']:
            raise ValueError('Higher trust requires a scoped canonical receipt')
    bodies = snapshot.get('sources')
    if not isinstance(bodies, list): raise ValueError('Invalid snapshot text sources')
    body_seen, text_bytes = set(), 0
    for body in bodies:
        if not isinstance(body, dict) or set(body) != {'scope', 'path', 'content'} or not isinstance(body['content'], str):
            raise ValueError('Invalid snapshot text body')
        key = (body['scope'], body['path']); source = seen.get(key)
        count = len(body['content'].encode('utf8'))
        if key in body_seen or source is None or source['captured_bytes'] != count:
            raise ValueError('Snapshot body differs from source byte accounting')
        if not source['truncated'] and hashlib.sha256(body['content'].encode('utf8')).hexdigest() != source['sha256']:
            raise ValueError('Complete source body hash mismatch')
        body_seen.add(key); text_bytes += count
    if any(s['captured_bytes'] and key not in body_seen for key, s in seen.items()):
        raise ValueError('Missing captured source body')
    goal = seen.get(('PROJECT', 'GOAL.md'))
    if goal is None or goal['truncated'] or not goal['captured_bytes'] or goal['trust'] != 'USER_FROZEN':
        raise ValueError('Snapshot has no complete frozen GOAL')
    if snapshot.get('focus', {}).get('binding', {}).get('goal_sha256') != goal['sha256']:
        raise ValueError('Frozen focus differs from GOAL source')
    limits = snapshot.get('limits', {})
    if (type(limits.get('derived_bytes')) is not int or limits['derived_bytes'] < 0
            or limits.get('text_bytes') != text_bytes + limits['derived_bytes']):
        raise ValueError('Snapshot text budget accounting mismatch')
    size = len(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf8'))
    if size > defaults['max_snapshot_bytes'] or limits.get('serialized_bytes') != size:
        raise ValueError('Serialized snapshot exceeds or differs from its byte bound')
    if snapshot.get('source_manifest_sha256') != canonical_hash(snapshot.get('source_manifest')):
        raise ValueError('Source manifest digest mismatch')
    unsigned = {k: v for k, v in snapshot.items() if k != 'input_snapshot_sha256'}
    if snapshot.get('input_snapshot_sha256') != canonical_hash(unsigned):
        raise ValueError('Input snapshot digest mismatch')


def _event_id(event):
    return canonical_hash({k: event[k] for k in
        ('project_id', 'route_epoch', 'trigger_type', 'trigger_run_id', 'focus')})


def validate_event(event, snapshot=None):
    _validate(event, event_schema())
    try:
        created = datetime.fromisoformat(event['created_utc'].replace('Z', '+00:00'))
        if created.tzinfo is None or created.utcoffset().total_seconds() != 0: raise ValueError('not UTC')
    except (ValueError, AttributeError) as exc: raise ValueError('Event requires a real UTC timestamp') from exc
    if event['event_id'] != _event_id(event): raise ValueError('Event ID does not match stable trigger identity')
    if snapshot is not None:
        _snapshot_check(snapshot)
        route, focus = snapshot['route_summary'], snapshot['focus']
        expected_focus = {'goal_sha256': focus['binding']['goal_sha256'], 'anchor_id': focus['anchor_id'],
                          'selected_idea': focus['binding'].get('selected_idea')}
        if (event['project_id'] != snapshot['project_id'] or event['focus'] != expected_focus
                or event['route_epoch'] != route['route_epoch']
                or event['trigger_run_id'] not in route['accepted_run_ids']
                or event['source_manifest_sha256'] != snapshot['source_manifest_sha256']
                or event['review_precedence'] != ('ROUTE_REVIEW_PENDING' if route['review_pending'] else 'ROUTE_REVIEW_NOT_PENDING')):
            raise ValueError('Event identity or accepted receipt differs from snapshot')
    return copy.deepcopy(event)


def make_event(snapshot, trigger_type, *, run_id=None, created_utc=None):
    _snapshot_check(snapshot)
    route, focus = snapshot['route_summary'], snapshot['focus']
    if not route['present'] or not route['accepted_run_ids']: raise ValueError('No real accepted route receipt')
    event = {'schema_version': 1, 'project_id': snapshot['project_id'],
        'route_epoch': route['route_epoch'], 'trigger_type': trigger_type,
        'trigger_run_id': run_id or route['accepted_run_ids'][-1],
        'focus': {'goal_sha256': focus['binding']['goal_sha256'], 'anchor_id': focus['anchor_id'],
                  'selected_idea': focus['binding'].get('selected_idea')},
        'source_manifest_sha256': snapshot['source_manifest_sha256'], 'state': 'QUEUED',
        'review_precedence': 'ROUTE_REVIEW_PENDING' if route['review_pending'] else 'ROUTE_REVIEW_NOT_PENDING',
        'created_utc': created_utc or datetime.now(timezone.utc).isoformat(timespec='seconds')}
    event['event_id'] = _event_id(event)
    return validate_event(event, snapshot)


def transition_event(event, state):
    result = validate_event(event)
    if state not in TRANSITIONS.get(result['state'], set()): raise ValueError('Illegal supervision event transition')
    result['state'] = state
    return result


def validate_proposal(proposal, event, snapshot):
    validate_event(event, snapshot)
    _validate(proposal, proposal_schema())
    if (proposal['event_id'] != event['event_id'] or proposal['project_id'] != event['project_id']
            or proposal['goal_anchor_id'] != event['focus']['anchor_id']
            or proposal['input_snapshot_sha256'] != snapshot['input_snapshot_sha256']):
        raise ValueError('Proposal differs from the bound event and snapshot')
    known = set(snapshot['obligation_ids'])
    if proposal['next_obligation_id'] not in known | {None}:
        raise ValueError('Proposal names an unknown frozen obligation')
    if proposal['action'] == 'REFOCUS_RECOMMENDED' and proposal['next_obligation_id'] is None:
        raise ValueError('Refocus must name a real frozen obligation')
    evidence = {s['path']: s for s in snapshot['source_manifest'] if s['scope'] == 'PROJECT' and s['evidence_eligible']}
    seen = set()
    for ref in proposal['evidence_refs']:
        source = evidence.get(ref['path'])
        if (source is None or source['sha256'] != ref['sha256'] or source['truncated']
                or not source['captured_bytes'] or ref['path'] in seen):
            raise ValueError('Proposal must cite distinct, complete snapshot evidence with exact hashes')
        seen.add(ref['path'])
    guide = {k: proposal[k] for k in ('next_task', 'success_criterion', 'falsification_criterion', 'guide_notes')}
    if len(json.dumps(guide, ensure_ascii=False).encode('utf8')) > snapshot['defaults']['max_guide_bytes']:
        raise ValueError('Proposed guide exceeds bounded text limit')
    return copy.deepcopy(proposal)
