"""Validate frozen candidate inputs; this module never creates scientific receipts."""
from __future__ import annotations
import copy
import json
import math
import re
from pathlib import Path
import configuration
from engine import claim_graph, problem_compiler
from engine.common import _unlinked_file, fresh, goal_binding, identifier, object_hash, strings, text
from research_quality import hash_file, read_object
from . import model


def safe(project, relative, *, roots=None):
    if (not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative
            or any(p in {'..', '.'} for p in relative.split('/')) or '//' in relative):
        raise ValueError('Candidate paths must stay inside the selected project')
    return _unlinked_file(project, relative, roots=roots)


def refs(project, values):
    strings(values, 'evidence_refs', empty=True)
    from engine.common import evidence
    for relative in values: safe(project, relative, roots={'research', 'proofs', 'literature', 'experiments'})
    return evidence(project, values, empty=True)


def positive_integer(value, name):
    if type(value) is not int or value < 1: raise ValueError(name + ' must be a positive integer')


def problem(project, spec):
    fixed = 'problem_id' in spec or 'problem_version' in spec
    draft = 'problem_proposal_file' in spec
    if fixed == draft: raise ValueError('Pin one exact fixed problem or one draft proposal')
    if fixed:
        identifier(spec.get('problem_id')); positive_integer(spec.get('problem_version'), 'problem_version')
        safe(project, 'research/discovery/PROBLEMS.json')
        record = problem_compiler.get_problem(project, spec['problem_id'], spec['problem_version'])
        if record['goal_sha256'] != hash_file(safe(project, 'GOAL.md')):
            raise ValueError('Fixed problem GOAL binding changed')
        if not fresh(project, record['source_bindings']): raise ValueError('Fixed problem sources changed')
        return {'status': 'FIXED', 'id': spec['problem_id'], 'version': record['version'],
                'spec_sha256': record['spec_sha256'], 'spec': copy.deepcopy(record['spec']),
                'source_bindings': copy.deepcopy(record['source_bindings'])}
    path = safe(project, spec['problem_proposal_file'], roots={'research'})
    draft_spec = problem_compiler.validate(read_object(path))
    return {'status': 'DRAFT_PENDING', 'id': draft_spec['id'], 'version': None,
            'spec_sha256': object_hash(draft_spec), 'spec': draft_spec,
            'source_path': spec['problem_proposal_file'], 'source_sha256': hash_file(path)}


def validate_spec(project, spec, anchor):
    if not isinstance(spec, dict) or spec.get('schema_version') != 1 or type(spec.get('schema_version')) is not int:
        raise ValueError('Candidate schema_version must be 1')
    if set(spec) - model.FIELDS: raise ValueError('Candidate contains unsupported or authority fields')
    identifier(spec.get('id'))
    for key in ('title', 'hypothesis', 'nontriviality_argument', 'falsification_gate', 'domain',
                'quantifiers', 'failure_scope', 'restart_conditions'):
        text(spec.get(key), key)
    if spec.get('goal_anchor_id') != anchor['goal_anchor_id']:
        raise ValueError('Candidate must bind the current frozen goal anchor')
    if len(json.dumps(spec, ensure_ascii=False).encode('utf8')) > 80000:
        raise ValueError('Candidate contract exceeds 80 KB')
    positive_integer(spec.get('estimated_context_bytes'), 'estimated_context_bytes')
    for key in ('assumptions', 'immutable_constraints', 'proof_obligations'):
        strings(spec.get(key), key)
        if len(spec[key]) != len(set(spec[key])): raise ValueError('Duplicate ' + key)
    for oid in spec['proof_obligations']: identifier(oid)
    security = spec.get('security_model')
    if not isinstance(security, dict): raise ValueError('security_model must be an explicit object')
    for key, value in security.items():
        identifier(key)
        if not ((isinstance(value, str) and value.strip()) or type(value) in {int, float}):
            raise ValueError('Security dimensions must be exact nonempty text or numeric values')
        if type(value) is float and not math.isfinite(value):
            raise ValueError('Security numeric dimensions must be finite')
    prior = spec.get('closest_prior_work')
    if not isinstance(prior, list) or not prior: raise ValueError('Nearest original work/check is required')
    for work in prior:
        if not isinstance(work, dict) or set(work) != {'source_id', 'check', 'full_text_checked'}:
            raise ValueError('Prior work requires source_id, check and full_text_checked')
        identifier(work['source_id']); text(work['check'], 'prior-work check')
        if type(work['full_text_checked']) is not bool: raise ValueError('full_text_checked must be boolean')
    deps = spec.get('dependency_claims')
    if not isinstance(deps, list): raise ValueError('dependency_claims must be explicit')
    seen = set()
    for pin in deps:
        if not isinstance(pin, dict) or set(pin) != {'id', 'revision', 'spec_sha256'}:
            raise ValueError('Dependency requires exact id/revision/spec_sha256')
        identifier(pin['id']); positive_integer(pin['revision'], 'dependency revision')
        if not isinstance(pin['spec_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', pin['spec_sha256']):
            raise ValueError('Invalid dependency SHA-256')
        if pin['id'] in seen: raise ValueError('Duplicate dependency claim')
        seen.add(pin['id'])
    parent = spec.get('parent')
    if parent is not None:
        if not isinstance(parent, dict) or set(parent) != {'id', 'revision'}: raise ValueError('Invalid parent pin')
        identifier(parent['id']); positive_integer(parent['revision'], 'parent revision')
    binding = problem(project, spec); baseline = binding['spec']
    for key in ('assumptions', 'immutable_constraints'):
        if not set(baseline[key]) <= set(spec[key]):
            raise ValueError('Frozen problem ' + key + ' cannot be reduced')
    for key in ('domain', 'quantifiers'):
        if spec[key] != baseline[key]: raise ValueError('Frozen problem ' + key + ' cannot change')
    if set(spec['proof_obligations']) != {o['id'] for o in baseline['obligations']}:
        raise ValueError('Candidate must retain all fixed proof obligations')
    old_security = baseline.get('security_model', {})
    for name, value in old_security.items():
        if 'corruption' in name.casefold() and 'threshold' in name.casefold():
            proposed = security.get(name)
            if proposed != value:
                raise ValueError('Frozen corruption threshold cannot be reduced or silently changed')
    conditional = (security != old_security or set(spec['assumptions']) != set(baseline['assumptions'])
                   or set(spec['immutable_constraints']) != set(baseline['immutable_constraints']))
    return copy.deepcopy(spec), binding, refs(project, spec.get('evidence_refs')), conditional


def ready_reasons(project, record, current_anchor):
    reasons = []
    if record['goal_binding'] != current_anchor['goal_binding'] or record['goal_anchor_id'] != current_anchor['goal_anchor_id']:
        reasons.append('FROZEN_GOAL_CHANGED')
    if record['project_manifest_sha256'] != current_anchor['project_manifest_sha256']:
        reasons.append('PROJECT_IDENTITY_CHANGED')
    if record['route_epoch'] != current_anchor['route_epoch']:
        reasons.append('ROUTE_EPOCH_CHANGED')
    if record['conditional']: reasons.append('CONDITIONAL_MODEL_REQUIRES_INDEPENDENT_ADJUDICATION')
    binding = record['problem_binding']
    if binding['status'] != 'FIXED': reasons.append('A fixed problem import is required before an attempt')
    else:
        try:
            now = problem(project, record['spec'])
            if now != binding: reasons.append('FIXED_PROBLEM_CHANGED')
        except (ValueError, OSError, KeyError): reasons.append('FIXED_PROBLEM_UNAVAILABLE')
    if not fresh(project, record['evidence_bindings']): reasons.append('CANDIDATE_EVIDENCE_CHANGED')
    pins = record['spec']['dependency_claims']
    if pins:
        try:
            safe(project, 'research/discovery/CLAIM_GRAPH.json')
            statuses = {v['id']: v for v in claim_graph.status(project)['claims']}
            for pin in pins:
                item = statuses.get(pin['id'], {})
                if any(item.get(key) != pin[key] for key in ('revision', 'spec_sha256')):
                    reasons.append('DEPENDENCY_PIN_CHANGED:' + pin['id'])
                if item.get('proof_status') != 'INDEPENDENTLY_REVIEWED':
                    reasons.append('DEPENDENCY_NOT_INDEPENDENTLY_REVIEWED:' + pin['id'])
        except (ValueError, OSError, KeyError, TypeError): reasons.append('DEPENDENCY_GRAPH_UNAVAILABLE')
    return reasons
