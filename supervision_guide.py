"""R04 single-file guide transactions. R01 wire contracts and R02 costs unchanged.

Only the trusted parent writes ACTIVE_GUIDE. Immutable plans/receipts and the
existing hash-chained operation journal retain history. No model or research
state/budget writer is called. Fake proposals require disposable fixture roots.
"""
from __future__ import annotations

import base64
import difflib
import hashlib
import html
import json
from pathlib import Path
import re
import tempfile

import configuration
import supervision
import supervision_calls as calls
import supervision_executor as executor
import supervision_ledger as queue
import supervision_scheduler as scheduler
from supervision_contracts import canonical_hash
from supervision_snapshot import _path, _accepted, _source_path

ACTIVE = 'supervision/ACTIVE_GUIDE.md'
ABSENT = 'ABSENT'
MAX_GUIDE = 12288
PLAN_FIELDS = {'schema_version', 'event_id', 'project_id', 'kind', 'previous_event',
               'old_guide_sha256', 'new_guide_sha256', 'before', 'after', 'binding', 'diff'}
KINDS = {'APPLY': ('guide-plans', 'guide-applied', 'GUIDE_PREPARED', 'GUIDE_APPLIED', 'APPLIED'),
         'ROLLBACK': ('guide-rollbacks', 'guide-reverted', 'GUIDE_ROLLBACK_PREPARED', 'GUIDE_ROLLED_BACK', 'ROLLED_BACK')}


def _hash(raw): return hashlib.sha256(raw).hexdigest() if raw is not None else ABSENT


def _read(path):
    if not path.exists(): return None
    if not path.is_file() or path.stat().st_size > MAX_GUIDE: raise ValueError('GUIDE_CONFLICT: invalid guide file')
    return path.read_bytes()


def _object(path):
    if path.stat().st_size > 100000: raise ValueError('Oversized guide audit artifact')
    value = executor.strict_json(path.read_text(encoding='utf8'))
    if not isinstance(value, dict) or value.get('payload_sha256') != canonical_hash({
            k: v for k, v in value.items() if k != 'payload_sha256'}):
        raise ValueError('Corrupt immutable guide artifact')
    return value


def _immutable(path, payload):
    expected = {**payload, 'payload_sha256': canonical_hash(payload)}
    if len(supervision._json_bytes(expected)) > 100000:
        raise ValueError('REJECTED_POLICY: guide audit artifact exceeds byte limit')
    if path.exists():
        if _object(path) != expected: raise ValueError('Guide artifact differs from original immutable version')
        return expected
    return queue._write_immutable(path, payload)


def _fixture_path(controller, project):
    queue.home(controller, project)  # Registered project and no linked roots.
    return _path(controller, 'state/supervision-fixtures/' + configuration.project_id(project) + '.json')


def _fixture_root(controller):
    root = Path(controller).resolve()
    if (not root.name.startswith('crc-r04-fixture-') or root == Path(tempfile.gettempdir()).resolve()
            or not root.is_relative_to(Path(tempfile.gettempdir()).resolve()) or (root / '.git').exists()):
        raise ValueError('FAKE_NOT_DISPOSABLE_FIXTURE')
    return root


def register_fixture(controller, project):
    """Test harness only; no CLI allow-fake override or real-project adoption."""
    root = _fixture_root(controller)
    payload = {'schema_version': 1, 'purpose': 'R04_OFFLINE_SYNTHETIC_ONLY',
        'controller_sha256': canonical_hash(str(root)), 'project_id': configuration.project_id(project)}
    _immutable(_fixture_path(controller, project), payload)


def _require_fixture(controller, project):
    root = _fixture_root(controller)
    marker = _object(_fixture_path(controller, project))
    expected = {'schema_version': 1, 'purpose': 'R04_OFFLINE_SYNTHETIC_ONLY',
        'controller_sha256': canonical_hash(str(root)), 'project_id': configuration.project_id(project)}
    if marker != {**expected, 'payload_sha256': canonical_hash(expected)}:
        raise ValueError('FAKE_NOT_DISPOSABLE_FIXTURE')


def _proposal(controller, project, event_id):
    record = queue.read_event(controller, project, event_id)
    _, reserved = queue.reservations(controller, project)
    saved = reserved.get(event_id)
    if not saved or saved['state'] != 'PROPOSED': raise ValueError('R03_COMPLETION_NOT_SETTLED')
    receipt = calls._read_completion(controller, project, event_id, saved)
    if not receipt or receipt['state'] != 'PROPOSED': raise ValueError('R03_VALIDATED_PROPOSAL_REQUIRED')
    witnessed = {op['type'] for op in queue.operations(controller, project) if op['id'] == event_id}
    if not {'CALL_COMPLETED', 'CLAIM_FINISHED'} <= witnessed:
        raise ValueError('R03_COMPLETION_REPLAY_REQUIRED')
    metadata = executor.strict_json(receipt['log'])
    if (not isinstance(metadata, dict) or metadata.get('executor_protocol') != 'R03'
            or metadata.get('snapshot_hash') != record['snapshot']['input_snapshot_sha256']
            or metadata.get('output_hash') != _hash(receipt['raw_output'].encode('utf8'))
            or metadata.get('output_truncated') is not False or type(metadata.get('exit_code')) is not int
            or metadata['exit_code'] != 0 or metadata.get('advisory_only') is not True
            or metadata.get('proof_authority') is not False):
        raise ValueError('R03_PROVENANCE_REQUIRED')
    if metadata.get('backend') != 'fake': raise ValueError('REAL_SUPERVISOR_BACKEND_BLOCKED')
    _require_fixture(controller, project)
    proposal = executor._validate_output(receipt['raw_output'], record, executor.review_data(record))
    text = '\n'.join(str(v) for v in proposal.values())
    prohibited = (r'已证明(?:安全|正确)|已经证明|证明已闭合|通过安全证明|(?:安全性|定理).{0,12}已证',
        r'(?:预算|budget).{0,40}(?:加|增|重置|补充|扩大|increase|add|reset|replenish)',
        r'(?:increase|add|reset|replenish|增加|重置).{0,40}(?:预算|budget)',
        r'(?:修改|改写|覆盖|放宽|变更|删除).{0,40}(?:目标|GOAL|安全模型|证明义务)',
        r'\b(?:python(?:\d+(?:\.\d+)*)?(?:\.exe)?|sh|sudo|rm|del|remove-item|invoke-webrequest)\s+\S+',
        r'[/\\](?:bin[/\\](?:sh|bash)|Windows[/\\]System32)')
    if any(re.search(pattern, text, re.IGNORECASE) for pattern in prohibited):
        raise ValueError('REJECTED_POLICY: unsafe goal, proof, command or budget request')
    return record, proposal, receipt


def _fresh(controller, project, record):
    """No snapshot rebuild: exact captured source hashes and accepted-run binding."""
    snapshot = record['snapshot']
    try:
        guard = scheduler._event_guard(controller, project, record)
        if not guard['claim_allowed']: raise ValueError('route/goal/stop changed')
        if 'ACTIVE_ATTEMPT_READONLY' in guard['restrictions']: raise ValueError('fixed attempt active')
        state = configuration.load_json(_path(project, 'research/STATE.json'))
        route = configuration.load_json(_path(controller, 'state/routes/' + configuration.project_id(project) + '.json'))
        _, accepted = _accepted(route, state)
        if not accepted or accepted[-1] != snapshot['route_summary']['accepted_run_ids'][-1]:
            raise ValueError('accepted run changed')
        from runner_core import digest_file
        for source in snapshot['source_manifest']:
            root = project if source['scope'] == 'PROJECT' else controller
            path = _path(root, source['path'])
            if not path.is_file() or digest_file(path) != source['sha256']: raise ValueError('source changed')
        for source in snapshot['missing']:
            if source['reason'] != 'MISSING': continue
            root = project if source['scope'] == 'PROJECT' else controller
            if _path(root, source['path']).exists(): raise ValueError('previously missing source appeared')
        # R01 may omit unreferenced inputs. Unknown security constraints cannot
        # silently enter a guide's authority: require complete frozen coverage.
        inputs = _path(project, 'inputs')
        actual_inputs = set()
        if inputs.exists():
            import os
            for base, dirs, files in os.walk(inputs, followlinks=False):
                for name in dirs + files:
                    relative = (Path(base) / name).relative_to(project).as_posix()
                    path = _source_path(project, relative)
                    if name in files and path.is_file(): actual_inputs.add(relative)
        captured_inputs = {s['path'] for s in snapshot['source_manifest']
                           if s['scope'] == 'PROJECT' and s['path'].startswith('inputs/')}
        if actual_inputs != captured_inputs: raise ValueError('security inputs are not fully frozen')
        if snapshot['claim_status']['present']:
            from engine.claim_graph import status
            if status(project)['claims'] != snapshot['claim_status']['claims']:
                raise ValueError('canonical claim verification status changed')
    except (ValueError, OSError, KeyError, IndexError) as exc:
        raise ValueError('REJECTED_STALE: frozen inputs or accepted-run binding changed') from exc


def _quote(text):
    text = html.escape(str(text), quote=True)
    text = re.sub(r'([\\`*_{}\[\]()#+!|])', r'\\\1', text)
    return '\n'.join('> ' + line for line in text.splitlines())


def _render(record, proposal):
    snapshot = record['snapshot']; event = record['event']
    lines = ['# Controller-generated supervision guide',
        'OFFLINE FIXTURE ONLY. Unverified scheduling advice; no scientific or route authority.',
        'GOAL and frozen problem, security assumptions, proof obligations, gates and route-review directives take priority.',
        'Event: ' + event['event_id'], 'Input snapshot: ' + snapshot['input_snapshot_sha256'],
        'Goal SHA-256: ' + event['focus']['goal_sha256'], 'Goal anchor: ' + event['focus']['anchor_id'],
        'Route epoch: ' + str(event['route_epoch']), 'Accepted run: ' + snapshot['route_summary']['accepted_run_ids'][-1],
        '## Frozen objective (reference only)', 'Read the unchanged GOAL.md; this guide cannot alter it.',
        '## Existing core obligations and verification scope',
        _quote('Selected: ' + str(proposal['next_obligation_id']) + '; frozen IDs: ' + ', '.join(snapshot['obligation_ids'])),
        'Existing verification receipts remain authoritative; this review does not upgrade proof status.',
        '## One next falsifiable task', _quote(proposal['next_task']),
        '## Success criterion', _quote(proposal['success_criterion']),
        '## Falsification criterion', _quote(proposal['falsification_criterion']),
        '## Evidence and limits', _quote(proposal['reason'])]
    lines += [_quote(ref['path'] + ' | SHA-256 ' + ref['sha256'] + ' | ' + ref['scope'] + ' | UNVERIFIED advice')
              for ref in proposal['evidence_refs']]
    lines += ['## Side work and unclosed questions (advice only)']
    lines += [_quote(note) for note in proposal['guide_notes']]
    raw = ('\n\n'.join(lines) + '\n').encode('utf8')
    if any(byte < 32 and byte not in (9, 10, 13) for byte in raw):
        raise ValueError('REJECTED_POLICY: control characters in guide')
    if len(raw) > min(MAX_GUIDE, snapshot['defaults']['max_guide_bytes']):
        raise ValueError('REJECTED_POLICY: rendered guide exceeds UTF-8 byte limit')
    return raw


def _diff(before, after):
    return ''.join(difflib.unified_diff((before or b'').decode('utf8').splitlines(True),
        (after or b'').decode('utf8').splitlines(True), fromfile=ACTIVE + ':old', tofile=ACTIVE + ':new'))


def _plan_path(controller, project, event_id, kind):
    return queue._event_path(controller, project, event_id, KINDS[kind][0])


def _receipt_path(controller, project, event_id, kind):
    return queue._event_path(controller, project, event_id, KINDS[kind][1])


def _abort_path(controller, project, event_id):
    return queue._event_path(controller, project, event_id, 'guide-aborted')


def _decode(text):
    if text is None: return None
    if not isinstance(text, str): raise ValueError('Invalid archived guide bytes')
    try: raw = base64.b64decode(text, validate=True); raw.decode('utf8')
    except (ValueError, UnicodeError) as exc: raise ValueError('Invalid archived guide encoding') from exc
    if len(raw) > MAX_GUIDE: raise ValueError('Oversized archived guide')
    return raw


def _plan(controller, project, event_id, kind):
    value = _object(_plan_path(controller, project, event_id, kind))
    if (set(value) != PLAN_FIELDS | {'payload_sha256'} or type(value['schema_version']) is not int or value['schema_version'] != 1
            or value['event_id'] != event_id or value['project_id'] != configuration.project_id(project)
            or value['kind'] != kind or (value['previous_event'] is not None and (
                not isinstance(value['previous_event'], str) or not queue.HEX.fullmatch(value['previous_event'])))):
        raise ValueError('Invalid guide transaction identity')
    before, after = _decode(value['before']), _decode(value['after'])
    if (value['old_guide_sha256'] != _hash(before) or value['new_guide_sha256'] != _hash(after)
            or value['diff'] != _diff(before, after) or (kind == 'APPLY' and after is None)):
        raise ValueError('Guide transaction bytes differ from recorded hashes')
    return value


def _receipt_payload(plan):
    return {'schema_version': 1, 'event_id': plan['event_id'], 'plan_sha256': plan['payload_sha256'],
        'status': KINDS[plan['kind']][4], 'old_guide_sha256': plan['old_guide_sha256'],
        'new_guide_sha256': plan['new_guide_sha256']}


def _abort_payload(plan): return {**_receipt_payload(plan), 'status': 'REJECTED_STALE'}


def _ack(controller, project, kind, event_id, **details):
    found = [op for op in queue.operations(controller, project) if op['type'] == kind and op['id'] == event_id]
    if found:
        if len(found) != 1 or found[0]['details'] != details: raise ValueError('Guide operation witness conflict')
    else: queue.append(controller, project, kind, event_id, **details)


def _history(controller, project):
    log = queue.operations(controller, project)
    plans, receipts, done, pending = {}, {}, set(), []
    for kind, names in KINDS.items():
        folder = _path(queue.home(controller, project), names[0])
        for path in sorted(folder.glob('*.json')) if folder.exists() else []:
            plans[(kind, path.stem)] = _plan(controller, project, path.stem, kind)
        receipt_folder = _path(queue.home(controller, project), names[1])
        for path in sorted(receipt_folder.glob('*.json')) if receipt_folder.exists() else []:
            key = (kind, path.stem)
            if key not in plans: raise ValueError('Guide receipt lost its original plan')
            expected = _receipt_payload(plans[key]); receipt = _object(path)
            if receipt != {**expected, 'payload_sha256': canonical_hash(expected)}:
                raise ValueError('Guide receipt differs from original plan')
            receipts[key] = receipt
    abort_folder = _path(queue.home(controller, project), 'guide-aborted')
    for path in sorted(abort_folder.glob('*.json')) if abort_folder.exists() else []:
        key = ('APPLY', path.stem)
        if key not in plans or key in receipts: raise ValueError('Guide abort lost its plan or conflicts with completion')
        expected = _abort_payload(plans[key]); receipt = _object(path)
        if receipt != {**expected, 'payload_sha256': canonical_hash(expected)}:
            raise ValueError('Guide abort differs from original plan')
        receipts[key] = receipt
    head = None; aborted = set()
    for op in log:
        if op['type'] == 'GUIDE_ABORTED':
            key = ('APPLY', op['id']); plan = plans.get(key); receipt = receipts.get(key)
            if (plan is None or receipt is None or receipt['status'] != 'REJECTED_STALE' or key in done
                    or op['details'] != {'plan_sha256': plan['payload_sha256'], 'receipt_sha256': receipt['payload_sha256']}):
                raise ValueError('Invalid guide abort witness')
            done.add(key); aborted.add(key)
            continue
        for kind, names in KINDS.items():
            if op['type'] not in names[2:4]: continue
            key = (kind, op['id']); plan = plans.get(key)
            if plan is None: raise ValueError('Acknowledged guide plan is missing')
            expected = {'plan_sha256': plan['payload_sha256']}
            if op['type'] == names[3]:
                if key not in receipts: raise ValueError('Acknowledged guide receipt is missing')
                expected['receipt_sha256'] = receipts[key]['payload_sha256']
                if key in done: raise ValueError('Duplicate guide commit witness')
                if kind == 'APPLY':
                    old = plans[('APPLY', head)]['new_guide_sha256'] if head else ABSENT
                    if plan['previous_event'] != head or plan['old_guide_sha256'] != old:
                        raise ValueError('Guide version chain conflict')
                    head = plan['event_id']
                else:
                    original = plans.get(('APPLY', op['id']))
                    if (head != op['id'] or original is None or plan['previous_event'] != original['previous_event']
                            or plan['before'] != original['after'] or plan['after'] != original['before']):
                        raise ValueError('Guide rollback chain conflict')
                    head = plan['previous_event']
                done.add(key)
            if op['details'] != expected: raise ValueError('Guide audit witness differs from artifact')
    for key in plans:
        if key not in done: pending.append(key)
    if len(pending) > 1: raise ValueError('Multiple unfinished guide transactions; operator audit required')
    return {'head': head, 'plans': plans, 'receipts': receipts, 'done': done, 'pending': pending, 'aborted': aborted}


def _managed(controller, project, history):
    raw = _read(_path(project, ACTIVE))
    expected = history['plans'][('APPLY', history['head'])]['new_guide_sha256'] if history['head'] else ABSENT
    allowed = {expected}
    for key in history['pending']:
        plan = history['plans'][key]; allowed.update((plan['old_guide_sha256'], plan['new_guide_sha256']))
    if _hash(raw) not in allowed: raise ValueError('GUIDE_CONFLICT: external edit; refusing overwrite')
    return raw


def _binding(record, proposal, receipt):
    return {'event_payload_sha256': record['payload_sha256'], 'proposal_sha256': canonical_hash(proposal),
            'completion_sha256': receipt['payload_sha256'], 'input_snapshot_sha256': record['snapshot']['input_snapshot_sha256']}


def _new_plan(controller, project, event_id, kind, before, after, previous_event, binding):
    payload = {'schema_version': 1, 'event_id': event_id, 'project_id': configuration.project_id(project),
        'kind': kind, 'previous_event': previous_event, 'old_guide_sha256': _hash(before), 'new_guide_sha256': _hash(after),
        'before': base64.b64encode(before).decode('ascii') if before is not None else None,
        'after': base64.b64encode(after).decode('ascii') if after is not None else None,
        'binding': binding, 'diff': _diff(before, after)}
    return _immutable(_plan_path(controller, project, event_id, kind), payload)


def _commit_receipt(controller, project, plan):
    receipt = _immutable(_receipt_path(controller, project, plan['event_id'], plan['kind']), _receipt_payload(plan))
    _ack(controller, project, KINDS[plan['kind']][3], plan['event_id'],
         plan_sha256=plan['payload_sha256'], receipt_sha256=receipt['payload_sha256'])
    return {k: receipt[k] for k in _receipt_payload(plan)}


def _commit_abort(controller, project, plan):
    receipt = _immutable(_abort_path(controller, project, plan['event_id']), _abort_payload(plan))
    _ack(controller, project, 'GUIDE_ABORTED', plan['event_id'],
         plan_sha256=plan['payload_sha256'], receipt_sha256=receipt['payload_sha256'])
    return {k: receipt[k] for k in _receipt_payload(plan)}


def _resume(controller, project, plan, history):
    key = (plan['kind'], plan['event_id'])
    _require_fixture(controller, project)
    if key in history['done']: return {k: history['receipts'][key][k] for k in _receipt_payload(plan)}
    current = _managed(controller, project, history)
    before, after = _decode(plan['before']), _decode(plan['after'])
    if current not in (before, after): raise ValueError('GUIDE_CONFLICT: transaction version changed')
    _ack(controller, project, KINDS[plan['kind']][2], plan['event_id'], plan_sha256=plan['payload_sha256'])
    if key in history['receipts']:
        if history['receipts'][key]['status'] == 'REJECTED_STALE':
            if current != before: raise ValueError('GUIDE_CONFLICT: rejected transaction changed')
            return _commit_abort(controller, project, plan)
        if current != after: raise ValueError('GUIDE_CONFLICT: completed receipt differs from current file')
        return _commit_receipt(controller, project, plan)
    record, proposal, receipt = _proposal(controller, project, plan['event_id'])
    if plan['kind'] == 'APPLY':
        if plan['binding'] != _binding(record, proposal, receipt): raise ValueError('Guide proposal binding changed')
        try: _fresh(controller, project, record)
        except ValueError:
            if current == after: supervision._write(_path(project, ACTIVE), before)
            return _commit_abort(controller, project, plan)
    elif 'ACTIVE_ATTEMPT_READONLY' in scheduler.restrictions(controller, project)['restrictions']:
        raise ValueError('ACTIVE_ATTEMPT_READONLY: guide rollback blocked')
    target = _path(project, ACTIVE)
    try:
        # Re-read immediately before replacement; all controller writers hold the
        # original route/core/queue locks. Unknown human changes are never undone.
        if _read(target) != current: raise ValueError('GUIDE_CONFLICT: concurrent external edit')
        if current != after: supervision._write(target, after)
        if _read(target) != after: raise ValueError('GUIDE_CONFLICT: file changed during replacement')
        if plan['kind'] == 'APPLY':
            try: _fresh(controller, project, record)
            except ValueError:
                supervision._write(target, before)
                return _commit_abort(controller, project, plan)
        return _commit_receipt(controller, project, plan)
    except Exception:
        # Receipt persistence is the commit point. If it exists, never undo it;
        # a missing journal ACK is repaired by recover, without another write.
        if not _receipt_path(controller, project, plan['event_id'], plan['kind']).exists() and _read(target) == after:
            supervision._write(target, before)
        raise


def preview(controller, project, event_id):
    """Read-only: no locks, enrollment, settlement, artifacts or provider calls."""
    history = _history(controller, project); current = _managed(controller, project, history)
    record, proposal, receipt = _proposal(controller, project, event_id)
    _fresh(controller, project, record)
    plan = history['plans'].get(('APPLY', event_id))
    after = _decode(plan['after']) if plan else _render(record, proposal)
    before = _decode(plan['before']) if plan else current
    return {'event_id': event_id, 'status': 'PREVIEW', 'old_guide_sha256': _hash(before),
        'new_guide_sha256': _hash(after), 'diff': _diff(before, after), 'guide': after.decode('utf8'),
        'automatic_apply_allowed': proposal['action'] in {'KEEP_GUIDE', 'REFOCUS_RECOMMENDED'}
                                   and not proposal['requires_operator_approval']}


def apply(controller, project, event_id, *, expected_hash):
    with scheduler._locks(controller, project, execution=True):
        history = _history(controller, project); current = _managed(controller, project, history)
        if ('ROLLBACK', event_id) in history['done']:
            plan = history['plans'][('ROLLBACK', event_id)]
            return _resume(controller, project, plan, history)
        key = ('APPLY', event_id)
        if key in history['plans']:
            if key not in history['done'] and expected_hash != history['plans'][key]['old_guide_sha256']:
                raise ValueError('GUIDE_CONFLICT: expected hash differs from original plan')
            return _resume(controller, project, history['plans'][key], history)
        if history['pending']: raise ValueError('GUIDE_RECOVERY_REQUIRED: finish original transaction first')
        if _hash(current) != expected_hash: raise ValueError('GUIDE_CONFLICT: expected old guide hash differs')
        record, proposal, receipt = _proposal(controller, project, event_id)
        _fresh(controller, project, record)
        if proposal['requires_operator_approval'] or proposal['action'] in {'PAUSE_RECOMMENDED', 'ESCALATE'}:
            return {'status': 'ADVISORY_ONLY', 'event_id': event_id, 'state_unchanged': True}
        if not scheduler.enabled(controller, project): raise ValueError('SUPERVISION_DISABLED')
        plan = _new_plan(controller, project, event_id, 'APPLY', current, _render(record, proposal),
                         history['head'], _binding(record, proposal, receipt))
        history['plans'][key] = plan; history['pending'] = [key]
        return _resume(controller, project, plan, history)


def rollback(controller, project, event_id, *, expected_hash):
    with scheduler._locks(controller, project, execution=True):
        history = _history(controller, project); current = _managed(controller, project, history)
        key = ('ROLLBACK', event_id)
        if key in history['plans']:
            if key not in history['done'] and expected_hash != history['plans'][key]['old_guide_sha256']:
                raise ValueError('GUIDE_CONFLICT: expected hash differs from original rollback plan')
            return _resume(controller, project, history['plans'][key], history)
        if history['pending']: raise ValueError('GUIDE_RECOVERY_REQUIRED')
        if history['head'] != event_id or _hash(current) != expected_hash:
            raise ValueError('GUIDE_CONFLICT: only the current exact version can be rolled back')
        original = history['plans'][('APPLY', event_id)]
        plan = _new_plan(controller, project, event_id, 'ROLLBACK', current, _decode(original['before']),
                         original['previous_event'], original['binding'])
        history['plans'][key] = plan; history['pending'] = [key]
        return _resume(controller, project, plan, history)


def recover(controller, project, event_id):
    with scheduler._locks(controller, project, execution=True):
        history = _history(controller, project); _managed(controller, project, history)
        kind = 'ROLLBACK' if ('ROLLBACK', event_id) in history['plans'] else 'APPLY'
        if (kind, event_id) not in history['plans']: raise ValueError('No original guide transaction to recover')
        return _resume(controller, project, history['plans'][(kind, event_id)], history)


def prompt_context(controller, project):
    """Verified single insertion; stale scientific inputs yield an expiry notice."""
    folder = Path(controller) / 'state/supervision' / configuration.project_id(project) / 'event_queue'
    if not (Path(project) / ACTIVE).exists() and not (folder / 'guide-plans').exists(): return ''
    history = _history(controller, project); current = _managed(controller, project, history)
    if history['pending']:
        plan = history['plans'][history['pending'][0]]
        if _hash(current) != plan['old_guide_sha256']:
            raise ValueError('GUIDE_RECOVERY_REQUIRED before loading a replaced guide')
    if history['head'] is None: return ''
    plan = history['plans'][('APPLY', history['head'])]
    record, _, _ = _proposal(controller, project, history['head'])
    try: _fresh(controller, project, record)
    except ValueError:
        return '# Supervision guide EXPIRED\nFrozen inputs changed; ignore the archived task and use GOAL/current accepted state. No scientific status was changed.'
    if current != _decode(plan['after']): raise ValueError('GUIDE_CONFLICT: current guide does not match accepted history')
    return current.decode('utf8')


def event_status(controller, project, event_id):
    history = _history(controller, project)
    if ('APPLY', event_id) not in history['plans']: return None
    aborted = ('APPLY', event_id) in history['aborted']
    applied = ('APPLY', event_id) in history['done'] and not aborted
    rolled_back = ('ROLLBACK', event_id) in history['done']
    return {'applied': applied, 'state': 'REJECTED_STALE' if aborted else 'ROLLED_BACK' if rolled_back else 'APPLIED' if applied else 'PREPARED',
            'active': history['head'] == event_id, 'recovery_required': any(key[1] == event_id for key in history['pending'])}
