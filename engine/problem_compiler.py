"""Compile explicit problem contracts; never infer that a theorem is proved."""
from __future__ import annotations
import copy
import configuration
from research_quality import CORE_TYPES
from .common import STORE, evidence, identifier, object_hash, strings, text, stamp


def pool(project):
    return configuration.load_json(project / STORE / 'PROBLEMS.json',
        {'schema_version': 1, 'problems': []})


def validate(spec):
    if not isinstance(spec, dict) or spec.get('schema_version') != 1:
        raise ValueError('Problem schema_version must be 1')
    identifier(spec.get('id'))
    for field in ('title', 'statement', 'quantifiers', 'domain', 'input_contract',
                  'output_contract', 'goal_connection', 'nontriviality_argument'):
        text(spec.get(field), field)
    for field in ('assumptions', 'immutable_constraints', 'baseline_exclusions'):
        strings(spec.get(field), field)
    if spec.get('contribution_type') not in CORE_TYPES:
        raise ValueError('Problem requires a theoretical contribution_type')
    obligations = spec.get('obligations')
    if not isinstance(obligations, list) or not obligations:
        raise ValueError('Problem needs explicit proof obligations')
    ids = set()
    for item in obligations:
        if not isinstance(item, dict): raise ValueError('Invalid obligation')
        oid = identifier(item.get('id'))
        if oid in ids: raise ValueError('Duplicate proof obligation')
        ids.add(oid)
        for key in ('statement', 'acceptance_criterion'): text(item.get(key), key)
    if 'priority' in spec and (type(spec['priority']) is not int or not 1 <= spec['priority'] <= 100):
        raise ValueError('Problem priority must be 1..100')
    strings(spec.get('source_paths', []), 'source_paths', empty=True)
    core = {k: spec[k] for k in ('title', 'statement', 'quantifiers', 'domain', 'input_contract',
            'output_contract', 'goal_connection', 'nontriviality_argument', 'assumptions',
            'immutable_constraints', 'baseline_exclusions', 'obligations')}
    if any(marker in str(core) for marker in ('填写', '待确认', 'UNCONFIRMED', '{{')):
        raise ValueError('Problem still contains template placeholders or unconfirmed core fields')
    if len(str(spec)) > 80000: raise ValueError('Problem contract exceeds 80 KB; cite detailed local evidence')
    return copy.deepcopy(spec)


def import_problem(project, spec, reason):
    spec = validate(spec)
    text(reason, 'revision reason')
    sources = evidence(project, spec.get('source_paths', []), empty=True)
    store = pool(project)
    item = next((p for p in store['problems'] if p['id'] == spec['id']), None)
    if item is None:
        item = {'id': spec['id'], 'revisions': []}
        store['problems'].append(item)
    digest = object_hash(spec)
    if item['revisions'] and item['revisions'][-1]['spec_sha256'] == digest:
        raise ValueError('Problem contract unchanged; do not create an artificial revision')
    revision = {'version': len(item['revisions']) + 1, 'spec': spec, 'spec_sha256': digest,
                'source_bindings': sources, 'goal_sha256': __import__('research_quality').hash_file(project / 'GOAL.md'),
                'created_at': stamp(), 'reason': reason}
    item['revisions'].append(revision)
    configuration.atomic_json(project / STORE / 'PROBLEMS.json', store)
    return revision


def get_problem(project, problem_id, version=None):
    identifier(problem_id)
    item = next((p for p in pool(project)['problems'] if p['id'] == problem_id), None)
    if item is None: raise ValueError('Unknown problem: ' + problem_id)
    revisions = item['revisions']
    record = next((r for r in revisions if r['version'] == version), None) if version else revisions[-1]
    if record is None: raise ValueError('Unknown problem revision')
    if object_hash(record['spec']) != record['spec_sha256']: raise ValueError('Problem contract digest mismatch')
    return record
