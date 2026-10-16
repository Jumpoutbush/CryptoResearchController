"""Atomic append-history catalog. It never imports problems or reserves budget."""
from __future__ import annotations
import copy
from pathlib import Path
import configuration
import research_focus
import route_budget
from engine.common import goal_binding, object_hash, text
from research_quality import hash_file, read_object
from . import model, validate


def _unlinked(path):
    from runner_core import project_link
    path = Path(path)
    for component in (path, *path.parents):
        if component.exists() and project_link(component):
            raise ValueError('Candidate store/project links are forbidden')
    return path


def _project(project):
    project = _unlinked(project).resolve()
    project.relative_to((configuration.ROOT / 'projects').resolve())
    key = configuration.project_id(project)
    if project != (configuration.ROOT / 'projects' / key).resolve():
        raise ValueError('Candidate project identity must match its registered project directory')
    validate.safe(project, 'PROJECT.json'); validate.safe(project, 'GOAL.md')
    return project, key


def path(project):
    _, key = _project(project)
    return _unlinked(configuration.ROOT / 'state/candidates' / key / 'catalog.json')


def anchor(project):
    project, key = _project(project)
    state = read_object(validate.safe(project, 'research/STATE.json'))
    route_path = _unlinked(configuration.ROOT / 'state/routes' / (key + '.json'))
    _unlinked(route_budget.registry_path(route_path))
    original = configuration.load_json(route_path)
    # load_ledger is deliberately read-only. Its high-water authority rejects a
    # lost/stale budget; its in-memory new epoch is never saved by this module.
    _, _, epoch = route_budget.load_ledger(configuration.ROOT, project, state)
    if original and original.get('epochs'):
        old = original['epochs'][-1]
        if old['route'] != route_budget.selected_route(state):
            raise ValueError('Candidate route changed; explicit existing refocus is required')
        if old.get('focus') and old['focus'] != epoch['focus']:
            raise ValueError('Candidate route focus changed; explicit refocus is required')
    focus = research_focus.require_current(project, epoch, state)
    if (not isinstance(focus, dict) or set(focus) != {'binding', 'core_problem', 'anchor_id'}
            or not isinstance(focus['core_problem'], str) or not focus['core_problem'].strip()
            or focus != research_focus.make_focus(project, state, focus['core_problem'])):
        raise ValueError('Existing route focus integrity is invalid; explicit audit is required')
    binding = goal_binding(project)
    for relative in binding['files']: validate.safe(project, relative)
    return {'project_id': key, 'goal_anchor_id': focus['anchor_id'],
            'goal_sha256': hash_file(project / 'GOAL.md'), 'goal_binding': binding,
            'route_epoch': epoch['epoch'],
            'project_manifest_sha256': hash_file(project / 'PROJECT.json')}


def _policy():
    policy_path = _unlinked(configuration.ROOT / 'config/candidate_policy.json')
    value = configuration.load_json(policy_path, {'schema_version': 1, 'max_active_candidates': 3})
    if (not isinstance(value, dict) or set(value) != {'schema_version', 'max_active_candidates'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or type(value['max_active_candidates']) is not int
            or not 1 <= value['max_active_candidates'] <= model.MAX_ACTIVE):
        raise ValueError('Candidate policy may only restrict the hard active limit to 1..3')
    return value


def _record_valid(record, key):
    if not isinstance(record, dict) or record.get('project_id') != key:
        raise ValueError('Candidate project mismatch')
    validate.positive_integer(record.get('revision'), 'candidate revision')
    validate.positive_integer(record.get('route_epoch'), 'route_epoch')
    if record.get('status') not in model.STATUSES: raise ValueError('Invalid candidate status')
    spec = record['spec']
    if record['id'] != spec['id'] or record['goal_anchor_id'] != spec['goal_anchor_id']:
        raise ValueError('Candidate identity changed')
    if record['spec_sha256'] != object_hash(spec): raise ValueError('Candidate spec digest changed')
    pb = record['problem_binding']
    if pb['spec_sha256'] != object_hash(pb['spec']): raise ValueError('Candidate problem snapshot changed')
    if record['semantic_sha256'] != model.semantic_key(spec, pb): raise ValueError('Candidate duplicate binding changed')
    if record['novelty_status'] != 'NOVELTY_PENDING': raise ValueError('Candidate cannot grant novelty approval')
    if type(record['conditional']) is not bool: raise ValueError('Invalid conditional marker')
    if record['conditional'] and record['status'] in model.ACTIVE_STATUSES:
        raise ValueError('Conditional candidate cannot become active')
    if record['status'] == 'ACTIVE': raise ValueError('ACTIVE requires a trusted attempt-owner event, unavailable in R11')
    if record['status'] in {'REFUTED', 'COVERED'}:
        disposition = record.get('disposition')
        if (not isinstance(disposition, dict) or set(disposition) != {
                'scope', 'restart_conditions', 'evidence_refs', 'evidence_bindings'}):
            raise ValueError('Rejected candidate history requires a scoped disposition')
        text(disposition['scope'], 'rejection scope'); text(disposition['restart_conditions'], 'restart conditions')
        from engine.common import strings
        strings(disposition['evidence_refs'], 'disposition evidence_refs', empty=True)
        bindings = disposition['evidence_bindings']
        import re
        if (not isinstance(bindings, dict) or set(bindings) != set(disposition['evidence_refs'])
                or any(not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha) for sha in bindings.values())):
            raise ValueError('Invalid historical disposition evidence pins')


def _tree(candidates):
    revisions = {(item['id'], r['revision']): r for item in candidates for r in item['revisions']}
    edges = {}
    for record in revisions.values():
        parent = record['spec'].get('parent')
        if parent:
            target = revisions.get((parent['id'], parent['revision']))
            if target is None: raise ValueError('Candidate parent revision is unavailable')
            if target['goal_anchor_id'] != record['goal_anchor_id']: raise ValueError('Parent crosses frozen goals')
            edges.setdefault(record['id'], set()).add(parent['id'])
    visiting = set(); complete = set()
    def visit(key):
        if key in visiting: raise ValueError('Candidate parent graph is cyclic')
        if key in complete: return
        visiting.add(key)
        for parent in edges.get(key, ()): visit(parent)
        visiting.remove(key); complete.add(key)
    for key in edges: visit(key)


def _validate_store(value, key):
    try:
        if (not isinstance(value, dict) or set(value) != {'schema_version', 'project_id', 'candidates', 'events'}
                or type(value['schema_version']) is not int or value['schema_version'] != 1
                or value['project_id'] != key or not isinstance(value['candidates'], list)
                or not isinstance(value['events'], list)):
            raise ValueError('Invalid candidate catalog envelope')
        if len(value['events']) > 20000: raise ValueError('Candidate catalog history limit exceeded')
        replay = []; by_id = {}; previous = None
        for seq, event in enumerate(value['events'], 1):
            unhashed = {k: v for k, v in event.items() if k != 'sha256'}
            if (type(event['sequence']) is not int or event['sequence'] != seq or event['previous_sha256'] != previous
                    or event['sha256'] != object_hash(unhashed)):
                raise ValueError('Candidate event history hash mismatch')
            text(event['reason'], 'event reason'); text(event['at'], 'event timestamp')
            record = copy.deepcopy(event['record']); _record_valid(record, key)
            cid = record['id']; current = by_id.get(cid)
            if event['type'] in {'PROPOSED', 'REVISED'}:
                expected = len(current['revisions']) + 1 if current else 1
                if record['revision'] != expected: raise ValueError('Candidate revision history gap')
                if event['type'] != ('REVISED' if current else 'PROPOSED'):
                    raise ValueError('Candidate history operation mismatch')
                if record['status'] != ('CONDITIONAL' if record['conditional'] else 'PROPOSED'):
                    raise ValueError('New candidate revision cannot start approved')
                if current is None:
                    current = {'id': cid, 'revisions': []}; by_id[cid] = current; replay.append(current)
                elif record['goal_anchor_id'] != current['revisions'][0]['goal_anchor_id']:
                    raise ValueError('Candidate revision cannot silently change frozen goal')
                current['revisions'].append(record)
            elif event['type'] == 'STATUS_CHANGED':
                if current is None or current['revisions'][-1]['revision'] != record['revision']:
                    raise ValueError('Candidate status addresses a noncurrent revision')
                old = current['revisions'][-1]
                immutable = lambda r: {k: v for k, v in r.items() if k not in {'status', 'disposition'}}
                if immutable(old) != immutable(record): raise ValueError('Status event rewrites candidate inputs')
                if old['status'] in model.TERMINAL_STATUSES:
                    raise ValueError('A rejected version cannot be reopened or overwritten')
                current['revisions'][-1] = record
            else: raise ValueError('Unknown candidate event operation')
            previous = event['sha256']
        if replay != value['candidates']: raise ValueError('Candidate materialization differs from immutable event history')
        if sum(c['revisions'][-1]['status'] in model.ACTIVE_STATUSES for c in replay) > model.MAX_ACTIVE:
            raise ValueError('Candidate catalog exceeds the hard active limit')
        _tree(replay)
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError('Corrupt candidate catalog history') from exc
    return value


def _load(project):
    _, key = _project(project)
    location = path(project)
    value = configuration.load_json(location, {'schema_version': 1, 'project_id': key,
                                              'candidates': [], 'events': []})
    return _validate_store(value, key)


def _view(project, record, current):
    value = copy.deepcopy(record)
    value['readiness_reasons'] = validate.ready_reasons(project, record, current)
    value['eligible_for_attempt'] = record['status'] == 'READY_FOR_ATTEMPT' and not value['readiness_reasons']
    value['scientific_status'] = 'UNREVIEWED_CANDIDATE' if record['status'] not in model.TERMINAL_STATUSES else record['status']
    value['duplicate_check_scope'] = 'CONSERVATIVE_NORMALIZED_EXACT_CONTENT_ONLY'
    value['positive_basis'] = False
    return value


def list_candidates(project):
    value = _load(project); current = anchor(project)
    return {'schema_version': 1, 'project_id': value['project_id'], 'anchor_id': current['goal_anchor_id'],
            'candidates': [_view(project, c['revisions'][-1], current) for c in value['candidates']],
            'event_count': len(value['events']),
            'history_sha256': value['events'][-1]['sha256'] if value['events'] else None}


def show(project, candidate_id, revision=None):
    from engine.common import identifier
    identifier(candidate_id)
    if revision is not None: validate.positive_integer(revision, 'candidate revision')
    value = _load(project)
    item = next((v for v in value['candidates'] if v['id'] == candidate_id), None)
    if item is None: raise ValueError('Unknown candidate ID')
    record = item['revisions'][-1] if revision is None else next(
        (r for r in item['revisions'] if r['revision'] == revision), None)
    if record is None: raise ValueError('Unknown candidate revision')
    return _view(project, record, anchor(project))


def _save(project, store, current):
    if anchor(project) != current: raise ValueError('Candidate frozen inputs changed during the transaction')
    _validate_store(store, current['project_id'])
    configuration.atomic_json(path(project), store)


def propose(project, spec, reason, *, revise=False, expected_revision=None):
    text(reason, 'candidate reason'); _policy()
    project, key = _project(project)
    lock = _unlinked(configuration.ROOT / 'locks' / ('candidates-' + key + '.lock'))
    with route_budget.file_lock(lock):
        current = anchor(project); store = _load(project)
        spec, binding, evidence, conditional = validate.validate_spec(project, spec, current)
        item = next((c for c in store['candidates'] if c['id'] == spec['id']), None)
        if item is not None and not revise: raise ValueError('Candidate exists; an explicit revision is required')
        if revise:
            if item is None: raise ValueError('Cannot revise an unknown candidate')
            if type(expected_revision) is not int or item['revisions'][-1]['revision'] != expected_revision:
                raise ValueError('Expected candidate revision conflict')
            if item['revisions'][0]['goal_anchor_id'] != current['goal_anchor_id']:
                raise ValueError('A candidate revision cannot change the frozen goal')
        elif expected_revision is not None: raise ValueError('expected_revision applies only to explicit revision')
        semantic = model.semantic_key(spec, binding)
        for existing in store['candidates']:
            for old in existing['revisions']:
                if old['goal_anchor_id'] == current['goal_anchor_id'] and old['semantic_sha256'] == semantic:
                    # Scientific and evidence pin changes warrant a new immutable
                    # revision; renaming a candidate never warrants a new route.
                    if existing['id'] != spec['id'] or object_hash(old['spec']) == object_hash(spec):
                        raise ValueError('DUPLICATE_CANDIDATE: normalized content already registered')
                    ignored = {'title', 'id', 'estimated_context_bytes'}
                    if {k: v for k, v in old['spec'].items() if k not in ignored} == {
                            k: v for k, v in spec.items() if k not in ignored}:
                        raise ValueError('DUPLICATE_CANDIDATE: renaming cannot create a new revision')
        record = {'project_id': key, 'id': spec['id'], 'revision': len(item['revisions']) + 1 if item else 1,
            'goal_anchor_id': current['goal_anchor_id'], 'goal_sha256': current['goal_sha256'],
            'goal_binding': copy.deepcopy(current['goal_binding']), 'route_epoch': current['route_epoch'],
            'project_manifest_sha256': current['project_manifest_sha256'],
            'spec': spec, 'spec_sha256': object_hash(spec), 'semantic_sha256': semantic,
            'problem_binding': binding, 'evidence_bindings': evidence, 'conditional': conditional,
            'status': 'CONDITIONAL' if conditional else 'PROPOSED', 'novelty_status': 'NOVELTY_PENDING',
            'created_at': route_budget.stamp(), 'reason': reason}
        if item is None:
            item = {'id': spec['id'], 'revisions': []}; store['candidates'].append(item)
        item['revisions'].append(record)
        store['events'].append(model.event(store['events'], 'REVISED' if revise else 'PROPOSED',
                                          record, reason, route_budget.stamp()))
        _tree(store['candidates'])
        # Recheck all newly pinned inputs immediately before the atomic replace.
        # This does not retroactively rewrite older immutable versions.
        if validate.problem(project, spec) != binding or validate.refs(project, spec['evidence_refs']) != evidence:
            raise ValueError('Candidate problem/evidence changed during registration')
        _save(project, store, current)
        return _view(project, record, current)


def transition(project, candidate_id, status, reason, *, expected_revision=None, disposition=None):
    text(reason, 'status reason'); project, key = _project(project); policy = _policy()
    if status not in model.STATUSES: raise ValueError('Invalid candidate status; scientific promotion is forbidden')
    if status == 'ACTIVE': raise ValueError('ACTIVE requires the original attempt owner; manual activation is forbidden')
    lock = _unlinked(configuration.ROOT / 'locks' / ('candidates-' + key + '.lock'))
    with route_budget.file_lock(lock):
        current = anchor(project); store = _load(project)
        item = next((c for c in store['candidates'] if c['id'] == candidate_id), None)
        if item is None: raise ValueError('Unknown candidate ID')
        old = item['revisions'][-1]
        if type(expected_revision) is not int or expected_revision != old['revision']:
            raise ValueError('Expected candidate revision conflict')
        if old['status'] in model.TERMINAL_STATUSES: raise ValueError('Rejected candidate revision is immutable')
        if old['status'] == status: raise ValueError('Candidate status is unchanged')
        if (old['goal_binding'] != current['goal_binding'] or old['goal_anchor_id'] != current['goal_anchor_id']
                or old['route_epoch'] != current['route_epoch']
                or old['project_manifest_sha256'] != current['project_manifest_sha256']):
            raise ValueError('Candidate frozen goal is stale')
        if old['conditional'] and status in model.ACTIVE_STATUSES:
            raise ValueError('CONDITIONAL model cannot become active without independent adjudication')
        if status in model.ACTIVE_STATUSES:
            count = sum(c['revisions'][-1]['status'] in model.ACTIVE_STATUSES
                        for c in store['candidates'] if c['id'] != candidate_id)
            if count >= policy['max_active_candidates']: raise ValueError('ACTIVE_LIMIT: retire another candidate first')
        if status == 'READY_FOR_ATTEMPT':
            reasons = validate.ready_reasons(project, old, current)
            if reasons: raise ValueError('; '.join(reasons))
        record = copy.deepcopy(old); record['status'] = status
        if status in {'REFUTED', 'COVERED'}:
            if not isinstance(disposition, dict) or set(disposition) != {'scope', 'restart_conditions', 'evidence_refs'}:
                raise ValueError('Rejection requires explicit scope, restart_conditions and evidence_refs')
            text(disposition['scope'], 'rejection scope'); text(disposition['restart_conditions'], 'restart_conditions')
            record['disposition'] = {**copy.deepcopy(disposition),
                                     'evidence_bindings': validate.refs(project, disposition['evidence_refs'])}
        elif disposition is not None: raise ValueError('Disposition is only for REFUTED/COVERED')
        item['revisions'][-1] = record
        store['events'].append(model.event(store['events'], 'STATUS_CHANGED', record, reason, route_budget.stamp()))
        _save(project, store, current)
        return _view(project, record, current)
