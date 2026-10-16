"""Versioned mathematical claims with transitive invalidation and scoped reviews."""
from __future__ import annotations
import copy
import re
import uuid
import configuration
from research_quality import CORE_TYPES, hash_file, local_file, read_object, validate_technical_review
from .common import (STORE, evidence, fresh, goal_binding, identifier, object_hash,
                     policy, stamp, strings, text)
from .problem_compiler import get_problem


def load(project):
    return configuration.load_json(project / STORE / 'CLAIM_GRAPH.json',
        {'schema_version': 1, 'claims': [], 'events': []})


def save(project, data):
    configuration.atomic_json(project / STORE / 'CLAIM_GRAPH.json', data)


def dependency_bindings_valid(item):
    """Check exact recorded ordinary pins without rebinding to current authority."""
    if not isinstance(item, dict) or not isinstance(item.get('spec'), dict): return False
    declared = item['spec'].get('dependencies'); pins = item.get('dependency_pins')
    if (not isinstance(declared, list) or not all(isinstance(dep, str) for dep in declared)
            or len(declared) != len(set(declared)) or not isinstance(pins, dict)
            or set(pins) != set(declared)):
        return False
    try:
        for dep in declared: identifier(dep)
    except ValueError: return False
    return all(isinstance(pin, dict) and set(pin) == {'revision', 'spec_sha256'}
               and type(pin['revision']) is int and pin['revision'] > 0
               and isinstance(pin['spec_sha256'], str)
               and re.fullmatch(r'[0-9a-f]{64}', pin['spec_sha256']) is not None
               for pin in pins.values())


_AUDIT_FIELDS = {'receipt_history_schema_version', 'receipt_history_availability',
                 'receipt_history', 'current_receipt_ids', 'legacy_current_receipts'}


def _current_receipts(item):
    reviews = item.get('reviews')
    if not isinstance(reviews, dict): raise ValueError('Invalid review collection')
    if not set(reviews) <= {'proof', 'statement', 'novelty', 'formal_audit'}:
        raise ValueError('Invalid review slot')
    result = {'review:' + kind: receipt for kind, receipt in reviews.items()}
    for field in ('formal_receipt', 'counterexample_receipt'):
        if item.get(field) is not None: result['tool:' + field] = item[field]
    return result


def _receipt_reference(record):
    return {key: record[key] for key in ('operation_id', 'record_sha256', 'receipt_sha256')}


def receipt_history_valid(item, events=None):
    """Legacy absence is explicit compatibility; present audit metadata must agree."""
    present = _AUDIT_FIELDS & set(item)
    recorded = [event for event in (events or []) if isinstance(event, dict)
                and event.get('id') == item.get('id') and event.get('revision') == item.get('revision')
                and event.get('type') in {'INDEPENDENT_REVIEW', 'TOOL_RESULT'} and event.get('operation_id')]
    if not present: return not recorded
    if present != _AUDIT_FIELDS: return False
    try:
        if (type(item['receipt_history_schema_version']) is not int
                or item['receipt_history_schema_version'] != 1
                or item['receipt_history_availability'] not in
                    {'COMPLETE_SINCE_IMPORT', 'LEGACY_OPERATIONS_UNAVAILABLE'}): return False
        records = item['receipt_history']; legacy = item['legacy_current_receipts']
        if not isinstance(records, list) or not isinstance(legacy, dict): return False
        if item['receipt_history_availability'] == 'COMPLETE_SINCE_IMPORT' and legacy: return False
        expected = {}; latest = {}; previous = None; seen = set()
        for slot, old in legacy.items():
            if (not isinstance(old, dict)
                    or old.get('availability') != 'CURRENT_SNAPSHOT_ONLY_OPERATION_HISTORY_UNAVAILABLE'
                    or not isinstance(old.get('receipt'), dict)
                    or old.get('receipt_sha256') != object_hash(old['receipt'])): return False
            expected[slot] = old['receipt_sha256']
        fields = {'schema_version', 'operation_id', 'operation_type', 'claim_id', 'claim_revision',
                  'claim_sha256', 'slot', 'receipt', 'receipt_sha256', 'source_bindings', 'reason', 'at',
                  'previous_operation_id', 'previous_record_sha256', 'supersedes_operation_id',
                  'supersedes_record_sha256', 'legacy_previous_receipt_sha256', 'record_sha256'}
        for record in records:
            if not isinstance(record, dict) or set(record) != fields: return False
            if (type(record['schema_version']) is not int or record['schema_version'] != 1
                    or record['claim_id'] != item['id']
                    or type(record['claim_revision']) is not int or record['claim_revision'] != item['revision']
                    or record['claim_sha256'] != item['spec_sha256']
                    or not isinstance(record['operation_id'], str)
                    or not re.fullmatch(r'[0-9a-f]{32}', record['operation_id'])
                    or record['operation_id'] in seen): return False
            receipt = record['receipt']; slot = record['slot']
            if (not isinstance(receipt, dict) or not isinstance(slot, str)
                    or record['receipt_sha256'] != object_hash(receipt)
                    or record['record_sha256'] != object_hash({k: v for k, v in record.items() if k != 'record_sha256'})
                    or record['claim_sha256'] != receipt.get('claim_sha256')): return False
            if slot.startswith('review:'):
                if (slot[7:] not in {'proof', 'statement', 'novelty', 'formal_audit'}
                        or record['operation_type'] != 'INDEPENDENT_REVIEW'
                        or record['source_bindings'] != receipt.get('evidence')): return False
            elif slot in {'tool:formal_receipt', 'tool:counterexample_receipt'}:
                if (record['operation_type'] != 'TOOL_RESULT'
                        or record['source_bindings'] != receipt.get('source_bindings')
                        or type(receipt.get('claim_revision')) is not int or receipt.get('claim_revision') != item['revision']
                        or receipt.get('claim_id') != item['id']): return False
            else: return False
            if record['reason'] != receipt.get('reason'): return False
            if (record['previous_operation_id'] != (previous['operation_id'] if previous else None)
                    or record['previous_record_sha256'] != (previous['record_sha256'] if previous else None)):
                return False
            prior = latest.get(slot)
            if (record['supersedes_operation_id'] != (prior['operation_id'] if prior else None)
                    or record['supersedes_record_sha256'] != (prior['record_sha256'] if prior else None)
                    or record['legacy_previous_receipt_sha256'] !=
                        (legacy[slot]['receipt_sha256'] if prior is None and slot in legacy else None)):
                return False
            seen.add(record['operation_id']); previous = record; latest[slot] = record
            expected[slot] = record['receipt_sha256']
        if item['current_receipt_ids'] != {slot: _receipt_reference(record) for slot, record in latest.items()}:
            return False
        if events is not None:
            if len(recorded) != len(records): return False
            by_operation = {record['operation_id']: record for record in records}
            for event in recorded:
                record = by_operation.pop(event['operation_id'], None)
                if (record is None or any(event.get(key) != value for key, value in _receipt_reference(record).items())
                        or event.get('claim_sha256') != item['spec_sha256']
                        or event.get('type') != record['operation_type']): return False
                if record['slot'].startswith('review:'):
                    if (event.get('kind') != record['slot'][7:]
                            or event.get('reviewer') != record['receipt'].get('reviewer')): return False
                elif (event.get('field') != record['slot'][5:]
                        or event.get('status') != record['receipt'].get('status')): return False
            if by_operation: return False
        current = _current_receipts(item)
        return set(current) == set(expected) and all(isinstance(receipt, dict)
            and object_hash(receipt) == expected[slot] for slot, receipt in current.items())
    except (KeyError, TypeError, ValueError): return False


def _append_receipt(item, slot, receipt):
    if not receipt_history_valid(item): raise ValueError('RECEIPT_HISTORY_INVALID: explicit audit recovery required')
    if not (_AUDIT_FIELDS & set(item)):
        item.update(receipt_history_schema_version=1,
            receipt_history_availability='LEGACY_OPERATIONS_UNAVAILABLE',
            receipt_history=[], current_receipt_ids={},
            legacy_current_receipts={key: {'availability': 'CURRENT_SNAPSHOT_ONLY_OPERATION_HISTORY_UNAVAILABLE',
                'receipt': copy.deepcopy(value), 'receipt_sha256': object_hash(value)}
                for key, value in _current_receipts(item).items()})
    records = item['receipt_history']; previous = records[-1] if records else None
    prior = next((r for r in reversed(records) if r['slot'] == slot), None)
    old = item['legacy_current_receipts'].get(slot)
    record = {'schema_version': 1, 'operation_id': uuid.uuid4().hex,
        'operation_type': 'INDEPENDENT_REVIEW' if slot.startswith('review:') else 'TOOL_RESULT',
        'claim_id': item['id'], 'claim_revision': item['revision'], 'claim_sha256': item['spec_sha256'],
        'slot': slot, 'receipt': copy.deepcopy(receipt), 'receipt_sha256': object_hash(receipt),
        'source_bindings': copy.deepcopy(receipt.get('evidence' if slot.startswith('review:') else 'source_bindings')),
        'reason': receipt.get('reason'), 'at': stamp(),
        'previous_operation_id': previous['operation_id'] if previous else None,
        'previous_record_sha256': previous['record_sha256'] if previous else None,
        'supersedes_operation_id': prior['operation_id'] if prior else None,
        'supersedes_record_sha256': prior['record_sha256'] if prior else None,
        'legacy_previous_receipt_sha256': old['receipt_sha256'] if old is not None and prior is None else None}
    record['record_sha256'] = object_hash(record)
    records.append(record); item['current_receipt_ids'][slot] = _receipt_reference(record)
    return record


def get(project, claim_id):
    identifier(claim_id)
    item = next((c for c in load(project)['claims'] if c['id'] == claim_id), None)
    if item is None: raise ValueError('Unknown claim: ' + claim_id)
    if item.get('formal_receipt'): item['formal_receipt_sha256'] = object_hash(item['formal_receipt'])
    return item


def import_claim(project, spec, reason):
    if not isinstance(spec, dict) or spec.get('schema_version') != 1: raise ValueError('Claim schema_version must be 1')
    cid = identifier(spec.get('id'))
    for key in ('statement', 'proposer', 'nontriviality_argument'): text(spec.get(key), key)
    strings(spec.get('assumptions'), 'assumptions')
    strings(spec.get('dependencies'), 'dependencies', empty=True)
    if 'knowledge_dependencies' in spec:
        strings(spec['knowledge_dependencies'], 'knowledge_dependencies', empty=True)
        if len(spec['knowledge_dependencies']) != len(set(spec['knowledge_dependencies'])):
            raise ValueError('Duplicate knowledge dependency')
    strings(spec.get('obligation_ids'), 'obligation_ids')
    if spec.get('contribution_type') not in CORE_TYPES: raise ValueError('Claim requires a theoretical contribution type')
    if spec.get('verification_mode') not in {'FORMAL_REQUIRED', 'INDEPENDENT_MANUAL'}:
        raise ValueError('Claim must declare FORMAL_REQUIRED or INDEPENDENT_MANUAL verification_mode')
    text(spec.get('formal_applicability_reason'), 'formal_applicability_reason')
    if spec.get('verification_mode') == 'FORMAL_REQUIRED' and not isinstance(spec.get('formal_target'), dict):
        raise ValueError('FORMAL_REQUIRED needs formal_target file/declaration')
    if 'formal_target' in spec:
        target = spec['formal_target']
        if not isinstance(target, dict) or set(target) != {'file', 'declaration'}: raise ValueError('Invalid formal_target')
        source = local_file(project, target['file'], roots={'proofs'})
        source.relative_to((project / 'proofs/lean').resolve())
        if source.suffix != '.lean': raise ValueError('formal_target must name a Lean source')
        text(target['declaration'], 'formal declaration')
    text(reason, 'claim import reason')
    problem = get_problem(project, spec.get('problem_id'), spec.get('problem_version'))
    if spec.get('problem_version') != problem['version']: raise ValueError('Claim must pin an exact problem_version')
    if not set(spec['obligation_ids']) <= {o['id'] for o in problem['spec']['obligations']}:
        raise ValueError('Claim lists obligations outside its problem')
    if 'machine_statement' in spec:
        from .falsification import validate_statement
        validate_statement(spec['machine_statement'])
    bindings = evidence(project, spec.get('evidence_paths'))
    graph = load(project); by_id = {c['id']: c for c in graph['claims']}
    if len(spec['dependencies']) != len(set(spec['dependencies'])): raise ValueError('Duplicate claim dependency')
    for dep in spec['dependencies']:
        identifier(dep)
        if dep not in by_id: raise ValueError('Import dependencies first: ' + dep)
    proposed = {key: value['spec']['dependencies'] for key, value in by_id.items()}
    proposed[cid] = spec['dependencies']
    visiting = set(); done = set()
    def visit(key):
        if key in visiting: raise ValueError('Claim dependency graph must be acyclic')
        if key in done: return
        visiting.add(key)
        for dep in proposed[key]: visit(dep)
        visiting.remove(key); done.add(key)
    for key in proposed: visit(key)
    old = by_id.get(cid)
    digest = object_hash(spec)
    dep_pins = {d: {'revision': by_id[d]['revision'], 'spec_sha256': by_id[d]['spec_sha256']} for d in spec['dependencies']}
    knowledge_pins = {}
    if spec.get('knowledge_dependencies'):
        from .knowledge_graph import pin_dependencies
        knowledge_pins = pin_dependencies(project, spec['knowledge_dependencies'])
    current_binding = goal_binding(project)
    if old and old['spec_sha256'] == digest and old['evidence'] == bindings and old.get('dependency_pins') == dep_pins and old.get('knowledge_pins', {}) == knowledge_pins and old['binding'] == current_binding and not old.get('invalidated'):
        raise ValueError('Unchanged claim; no artificial revision')
    item = {'id': cid, 'revision': old['revision'] + 1 if old else 1,
        'spec': copy.deepcopy(spec), 'spec_sha256': digest, 'evidence': bindings,
        'binding': current_binding, 'problem_sha256': problem['spec_sha256'],
        'dependency_pins': dep_pins,
        'reviews': {}, 'invalidated': None, 'formal_receipt': None, 'counterexample_receipt': None,
        'receipt_history_schema_version': 1, 'receipt_history_availability': 'COMPLETE_SINCE_IMPORT',
        'receipt_history': [], 'current_receipt_ids': {}, 'legacy_current_receipts': {},
        'imported_at': stamp(),
        'history': (old.get('history', []) + [{k: copy.deepcopy(v) for k, v in old.items() if k != 'history'}]) if old else []}
    if 'knowledge_dependencies' in spec:
        item['knowledge_pins'] = knowledge_pins
    if old:
        graph['claims'][graph['claims'].index(old)] = item
    else: graph['claims'].append(item)
    graph['events'].append({'type': 'CLAIM_REVISED' if old else 'CLAIM_IMPORTED', 'id': cid,
                            'revision': item['revision'], 'reason': reason, 'at': stamp()})
    save(project, graph)
    refresh(project)
    return item


def receipt_fresh(project, item, receipt):
    if isinstance(receipt, dict) and receipt.get('output_file'):
        try:
            path = __import__('pathlib').Path(receipt['output_file'])
            path.resolve().relative_to((configuration.ROOT / 'logs').resolve())
            if hash_file(path) != receipt.get('output_sha256'): return False
        except (OSError, ValueError): return False
    return (isinstance(receipt, dict) and receipt.get('claim_revision') == item['revision']
            and receipt.get('claim_sha256') == item['spec_sha256']
            and fresh(project, receipt.get('source_bindings', {})))


def _revocation_latches(item, events):
    """Resolve persisted scope revocations from the canonical operation history."""
    latches = {}; positions = {}; set_at = {}
    history = item.get('receipt_history', [])
    receipts = {entry['operation_id']: entry for entry in (history if isinstance(history, list) else [])
                if isinstance(entry, dict) and isinstance(entry.get('operation_id'), str)}
    try:
        for index, event in enumerate(events):
            if event.get('id') != item['id'] or event.get('revision') != item['revision']: continue
            kind = event.get('type')
            if kind in {'INDEPENDENT_REVIEW', 'TOOL_RESULT'} and event.get('operation_id'):
                positions[event['operation_id']] = index
            elif kind == 'REVALIDATION_REQUIRED':
                latch = event['latch']; slot = latch['slot']
                if (set(latch) != {'schema_version', 'operation_id', 'claim_id', 'claim_revision',
                        'claim_sha256', 'slot', 'observed_reasons', 'receipt_sha256', 'at', 'latch_sha256'}
                        or type(latch['schema_version']) is not int or latch['schema_version'] != 1
                        or latch['claim_id'] != item['id'] or type(latch['claim_revision']) is not int
                        or latch['claim_revision'] != item['revision'] or latch['claim_sha256'] != item['spec_sha256']
                        or slot not in {'review:proof', 'review:statement', 'review:novelty',
                                        'review:formal_audit', 'tool:formal_receipt'}
                        or not isinstance(latch['observed_reasons'], list) or not latch['observed_reasons']
                        or not all(isinstance(reason, str) and reason for reason in latch['observed_reasons'])
                        or latch['latch_sha256'] != object_hash({k: v for k, v in latch.items() if k != 'latch_sha256'})
                        or slot in latches): return None
                latches[slot] = latch; set_at[slot] = index
            elif kind == 'REVALIDATION_REVIEWED':
                slot = event['slot']; receipt = receipts.get(event.get('receipt_operation_id'))
                if (slot not in latches or event.get('latch_sha256') != latches[slot]['latch_sha256']
                        or receipt is None or receipt['slot'] != slot
                        or positions.get(receipt['operation_id'], -1) <= set_at[slot]): return None
                del latches[slot]; del set_at[slot]
        stored = item.get('revocation_latches', {})
        return latches if isinstance(stored, dict) and stored == latches else None
    except (KeyError, TypeError, ValueError): return None


def status(project, *, _graph=None):
    graph = load(project) if _graph is None else _graph
    by_id = {c['id']: c for c in graph['claims']}; results = {}
    binding = goal_binding(project) if by_id else None
    visiting = set()
    def compute(cid):
        if cid in results: return results[cid]
        if cid in visiting: raise ValueError('Corrupt cyclic claim graph')
        visiting.add(cid)
        item = by_id[cid]; spec = item['spec']; reasons = []
        dependency_valid = dependency_bindings_valid(item)
        audit_valid = receipt_history_valid(item, graph.get('events'))
        latches = _revocation_latches(item, graph['events'])
        revocation_valid = latches is not None
        if not revocation_valid: reasons.append('REVOCATION_HISTORY_INVALID')
        latches = latches or {}
        if not dependency_valid: reasons.append('DEPENDENCY_BINDING_INVALID')
        if not audit_valid: reasons.append('RECEIPT_HISTORY_INVALID')
        if item.get('invalidated'): reasons.append(item['invalidated']['reason'])
        if object_hash(spec) != item['spec_sha256']: reasons.append('CLAIM_DIGEST_CHANGED')
        if binding != item['binding']: reasons.append('GOAL_OR_CONSTRAINTS_CHANGED')
        if not fresh(project, item['evidence']): reasons.append('EVIDENCE_CHANGED')
        knowledge_pins = item.get('knowledge_pins', {})
        if not isinstance(knowledge_pins, dict):
            reasons.append('KNOWLEDGE_BINDING_INVALID')
            knowledge_pins = {}
        if set(knowledge_pins) != set(spec.get('knowledge_dependencies', [])):
            reasons.append('KNOWLEDGE_BINDING_MISMATCH')
        if knowledge_pins:
            from .knowledge_graph import dependency_reasons
            reasons.extend(dependency_reasons(project, knowledge_pins, graph=graph))
        try:
            problem = get_problem(project, spec['problem_id'], spec['problem_version'])
            if problem['spec_sha256'] != item['problem_sha256'] or not fresh(project, problem['source_bindings']):
                reasons.append('PROBLEM_OR_SOURCE_CHANGED')
        except (OSError, ValueError, KeyError): reasons.append('PROBLEM_UNAVAILABLE')
        for dep, pin in item['dependency_pins'].items() if dependency_valid else []:
            parent = by_id.get(dep)
            if parent is None: reasons.append('DEPENDENCY_MISSING:' + dep); continue
            if pin != {'revision': parent['revision'], 'spec_sha256': parent['spec_sha256']}:
                reasons.append('DEPENDENCY_REVISED:' + dep)
            if compute(dep)['proof_status'] != 'INDEPENDENTLY_REVIEWED':
                reasons.append('DEPENDENCY_NOT_VALID:' + dep)
        reviews = item['reviews']
        def reviewed(kind):
            r = reviews.get(kind, {})
            return ('review:' + kind not in latches and bool(r)
                    and r.get('claim_sha256') == item['spec_sha256'] and fresh(project, r.get('evidence', {})))
        counterexample = item.get('counterexample_receipt')
        if counterexample and receipt_fresh(project, item, counterexample): reasons.append('MACHINE_STATEMENT_REFUTED')
        formal = item.get('formal_receipt')
        tool_ok = (dependency_valid and audit_valid and revocation_valid and 'tool:formal_receipt' not in latches
                   and receipt_fresh(project, item, formal) and formal.get('status') == 'TOOL_PASSED_AUDIT_PENDING')
        formal_review = reviews.get('formal_audit', {})
        formal_ok = tool_ok and reviewed('formal_audit') and formal_review.get('receipt_sha256') == object_hash(formal)
        manual_ok = reviewed('proof') and reviewed('statement')
        proven = not reasons and (formal_ok or manual_ok)
        novelty_ok = reviewed('novelty') and not reasons
        required_formal = policy(project)['formal_verification'] == 'required' or spec['verification_mode'] == 'FORMAL_REQUIRED'
        if required_formal and not formal_ok: proven = False
        accepted = proven and novelty_ok and (formal_ok or not required_formal)
        pending_proof = bool(reasons or set(latches) &
            {'review:proof', 'review:statement', 'review:formal_audit', 'tool:formal_receipt'})
        reported_reasons = reasons + ['REVALIDATION_REQUIRED:' + slot for slot in sorted(latches)]
        result = {'id': cid, 'revision': item['revision'], 'spec_sha256': item['spec_sha256'],
            'problem_id': spec['problem_id'], 'problem_version': spec['problem_version'],
            'statement': spec['statement'], 'obligation_ids': spec['obligation_ids'],
            'proof_status': 'INDEPENDENTLY_REVIEWED' if proven else 'PENDING_REVALIDATION' if pending_proof else 'CANDIDATE',
            'formal_status': 'AUDITED_TOOL_CHECK' if formal_ok and not reasons else 'TOOL_CHECKED_STATEMENT_PENDING' if tool_ok else 'NOT_VERIFIED',
            'novelty_status': 'REVIEWED_THEORETICAL_CONTRIBUTION' if novelty_ok else 'PENDING',
            'accepted_contribution': accepted, 'invalidation_reasons': reported_reasons,
            'revocation_latches': copy.deepcopy(latches),
            'receipt_history_availability': item.get('receipt_history_availability', 'LEGACY_OPERATIONS_UNAVAILABLE'),
            'review_scope': 'Operator-attested review; automated structure checks do not prove research truth'}
        results[cid] = result; visiting.remove(cid)
        return result
    for cid in by_id: compute(cid)
    return {'schema_version': 1, 'claims': [results[c['id']] for c in graph['claims']]}


def _pending_revocations(project, graph, current):
    pending = []
    for result in current['claims']:
        item = next(c for c in graph['claims'] if c['id'] == result['id'])
        latches = _revocation_latches(item, graph['events'])
        if latches is None: raise ValueError('REVOCATION_HISTORY_INVALID: explicit audit recovery required')
        observed = {}; receipts = _current_receipts(item)
        reasons = [reason for reason in result['invalidation_reasons'] if not reason.startswith('REVALIDATION_REQUIRED:')]
        positive_slots = [slot for slot in receipts if slot.startswith('review:')
            or slot == 'tool:formal_receipt' and receipts[slot].get('status') == 'TOOL_PASSED_AUDIT_PENDING']
        if reasons:
            observed.update({slot: reasons for slot in positive_slots})
        else:
            for kind, receipt in item['reviews'].items():
                if not fresh(project, receipt.get('evidence', {})):
                    observed['review:' + kind] = ['REVIEW_EVIDENCE_CHANGED:' + kind]
            formal = item.get('formal_receipt')
            if formal and formal.get('status') == 'TOOL_PASSED_AUDIT_PENDING' and not receipt_fresh(project, item, formal):
                observed['tool:formal_receipt'] = ['TOOL_SOURCE_OR_OUTPUT_CHANGED']
            if formal and 'formal_audit' in item['reviews'] and (
                    not receipt_fresh(project, item, formal) or formal.get('status') != 'TOOL_PASSED_AUDIT_PENDING'
                    or item['reviews']['formal_audit'].get('receipt_sha256') != object_hash(formal)):
                observed['review:formal_audit'] = ['FORMAL_TOOL_REVALIDATION_REQUIRED']
        for slot, causes in sorted(observed.items()):
            if slot in latches: continue
            pending.append({'claim_id': item['id'], 'claim_revision': item['revision'],
                'claim_sha256': item['spec_sha256'], 'slot': slot,
                'observed_reasons': list(causes), 'receipt_sha256': object_hash(receipts[slot])})
    return pending


def pending_revocations(project):
    """Pure diagnostic: existing positive attestations needing explicit observation."""
    graph = load(project)
    return _pending_revocations(project, graph, status(project, _graph=graph))


def refresh(project):
    """Explicitly persist observed revocations without changing goals, evidence or pins."""
    graph = load(project)
    current = status(project, _graph=graph)
    changed = False
    for observation in _pending_revocations(project, graph, current):
        item = next(c for c in graph['claims'] if c['id'] == observation['claim_id'])
        latch = {'schema_version': 1, 'operation_id': uuid.uuid4().hex, **observation, 'at': stamp()}
        latch['latch_sha256'] = object_hash(latch)
        item.setdefault('revocation_latches', {})[latch['slot']] = latch
        graph['events'].append({'type': 'REVALIDATION_REQUIRED', 'id': item['id'],
            'revision': item['revision'], 'latch': copy.deepcopy(latch), 'at': stamp()})
        changed = True
    if changed: current = status(project, _graph=graph)
    for result in current['claims']:
        item = next(c for c in graph['claims'] if c['id'] == result['id'])
        summary = {'proof_status': result['proof_status'], 'reasons': result['invalidation_reasons']}
        if item.get('last_validity') != summary:
            item['last_validity'] = summary; changed = True
            graph['events'].append({'type': 'VALIDITY_CHANGED', 'id': result['id'], **summary, 'at': stamp()})
    if changed: save(project, graph)
    return current


def _release_revalidation_scope(project, graph, item, slot, receipt):
    latches = _revocation_latches(item, graph['events'])
    if latches is None: raise ValueError('REVOCATION_HISTORY_INVALID: explicit audit recovery required')
    if slot not in latches: return
    current = next(c for c in status(project, _graph=graph)['claims'] if c['id'] == item['id'])
    if any(not reason.startswith('REVALIDATION_REQUIRED:') for reason in current['invalidation_reasons']): return
    latch = item['revocation_latches'].pop(slot)
    graph['events'].append({'type': 'REVALIDATION_REVIEWED', 'id': item['id'], 'revision': item['revision'],
        'slot': slot, 'latch_sha256': latch['latch_sha256'], 'receipt_operation_id': receipt['operation_id'], 'at': stamp()})


def review(project, claim_id, kind, evidence_path, reviewer, reason):
    if kind == 'proof_and_statement':
        review(project, claim_id, 'proof', evidence_path, reviewer, reason)
        return review(project, claim_id, 'statement', evidence_path, reviewer, reason)
    text(reviewer, 'reviewer'); text(reason, 'review reason')
    graph = load(project); item = next((c for c in graph['claims'] if c['id'] == claim_id), None)
    if item is None: raise ValueError('Unknown claim')
    if not receipt_history_valid(item, graph.get('events')): raise ValueError('RECEIPT_HISTORY_INVALID: explicit audit recovery required')
    if reviewer.strip().casefold() == item['spec']['proposer'].strip().casefold():
        raise ValueError('Claim proposer cannot attest its own independent review')
    if kind not in {'proof', 'statement', 'novelty', 'formal_audit'}: raise ValueError('Invalid review kind')
    bindings = evidence(project, [evidence_path])
    receipt_sha = None
    if kind == 'novelty':
        report = read_object(local_file(project, evidence_path))
        if report.get('claim_id') != claim_id or report.get('claim_sha256') != item['spec_sha256']:
            raise ValueError('Novelty review must bind exact claim ID and spec_sha256')
        if report.get('verdict') != 'NEW_THEORETICAL_CONTRIBUTION': raise ValueError('Novelty is unresolved or covered')
        for field in ('nontriviality_argument', 'novelty_mechanism', 'search_scope'): text(report.get(field), field)
        paths = strings(report.get('technical_reviews'), 'technical_reviews')
        for rel in paths:
            technical = validate_technical_review(project, rel, claim_id)
            if technical.get('fulltext_status') != 'TECHNICALLY_CHECKED' or technical['coverage_verdict'] in {'COVERS', 'CONTRADICTS', 'UNVERIFIED'}:
                raise ValueError('Novelty requires full technical comparison without known coverage/conflict')
            refs = [rel, technical['paper']['source_file']] + technical.get('derivation_paths', [])
            bindings.update(evidence(project, refs))
    if kind == 'formal_audit':
        formal = item.get('formal_receipt')
        latches = _revocation_latches(item, graph['events'])
        if latches is None: raise ValueError('REVOCATION_HISTORY_INVALID: explicit audit recovery required')
        if 'tool:formal_receipt' in latches: raise ValueError('Formal tool revalidation needs a new tool receipt before audit')
        if not receipt_fresh(project, item, formal) or formal.get('status') != 'TOOL_PASSED_AUDIT_PENDING':
            raise ValueError('No current successful formal verifier receipt to audit')
        report = read_object(local_file(project, evidence_path))
        receipt_sha = object_hash(formal)
        if report.get('claim_id') != claim_id or report.get('receipt_sha256') != receipt_sha:
            raise ValueError('Formal audit must bind the exact verifier receipt')
        if report.get('verdict') != 'MATCHED_AND_AUDITED': raise ValueError('Formal statement/axioms audit not passed')
        for field in ('statement_mapping', 'axioms_argument', 'dependency_scope'): text(report.get(field), field)
        strings(report.get('allowed_axioms'), 'allowed_axioms', empty=True)
        if any('sorry' in a.casefold() for a in report['allowed_axioms']): raise ValueError('sorryAx is never allowed')
    receipt = {'reviewer': reviewer, 'reason': reason, 'at': stamp(),
        'claim_sha256': item['spec_sha256'], 'evidence': bindings, 'receipt_sha256': receipt_sha}
    audit = _append_receipt(item, 'review:' + kind, receipt)
    item['reviews'][kind] = receipt
    graph['events'].append({'type': 'INDEPENDENT_REVIEW', 'id': claim_id, 'kind': kind, 'reviewer': reviewer,
        'revision': item['revision'], 'claim_sha256': item['spec_sha256'], **_receipt_reference(audit), 'at': stamp()})
    _release_revalidation_scope(project, graph, item, 'review:' + kind, audit)
    save(project, graph)
    return refresh(project)


def invalidate(project, claim_id, reason):
    text(reason, 'invalidation reason')
    graph = load(project)
    item = next((c for c in graph['claims'] if c['id'] == claim_id), None)
    if item is None: raise ValueError('Unknown claim')
    item['invalidated'] = {'reason': reason, 'at': stamp()}
    graph['events'].append({'type': 'CLAIM_INVALIDATED', 'id': claim_id, 'reason': reason, 'at': stamp()})
    save(project, graph)
    return refresh(project)


def record_tool(project, claim_id, field, receipt):
    graph = load(project); item = next(c for c in graph['claims'] if c['id'] == claim_id)
    if not receipt_history_valid(item, graph.get('events')): raise ValueError('RECEIPT_HISTORY_INVALID: explicit audit recovery required')
    if field not in {'formal_receipt', 'counterexample_receipt'}: raise ValueError('Invalid tool receipt slot')
    if (receipt['claim_sha256'] != item['spec_sha256'] or type(receipt['claim_revision']) is not int
            or receipt['claim_revision'] != item['revision'] or receipt['claim_id'] != claim_id):
        raise ValueError('Claim changed during verification')
    audit = _append_receipt(item, 'tool:' + field, receipt)
    item[field] = copy.deepcopy(receipt)
    graph['events'].append({'type': 'TOOL_RESULT', 'id': claim_id, 'status': receipt['status'], 'field': field,
        'revision': item['revision'], 'claim_sha256': item['spec_sha256'], **_receipt_reference(audit), 'at': stamp()})
    if field == 'formal_receipt' and receipt.get('status') == 'TOOL_PASSED_AUDIT_PENDING' and receipt_fresh(project, item, receipt):
        _release_revalidation_scope(project, graph, item, 'tool:' + field, audit)
    save(project, graph)
    return refresh(project)


def require_theory_claim(project, claim_id):
    graph = load(project)
    if not graph['claims']:
        from .problem_compiler import pool
        if pool(project)['problems']: raise ValueError('Discovery problems exist but no independently reviewed claim is registered')
        return None
    current = status(project)['claims']
    item = next((c for c in current if c['id'] == claim_id), None)
    if item is None or not item['accepted_contribution']:
        raise ValueError('Discovery claim has not passed correctness, statement and theorem-level novelty review')
    problem = get_problem(project, item['problem_id'], item['problem_version'])
    covered = set()
    # Only declared dependencies of the approved claim can close its problem obligations.
    by_id = {c['id']: c for c in graph['claims']}; closure = set()
    def visit(cid):
        if cid in closure: return
        closure.add(cid)
        for dep in by_id[cid]['spec']['dependencies']: visit(dep)
    visit(claim_id)
    for candidate in current:
        if candidate['id'] in closure and candidate['proof_status'] == 'INDEPENDENTLY_REVIEWED' and candidate['problem_id'] == item['problem_id'] and candidate['problem_version'] == item['problem_version']:
            covered.update(candidate['obligation_ids'])
    if covered != {o['id'] for o in problem['spec']['obligations']}:
        raise ValueError('Critical problem obligations remain open in the approved claim dependency closure')
    return item
