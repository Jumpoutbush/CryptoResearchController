"""Source-bound research memory, extending the existing CLAIM_GRAPH store.

Canonical claims and their scientific review gates remain in claim_graph.py.
Memory records describe sources and dependencies; they never certify a theorem.
Read operations build an ephemeral source view. Only explicit imports/refreshes
persist versions, using one atomic write to the original graph file.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path, PurePosixPath
import re

import configuration
from research_quality import hash_file
from .common import STORE, identifier, object_hash, stamp, text

KINDS = {'paper', 'theorem', 'evidence', 'failed_path', 'obligation'}
ROOTS = {'research', 'proofs', 'literature', 'experiments', 'inputs', 'reports', 'ideas'}
CONTROL = {'state.json', 'round_review.json', 'route_signal.json', 'route_verdict.json',
           'route_directive.md', 'run_result.json', 'checkpoint.json', 'theory_readiness.json',
           'queries.json', 'supervision_report.md'}
NOTE = ('Source bindings and declared locations are provenance, not independent proof, '
        'novelty, security verification, or discharge of a research obligation.')


def _safe(project, relative, *, source=False):
    if not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative:
        raise ValueError('Knowledge sources require project-relative forward-slash paths')
    parts = PurePosixPath(relative).parts
    if not parts or PurePosixPath(relative).is_absolute() or any(p in {'', '.', '..'} for p in relative.split('/')):
        raise ValueError('Invalid knowledge source path')
    from runner_core import project_link
    path = Path(project).resolve()
    for part in parts:
        path = path / part
        if project_link(path): raise ValueError('Knowledge paths cannot use symlinks or junctions')
    path.resolve().relative_to(Path(project).resolve())
    if source:
        lowered = relative.casefold()
        if (parts[0].casefold() not in ROOTS or path.name.casefold() in CONTROL
                or lowered.startswith(STORE.casefold() + '/')
                or lowered.startswith('research/supervision/') or '_upgrade_proposals' in lowered.split('/')):
            raise ValueError('Controller records cannot serve as knowledge evidence')
        if not path.is_file() or path.stat().st_size == 0: raise ValueError('Knowledge source missing or empty: ' + relative)
    return path


def _load(project):
    _safe(project, STORE + '/CLAIM_GRAPH.json')
    from .claim_graph import load
    graph = load(Path(project))
    if (not isinstance(graph, dict) or type(graph.get('schema_version')) is not int
            or graph['schema_version'] != 1 or not isinstance(graph.get('claims'), list) or not isinstance(graph.get('events'), list)):
        raise ValueError('Invalid canonical claim graph')
    _memory(graph)
    return graph


def _memory(graph):
    memory = graph.get('memory', {'schema_version': 1, 'nodes': [], 'events': []})
    if (not isinstance(memory, dict) or type(memory.get('schema_version')) is not int or memory['schema_version'] != 1
            or not isinstance(memory.get('nodes'), list) or not isinstance(memory.get('events'), list)):
        raise ValueError('Invalid research memory extension')
    seen = set()
    for node in memory['nodes']:
        if not isinstance(node, dict): raise ValueError('Invalid knowledge node')
        key = identifier(node.get('id'))
        if key in seen: raise ValueError('Duplicate knowledge node ID')
        seen.add(key)
        revision, history = node.get('revision'), node.get('history')
        if (type(revision) is not int or revision < 1 or not isinstance(history, list)
                or len(history) != revision - 1
                or any(not isinstance(old, dict) or type(old.get('revision')) is not int
                       or old['revision'] != index or old.get('id') != key
                       for index, old in enumerate(history, 1))):
            raise ValueError('Knowledge revision history is incomplete or malformed')
    return memory


def _provenance(node):
    return object_hash({key: node.get(key) for key in
        ('id', 'revision', 'invalidated', 'source_bindings', 'sources', 'dependency_pins', 'goal_sha256')})


def _integrity_reasons(node):
    reasons = []
    if type(node.get('revision')) is not int or node['revision'] < 1: reasons.append('RECORD_REVISION_INVALID')
    if node.get('id') != node['spec'].get('id'): reasons.append('RECORD_ID_MISMATCH')
    if object_hash(node['spec']) != node.get('spec_sha256'): reasons.append('RECORD_DIGEST_CHANGED')
    if node.get('provenance_sha256') != _provenance(node): reasons.append('PROVENANCE_DIGEST_CHANGED')
    return reasons


def _pointer(value, pointer):
    if pointer == '': return value
    if not pointer.startswith('/'): raise ValueError('JSON locator must be a JSON pointer')
    for token in pointer[1:].split('/'):
        if re.search(r'~(?![01])', token): raise ValueError('Invalid JSON pointer escape')
        token = token.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', token) or int(token) >= len(value): raise ValueError('JSON locator entry missing')
            value = value[int(token)]
        elif isinstance(value, dict) and token in value: value = value[token]
        else: raise ValueError('JSON locator entry missing')
    return value


def _location(path, locator):
    if not isinstance(locator, str) or not locator.strip() or len(locator) > 2000 or '\x00' in locator:
        raise ValueError('Knowledge source requires a bounded nonempty locator')
    if locator.startswith('lines:'):
        match = re.fullmatch(r'lines:([1-9][0-9]*)(?:-([1-9][0-9]*))?', locator)
        if not match: raise ValueError('Invalid line locator')
        lines = path.read_text(encoding='utf-8-sig').splitlines()
        start, end = int(match[1]), int(match[2] or match[1])
        if start > end or end > len(lines): raise ValueError('Line locator is outside the source')
        excerpt = '\n'.join(lines[start - 1:end])
        return 'LOCATION_CHECKED', object_hash(excerpt), excerpt[:4000]
    if locator.startswith('json:'):
        value = _pointer(configuration.load_json(path), locator[5:])
        return 'LOCATION_CHECKED', object_hash(value), json.dumps(value, ensure_ascii=False)[:4000]
    if locator.startswith('page:') and not re.match(r'^page:[1-9][0-9]*(?:$|[; ,])', locator):
        raise ValueError('Invalid declared page locator')
    return 'LOCATOR_DECLARED_NOT_VERIFIED', None, ''


def _bind(project, sources):
    if not isinstance(sources, list) or not 1 <= len(sources) <= 100: raise ValueError('Knowledge sources must be a bounded nonempty list')
    bindings, refs = {}, []
    for ref in sources:
        if not isinstance(ref, dict) or set(ref) - {'path', 'locator', 'sha256'} or not {'path', 'locator'} <= set(ref):
            raise ValueError('Invalid knowledge source fields')
        path = _safe(project, ref['path'], source=True)
        digest = hash_file(path)
        if 'sha256' in ref and ref['sha256'] != digest: raise ValueError('Knowledge source SHA256 mismatch')
        state, location_hash, excerpt = _location(path, ref['locator'])
        if hash_file(path) != digest: raise ValueError('Source changed while binding its location')
        bindings[ref['path']] = digest
        refs.append({'path': ref['path'], 'locator': ref['locator'], 'sha256': digest,
                     'locator_status': state, 'location_sha256': location_hash, 'excerpt': excerpt})
    return bindings, refs


def _validate_spec(spec):
    required = {'schema_version', 'id', 'kind', 'title', 'statement', 'sources'}
    optional = {'dependencies', 'claim_ids', 'assumptions', 'metadata', 'external_url'}
    if not isinstance(spec, dict) or not required <= set(spec) or set(spec) - required - optional:
        raise ValueError('Invalid knowledge record fields')
    if type(spec['schema_version']) is not int or spec['schema_version'] != 1: raise ValueError('Knowledge schema_version must be 1')
    identifier(spec['id'])
    if spec['kind'] not in KINDS: raise ValueError('Unsupported knowledge node kind')
    for field in ('title', 'statement'):
        text(spec[field], field)
        if len(spec[field]) > 30000: raise ValueError('Knowledge text is too large')
    for field in ('dependencies', 'claim_ids', 'assumptions'):
        values = spec.get(field, [])
        if not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values):
            raise ValueError(field + ' must be an array of strings')
        if len(values) != len(set(values)): raise ValueError('Duplicate knowledge ' + field)
        if field != 'assumptions':
            for value in values: identifier(value)
    if 'metadata' in spec and not isinstance(spec['metadata'], dict): raise ValueError('Knowledge metadata must be an object')
    if 'external_url' in spec:
        from urllib.parse import urlparse
        if not isinstance(spec['external_url'], str) or urlparse(spec['external_url']).scheme not in {'https', 'http'}:
            raise ValueError('External source URL must use HTTP(S); no network request is performed')
    if len(json.dumps(spec, ensure_ascii=False)) > 200000: raise ValueError('Knowledge record exceeds 200 KB')
    return copy.deepcopy(spec)


def _states(project, graph):
    nodes = {n['id']: n for n in _memory(graph)['nodes']}
    results, visiting, digests = {}, set(), {}
    goal = hash_file(Path(project) / 'GOAL.md')
    def compute(key):
        if key in results: return results[key]
        if key in visiting: raise ValueError('Knowledge dependencies must be acyclic')
        visiting.add(key)
        node = nodes[key]; reasons = _integrity_reasons(node)
        if node.get('invalidated'): reasons.append('EXPLICITLY_INVALIDATED:' + node['invalidated']['reason'])
        if node.get('goal_sha256') != goal: reasons.append('GOAL_CHANGED')
        bindings = node.get('source_bindings')
        expected = node['spec'].get('sources', [])
        refs = node.get('sources', [])
        if (not isinstance(expected, list) or not isinstance(refs, list) or len(expected) != len(refs)
                or not isinstance(bindings, dict) or set(bindings) != {s.get('path') for s in expected if isinstance(s, dict)}
                or any(not isinstance(a, dict) or not isinstance(b, dict)
                       or a.get('path') != b.get('path') or a.get('locator') != b.get('locator')
                       or b.get('sha256') != bindings.get(a.get('path'))
                       or ('sha256' in a and a['sha256'] != b.get('sha256'))
                       for a, b in zip(expected, refs))):
            reasons.append('SOURCE_BINDING_MISMATCH')
        for missing in node['spec'].get('metadata', {}).get('missing_dependencies', []):
            reasons.append('INDEX_SOURCE_MISSING:' + str(missing))
        if not isinstance(bindings, dict) or not bindings: reasons.append('SOURCE_BINDINGS_MISSING')
        else:
            for relative, digest in bindings.items():
                try:
                    if relative not in digests: digests[relative] = hash_file(_safe(project, relative, source=True))
                    if digests[relative] != digest: reasons.append('SOURCE_CHANGED:' + relative)
                except (OSError, ValueError): reasons.append('SOURCE_UNAVAILABLE:' + relative)
        pins = node.get('dependency_pins', {})
        if not isinstance(pins, dict) or set(pins) != set(node['spec'].get('dependencies', [])):
            reasons.append('DEPENDENCY_BINDING_INVALID'); pins = pins if isinstance(pins, dict) else {}
        for dep, pin in pins.items():
            if dep not in nodes: reasons.append('DEPENDENCY_MISSING:' + dep); continue
            parent = nodes[dep]
            if pin != {'revision': parent['revision'], 'spec_sha256': parent['spec_sha256']}:
                reasons.append('DEPENDENCY_REVISED:' + dep)
            if compute(dep)['validity'] != 'SOURCE_BOUND': reasons.append('DEPENDENCY_NOT_VALID:' + dep)
        result = {'id': key, 'key': 'memory:' + key, 'kind': node['spec']['kind'],
                  'title': node['spec']['title'], 'statement': node['spec']['statement'],
                  'revision': node['revision'], 'spec_sha256': node['spec_sha256'],
                  'validity': 'PENDING_REVALIDATION' if reasons else 'SOURCE_BOUND',
                  'verification_status': 'UNVERIFIED_SOURCE', 'invalidation_reasons': reasons,
                  'sources': copy.deepcopy(node.get('sources', [])),
                  'source_bindings': copy.deepcopy(bindings), 'metadata': copy.deepcopy(node['spec'].get('metadata', {})),
                  'persisted': node.get('origin') != 'ephemeral_index'}
        results[key] = result; visiting.remove(key)
        return result
    for key in nodes: compute(key)
    return results


def pin_dependencies(project, ids):
    if not isinstance(ids, list) or len(ids) != len(set(ids)): raise ValueError('Knowledge dependencies require unique node IDs')
    for key in ids: identifier(key)
    graph = _load(project)
    return _pins(project, graph, ids)


def _pins(project, graph, ids, *, require_valid=True):
    nodes = {n['id']: n for n in _memory(graph)['nodes']}
    states = _states(project, graph) if ids and require_valid else {}
    pins = {}
    for key in ids:
        if key not in nodes: raise ValueError('Unknown knowledge dependency; import or refresh first: ' + key)
        if require_valid and states[key]['validity'] != 'SOURCE_BOUND': raise ValueError('Knowledge dependency needs revalidation: ' + key)
        pins[key] = {'revision': nodes[key]['revision'], 'spec_sha256': nodes[key]['spec_sha256']}
    return pins


def dependency_reasons(project, pins, graph=None):
    if not isinstance(pins, dict): return ['KNOWLEDGE_BINDING_INVALID']
    graph = _load(project) if graph is None else graph
    states = _states(project, graph)
    reasons = []
    for key, pin in pins.items():
        current = states.get(key)
        if current is None: reasons.append('KNOWLEDGE_MISSING:' + key); continue
        if pin != {'revision': current['revision'], 'spec_sha256': current['spec_sha256']}:
            reasons.append('KNOWLEDGE_REVISED:' + key)
        if current['validity'] != 'SOURCE_BOUND': reasons.append('KNOWLEDGE_NOT_VALID:' + key)
    return reasons


def _upsert(project, graph, spec, reason, *, automatic=False, ephemeral=False):
    spec = _validate_spec(spec)
    memory = graph.setdefault('memory', {'schema_version': 1, 'nodes': [], 'events': []})
    nodes = {n['id']: n for n in memory['nodes']}
    old = nodes.get(spec['id'])
    if automatic and old and old.get('origin') not in {'auto_index', 'ephemeral_index'}: return old
    if spec['id'].startswith('AUTO-') and not automatic and old is None: raise ValueError('AUTO- IDs are reserved for indexed sources')
    if spec['id'] in spec.get('dependencies', []): raise ValueError('Knowledge dependency cycle')
    proposed = {n['id']: n['spec'].get('dependencies', []) for n in memory['nodes']}
    proposed[spec['id']] = spec.get('dependencies', [])
    done, visiting = set(), set()
    def visit(key):
        if key in visiting: raise ValueError('Knowledge dependencies must be acyclic')
        if key in done: return
        if key not in proposed: raise ValueError('Unknown knowledge dependency: ' + key)
        visiting.add(key)
        for dep in proposed[key]: visit(dep)
        visiting.remove(key); done.add(key)
    for key in proposed: visit(key)
    claims = {c['id'] for c in graph['claims']}
    if not set(spec.get('claim_ids', [])) <= claims: raise ValueError('Unknown canonical claim association')
    bindings, refs = _bind(project, spec['sources'])
    pins = _pins(project, graph, spec.get('dependencies', []), require_valid=not automatic)
    digest, goal = object_hash(spec), hash_file(Path(project) / 'GOAL.md')
    unchanged = bool(old and old['spec_sha256'] == digest and old['spec'] == spec
                     and old['source_bindings'] == bindings and old.get('sources') == refs
                     and old['dependency_pins'] == pins and old['goal_sha256'] == goal
                     and not _integrity_reasons(old))
    if unchanged and (not old.get('invalidated') or automatic): return old
    node = {'id': spec['id'], 'revision': old['revision'] + 1 if old else 1,
            'spec': spec, 'spec_sha256': digest, 'source_bindings': bindings, 'sources': refs,
            'dependency_pins': pins, 'goal_sha256': goal,
            'origin': 'ephemeral_index' if ephemeral else 'auto_index' if automatic else 'manual',
            'invalidated': copy.deepcopy(old.get('invalidated')) if old and automatic else None,
            'registered_at': stamp(), 'reason': reason,
            'history': (old.get('history', []) + [{k: copy.deepcopy(v) for k, v in old.items() if k != 'history'}]) if old else []}
    node['provenance_sha256'] = _provenance(node)
    if old: memory['nodes'][memory['nodes'].index(old)] = node
    else: memory['nodes'].append(node)
    memory['events'].append({'type': 'NODE_REVISED' if old else 'NODE_IMPORTED',
                             'id': node['id'], 'revision': node['revision'], 'reason': reason, 'at': stamp()})
    return node


def import_record(project, spec, reason):
    text(reason, 'knowledge import reason')
    graph = _load(project); before = copy.deepcopy(graph)
    node = _upsert(project, graph, spec, reason)
    if graph != before: configuration.atomic_json(_safe(project, STORE + '/CLAIM_GRAPH.json'), graph)
    return copy.deepcopy(node)


def _auto_id(key):
    return 'AUTO-' + object_hash(key)[:24]


def _indexed(project):
    """Index declarations, retaining original full-text and verification caveats."""
    from runner_core import project_files
    records, errors = [], []
    suffixes = {'.md', '.json', '.txt', '.py', '.csv', '.tsv', '.tex', '.bib', '.lean', '.sage', '.pdf',
                '.html', '.htm', '.png', '.jpg', '.jpeg', '.webp', '.svg', '.log', '.yaml', '.yml'}
    registries = {'seed_papers.json': ('papers', 'paper'), 'catalog.json': ('items', 'paper'),
                  'seed_sources.json': ('sources', 'paper'), 'claim_index.json': ('claims', 'theorem'),
                  'claim_register.json': ('claims', 'theorem'), 'proof_obligations.json': ('obligations', 'obligation'),
                  'evidence.json': ('items', 'evidence')}
    for path in project_files(Path(project).resolve()):
        relative = path.relative_to(Path(project).resolve()).as_posix()
        if path.suffix.lower() not in suffixes: continue
        try: _safe(project, relative, source=True)
        except ValueError: continue
        if len(records) >= 5000:
            errors.append('Index capped at 5,000 records; use explicit imports for additional sources'); break
        digest = hash_file(path)
        kind = 'failed_path' if path.name.casefold() in {'failed_paths.md', 'failed_routes.md'} else 'evidence'
        source = {'path': relative, 'locator': 'whole-file; content not independently verified', 'sha256': digest}
        file_id = _auto_id([relative, 'file'])
        spec = {'schema_version': 1, 'id': file_id, 'kind': kind, 'title': relative,
                'statement': 'Local source indexed for retrieval; scientific content is not independently verified.',
                'sources': [source], 'dependencies': [],
                'metadata': {'source_path': relative, 'index_role': 'source_file', 'original_verification': 'UNVERIFIED'}}
        data = None
        if path.suffix.lower() == '.json' and path.stat().st_size <= 1_000_000:
            try:
                data = configuration.load_json(path)
                if isinstance(data, dict):
                    spec['metadata']['source_caveats'] = {k: copy.deepcopy(v) for k, v in data.items()
                        if k in {'hash_scope', 'scope', 'binary_available', 'pdf_binary_sha256', 'read_depth',
                                 'full_text_status', 'full_text_verified', 'warning', 'note'}}
            except (ValueError, OSError) as exc: errors.append(relative + ': ' + str(exc))
        records.append(spec)
        registry = registries.get(path.name.casefold())
        if registry and isinstance(data, dict) and isinstance(data.get(registry[0]), list):
            field, row_kind = registry
            for index, row in enumerate(data[field]):
                if not isinstance(row, dict): continue
                row_id = str(row.get('id', row.get('doi', index)))
                title = str(row.get('title') or row.get('name') or row.get('claim') or row_id)
                statement = str(row.get('statement') or row.get('claim') or row.get('description') or title)
                records.append({'schema_version': 1, 'id': _auto_id([relative, field, row_id]), 'kind': row_kind,
                    'title': title[:30000], 'statement': statement[:30000],
                    'sources': [{'path': relative, 'locator': f'json:/{field}/{index}', 'sha256': digest}],
                    'dependencies': [file_id], 'metadata': {'original_id': row_id, 'source_path': relative,
                        'index_role': 'registry_entry', 'original_record': copy.deepcopy(row),
                        'registry_field': field, 'declared_status_only': True}})
        if kind == 'failed_path' and path.stat().st_size <= 1_000_000:
            lines = path.read_text(encoding='utf-8-sig').splitlines()
            headings = [(i, re.sub(r'^#{1,6}\s+', '', line).strip()) for i, line in enumerate(lines) if re.match(r'^#{1,6}\s+', line)]
            for index, (start, title) in enumerate(headings):
                end = headings[index + 1][0] if index + 1 < len(headings) else len(lines)
                records.append({'schema_version': 1, 'id': _auto_id([relative, 'section', index]), 'kind': 'failed_path',
                    'title': title, 'statement': '\n'.join(lines[start:end])[:30000],
                    'sources': [{'path': relative, 'locator': f'lines:{start + 1}-{end}', 'sha256': digest}],
                    'dependencies': [file_id], 'metadata': {'source_path': relative,
                        'index_role': 'failed_path_section', 'scope': 'Recorded local boundary only; not a refutation of the frozen goal'}})
    from .knowledge_links import link_records
    records, linking_errors = link_records(records)
    return records, errors + linking_errors


def _view(project, *, dynamic=True):
    graph = _load(project)
    errors = []
    if dynamic:
        indexed, errors = _indexed(project)
        stored = {n['id'] for n in _memory(graph)['nodes']}
        for spec in indexed:
            # Stored versions are never rebound by a read. Changed or removed
            # sources stay stale until an explicit refresh/import creates a revision.
            if spec['id'] not in stored:
                _upsert(project, graph, spec, 'Ephemeral read-only source index', automatic=True, ephemeral=True)
    states = _states(project, graph)
    from .claim_graph import status as claim_status
    canonical = claim_status(Path(project))['claims']
    claims = [{'key': 'claim:' + c['id'], 'kind': 'claim', **c} for c in canonical]
    raw_claims = {c['id']: c for c in graph['claims']}
    nodes = list(states.values()) + claims
    edges, sources = [], {}
    for node in _memory(graph)['nodes']:
        key = 'memory:' + node['id']
        for dep, pin in node.get('dependency_pins', {}).items():
            edges.append({'from': key, 'to': 'memory:' + dep, 'relation': 'depends_on', 'pin': copy.deepcopy(pin)})
        for cid in node['spec'].get('claim_ids', []):
            edges.append({'from': key, 'to': 'claim:' + cid, 'relation': 'associated_with'})
        for relation in node['spec'].get('metadata', {}).get('related_nodes', []):
            edges.append({'from': key, 'to': 'memory:' + relation['target'], 'relation': relation['relation']})
        for ref in node.get('sources', []):
            uid = 'source:' + object_hash([ref['path'], ref['locator'], ref['sha256']])[:24]
            sources[uid] = {'key': uid, 'id': uid, 'kind': 'source', 'title': ref['path'], **copy.deepcopy(ref),
                            'verification_status': 'UNVERIFIED_SOURCE'}
            edges.append({'from': key, 'to': uid, 'relation': 'cites'})
    for cid, claim in raw_claims.items():
        for dep, pin in claim.get('dependency_pins', {}).items():
            edges.append({'from': 'claim:' + cid, 'to': 'claim:' + dep, 'relation': 'depends_on', 'pin': copy.deepcopy(pin)})
        for dep, pin in (claim.get('knowledge_pins') or {}).items():
            edges.append({'from': 'claim:' + cid, 'to': 'memory:' + dep, 'relation': 'depends_on', 'pin': copy.deepcopy(pin)})
        references = [(relative, digest, 'claim evidence') for relative, digest in claim.get('evidence', {}).items()]
        for kind, review in claim.get('reviews', {}).items():
            references += [(relative, digest, 'independent ' + kind + ' review source')
                           for relative, digest in review.get('evidence', {}).items()]
        for relative, digest, scope in references:
            uid = 'source:' + object_hash([relative, scope, digest])[:24]
            sources[uid] = {'key': uid, 'id': uid, 'kind': 'source', 'title': relative,
                            'path': relative, 'sha256': digest, 'locator': scope + ' (see original review)',
                            'verification_status': 'REVIEW_SCOPE_IN_CANONICAL_CLAIM'}
            edges.append({'from': 'claim:' + cid, 'to': uid, 'relation': 'cites'})
    # Problem obligations are projections of the existing compiler registry,
    # never a second mutable obligation table or an automatic discharge.
    from .problem_compiler import pool
    from .common import fresh
    for problem_index, problem in enumerate(pool(Path(project))['problems']):
        for index, revision in enumerate(problem['revisions']):
            reasons = []
            if object_hash(revision['spec']) != revision['spec_sha256']: reasons.append('PROBLEM_DIGEST_CHANGED')
            if revision['goal_sha256'] != hash_file(Path(project) / 'GOAL.md'): reasons.append('GOAL_CHANGED')
            if not fresh(Path(project), revision['source_bindings']): reasons.append('PROBLEM_SOURCE_CHANGED')
            for obligation in revision['spec']['obligations']:
                uid = 'obligation:' + problem['id'] + '@' + str(revision['version']) + ':' + obligation['id']
                nodes.append({'key': uid, 'id': obligation['id'], 'kind': 'obligation',
                    'title': obligation['id'], 'statement': obligation['statement'],
                    'acceptance_criterion': obligation['acceptance_criterion'],
                    'problem_id': problem['id'], 'problem_version': revision['version'],
                    'validity': 'PENDING_REVALIDATION' if reasons else 'SOURCE_BOUND',
                    'invalidation_reasons': reasons,
                    'registry_path': STORE + '/PROBLEMS.json',
                    'registry_locator': f'json:/problems/{problem_index}/revisions/{index}/spec/obligations',
                    'goal_sha256': revision['goal_sha256'],
                    'verification_status': 'UNVERIFIED_SOURCE', 'source_bindings': copy.deepcopy(revision['source_bindings'])})
                for relative, digest in revision['source_bindings'].items():
                    source_id = 'source:' + object_hash([relative, 'compiled problem source', digest])[:24]
                    sources[source_id] = {'key': source_id, 'id': source_id, 'kind': 'source',
                        'title': relative, 'path': relative, 'sha256': digest,
                        'locator': 'Compiled problem source; see original problem contract',
                        'verification_status': 'UNVERIFIED_SOURCE'}
                    edges.append({'from': uid, 'to': source_id, 'relation': 'cites'})
                for cid, claim in raw_claims.items():
                    if (claim['spec']['problem_id'] == problem['id'] and claim['spec']['problem_version'] == revision['version']
                            and obligation['id'] in claim['spec']['obligation_ids']):
                        edges.append({'from': 'claim:' + cid, 'to': uid, 'relation': 'addresses'})
    nodes += list(sources.values())
    return graph, {'schema_version': 1, 'memory_nodes': list(states.values()), 'claim_nodes': claims,
                   'nodes': nodes, 'edges': edges, 'index_errors': errors, 'note': NOTE}


def status(project):
    return _view(Path(project))[1]


def _resolve(view, key):
    if not isinstance(key, str) or not key: raise ValueError('Knowledge node ID is required')
    matches = [n for n in view['nodes'] if n['key'] == key] if ':' in key else [n for n in view['nodes'] if n['id'] == key]
    if not matches: raise ValueError('Unknown knowledge node: ' + key)
    if len(matches) != 1: raise ValueError('Ambiguous node ID; use memory:ID or claim:ID')
    return matches[0]


def get(project, node_id, revision=None):
    if revision is not None and (type(revision) is not int or revision < 1):
        raise ValueError('Invalid knowledge revision')
    graph, view = _view(Path(project))
    current = _resolve(view, node_id)
    if current['kind'] == 'claim':
        if revision is not None: raise ValueError('Use claim show for canonical claim history')
        from .claim_graph import get as claim_get
        return {**claim_get(Path(project), current['id']), **current}
    if current['key'].startswith('memory:'):
        raw = next(n for n in _memory(graph)['nodes'] if n['id'] == current['id'])
        if revision is None or revision == raw['revision']: return {**copy.deepcopy(raw), **current}
        old = next((r for r in raw['history'] if r['revision'] == revision), None)
        if old is None: raise ValueError('Unknown knowledge revision')
        if _integrity_reasons(old): raise ValueError('Historical knowledge record integrity mismatch')
        return {**copy.deepcopy(old), 'key': current['key'], 'historical': True,
                'validity': 'HISTORICAL_REVISION', 'verification_status': 'UNVERIFIED_SOURCE'}
    if revision is not None: raise ValueError('Source nodes do not have mutable revisions')
    return copy.deepcopy(current)


def search(project, query, kind=None, limit=20):
    text(query, 'knowledge search query')
    if kind is not None and kind not in KINDS | {'claim', 'source'}: raise ValueError('Unknown knowledge kind')
    if type(limit) is not int or not 1 <= limit <= 200: raise ValueError('Knowledge search limit must be 1..200')
    graph, view = _view(Path(project)); terms = query.casefold().split()
    from .knowledge_history import historical_nodes
    candidates = view['nodes'] + historical_nodes(graph)
    matches = [n for n in candidates if (kind is None or n['kind'] == kind)
               and all(term in json.dumps(n, ensure_ascii=False).casefold() for term in terms)]
    matches.sort(key=lambda n: (n.get('historical', False), not n['key'].startswith('claim:'), n['key']))
    return {'query': query, 'matches': matches[:limit], 'total': len(matches), 'note': NOTE}


def _walk(view, key, *, reverse=False):
    root = _resolve(view, key)
    reached = {root['key']}; queue = [root['key']]
    while queue:
        current = queue.pop(0)
        for edge in view['edges']:
            if reverse and edge['relation'] == 'associated_with': continue
            src, dst = (edge['to'], edge['from']) if reverse else (edge['from'], edge['to'])
            if src == current and dst not in reached:
                reached.add(dst); queue.append(dst)
    return root, [n for n in view['nodes'] if n['key'] in reached], [e for e in view['edges'] if e['from'] in reached and e['to'] in reached]


def trace(project, node_id):
    graph, view = _view(Path(project))
    root, nodes, edges = _walk(view, node_id)
    from .knowledge_history import pinned_trace
    frozen = pinned_trace(graph, root['key']) if root['key'].startswith(('memory:', 'claim:')) else {
        'frozen_nodes': [], 'frozen_edges': [], 'unresolved_pins': []}
    return {'root': root, 'nodes': nodes, 'edges': edges, **frozen, 'direction': 'UPSTREAM', 'note': NOTE}


def impact(project, node_id):
    root, nodes, edges = _walk(status(project), node_id, reverse=True)
    return {'root': root, 'affected': [n for n in nodes if n['key'] != root['key']], 'nodes': nodes,
            'edges': edges, 'direction': 'DOWNSTREAM', 'note': 'Reachability is dependency scope, not automatic scientific rejection.'}


def refresh(project):
    """Explicit materialisation; does not alter claims, STATE, budgets or pins."""
    project = Path(project)
    graph = _load(project); before = copy.deepcopy(graph)
    records, errors = _indexed(project)
    for spec in records: _upsert(project, graph, spec, 'Refresh local source index', automatic=True)
    memory = graph.get('memory')
    if memory:
        for key, result in _states(project, graph).items():
            node = next(n for n in memory['nodes'] if n['id'] == key)
            validity = {'validity': result['validity'], 'reasons': result['invalidation_reasons']}
            if node.get('last_validity') != validity:
                node['last_validity'] = validity
                memory['events'].append({'type': 'VALIDITY_CHANGED', 'id': key, **validity, 'at': stamp()})
    if graph != before: configuration.atomic_json(_safe(project, STORE + '/CLAIM_GRAPH.json'), graph)
    return {'schema_version': 1, 'changed': graph != before,
            'registered_nodes': len(_memory(graph)['nodes']), 'index_errors': errors, 'note': NOTE}


def invalidate(project, node_id, reason):
    text(reason, 'knowledge invalidation reason')
    project = Path(project); graph, view = _view(project)
    current = _resolve(view, node_id)
    if current['kind'] == 'claim':
        from .claim_graph import invalidate as invalidate_claim
        return invalidate_claim(project, current['id'], reason)
    # Reload the persisted store; ephemeral reads never become registrations as a side effect.
    graph = _load(project); memory = _memory(graph)
    node = next((n for n in memory['nodes'] if n['id'] == current['id']), None)
    if node is None: raise ValueError('Refresh or import a source before explicitly invalidating its registered version')
    if (node.get('invalidated') or {}).get('reason') == reason: return get(project, node_id)
    node['invalidated'] = {'reason': reason, 'at': stamp()}
    node['provenance_sha256'] = _provenance(node)
    memory['events'].append({'type': 'NODE_INVALIDATED', 'id': node['id'], 'reason': reason, 'at': stamp()})
    configuration.atomic_json(_safe(project, STORE + '/CLAIM_GRAPH.json'), graph)
    return get(project, node_id)


def context(project, *, limit=12):
    """Bounded, read-only retrieval for research and independent supervision."""
    view = status(project)
    registered = [n for n in view['memory_nodes'] if n['persisted']]
    selected = [n for n in registered if n['validity'] == 'PENDING_REVALIDATION']
    selected += [n for n in view['claim_nodes'] if n.get('invalidation_reasons')]
    selected += [n for n in registered if n not in selected]
    if not selected: selected = [n for n in view['memory_nodes'] if n['kind'] in {'obligation', 'failed_path', 'paper'}]
    compact = [{k: n[k] for k in ('key', 'kind', 'title', 'statement', 'revision', 'validity', 'proof_status', 'invalidation_reasons', 'sources') if k in n}
               for n in selected[:limit]]
    return ('# Source-bound long-term research memory\n' + NOTE + '\n'
            + json.dumps(compact, ensure_ascii=False, indent=2)[:20000]
            + '\nUse knowledge trace/show for exact revisions and original source locations. '
              'Stale dependencies must be revalidated; memory never overrides the frozen goal or proof gates.\n')
