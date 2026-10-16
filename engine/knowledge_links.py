"""Resolve declared legacy evidence links without inferring scientific truth.

The indexer supplies source-file and registry-entry specs. This pure adapter
connects explicit local paths and evidence IDs to those specs, retains missing
or ambiguous references, and never reads project files or changes input data.
"""
from __future__ import annotations

import copy
from urllib.parse import urlparse


SCIENTIFIC_ROOTS = {'research', 'proofs', 'literature', 'experiments', 'inputs',
                    'reports', 'ideas'}
PATH_FIELDS = ('evidence', 'evidence_paths', 'source_paths', 'file', 'path',
               'source_file', 'derivation_paths', 'technical_reviews')
RELATED_FIELDS = ('blocking_obligations', 'obligation_ids', 'addresses_obligations')


def _path(value):
    """Return a canonical lookup key only for explicit scientific paths."""
    if not isinstance(value, str) or not value.strip(): return None
    if urlparse(value).scheme.casefold() in {'http', 'https'}: return None
    first = value.split('/', 1)[0].casefold()
    plausible = first in SCIENTIFIC_ROOTS or value.startswith(('/', '..', '.\\')) or '\\' in value or ':' in value
    if not plausible: return None
    if (value != value.strip() or '\\' in value or ':' in value or value.startswith('/')
            or any(p in {'', '.', '..'} for p in value.split('/'))
            or first not in SCIENTIFIC_ROOTS or '/' not in value):
        raise ValueError('Unsafe or non-scientific local source path: ' + value)
    return value.casefold()


def _path_refs(value):
    """Yield (path, optional declared digest) from explicit legacy fields."""
    if isinstance(value, str):
        yield value, None
    elif isinstance(value, list):
        for item in value: yield from _path_refs(item)
    elif isinstance(value, dict):
        explicit = False
        for field in ('path', 'file', 'source_file'):
            if isinstance(value.get(field), str):
                explicit = True
                yield value[field], value.get('sha256')
        if not explicit:
            for path, digest in value.items():
                if isinstance(path, str):
                    try: canonical = _path(path)
                    except ValueError: canonical = True
                    if canonical: yield path, digest if isinstance(digest, str) else None


def _ids(value):
    if isinstance(value, str): return [value]
    if isinstance(value, list): return [v for v in value if isinstance(v, str)]
    return []


def link_records(records):
    """Return linked specs in dependency order plus auditable index errors.

    Only declared evidence dependencies affect validity. Proof-obligation links
    are tagged ``addresses`` relationships and cannot certify or reject a claim.
    An unresolved dependency is retained in ``metadata.missing_dependencies``.
    """
    if not isinstance(records, list): raise ValueError('Knowledge index records must be a list')
    result = copy.deepcopy(records)
    by_id, paths, evidence_ids, obligation_ids = {}, {}, {}, {}
    errors = []
    for spec in result:
        if not isinstance(spec, dict) or not isinstance(spec.get('id'), str):
            raise ValueError('Invalid knowledge index record')
        if spec['id'] in by_id: raise ValueError('Duplicate automatic knowledge index ID: ' + spec['id'])
        by_id[spec['id']] = spec
        metadata = spec.setdefault('metadata', {})
        if not isinstance(metadata, dict): raise ValueError('Invalid knowledge index metadata')
        if metadata.get('index_role') == 'source_file':
            canonical = _path(metadata.get('source_path'))
            if canonical: paths.setdefault(canonical, []).append(spec)
        if metadata.get('index_role') == 'registry_entry' and isinstance(metadata.get('original_id'), str):
            if spec.get('kind') == 'evidence':
                evidence_ids.setdefault(metadata['original_id'], []).append(spec)
            if spec.get('kind') == 'obligation':
                obligation_ids.setdefault(metadata['original_id'], []).append(spec)

    def missing(spec, reference, message):
        values = spec['metadata'].setdefault('missing_dependencies', [])
        if reference not in values: values.append(reference)
        errors.append(spec['id'] + ': ' + message)

    def cyclic(source, target):
        pending, visited = [target], set()
        while pending:
            node_id = pending.pop()
            if node_id == source: return True
            if node_id in visited: continue
            visited.add(node_id)
            node = by_id.get(node_id)
            if node: pending.extend(node.get('dependencies', []))
        return False

    def connect(spec, target, reference):
        deps = spec.setdefault('dependencies', [])
        if target['id'] in deps: return
        if cyclic(spec['id'], target['id']):
            missing(spec, 'cycle:' + reference, 'Cyclic declared evidence dependency: ' + reference)
            return
        deps.append(target['id'])

    for spec in result:
        metadata = spec['metadata']
        row = metadata.get('original_record')
        if metadata.get('index_role') != 'registry_entry' or not isinstance(row, dict): continue
        references = []
        for field in PATH_FIELDS:
            for path, declared_digest in _path_refs(row.get(field)):
                if field in {'file', 'path', 'source_file'} and declared_digest is None:
                    declared_digest = row.get('sha256')
                references.append((path, declared_digest))
        seen = set()
        for path, declared_digest in references:
            reference_key = (path, str(declared_digest))
            if reference_key in seen: continue
            seen.add(reference_key)
            try: canonical = _path(path)
            except ValueError as exc:
                missing(spec, 'unsafe:' + path, str(exc)); continue
            if canonical is None: continue
            candidates = paths.get(canonical, [])
            if len(candidates) != 1:
                missing(spec, path, ('Ambiguous' if candidates else 'Missing') + ' declared scientific source: ' + path)
                continue
            target = candidates[0]
            target_digest = next((s.get('sha256') for s in target.get('sources', [])
                                  if isinstance(s, dict) and isinstance(s.get('path'), str)
                                  and s['path'].casefold() == canonical), None)
            if declared_digest is not None and declared_digest != target_digest:
                missing(spec, 'digest:' + path, 'Declared scientific source digest mismatch: ' + path)
            connect(spec, target, path)
        for evidence_id in _ids(row.get('evidence_ids')):
            candidates = evidence_ids.get(evidence_id, [])
            if len(candidates) != 1:
                missing(spec, 'evidence_id:' + evidence_id,
                        ('Ambiguous' if candidates else 'Missing') + ' declared evidence ID: ' + evidence_id)
                continue
            connect(spec, candidates[0], 'evidence_id:' + evidence_id)
        related = metadata.setdefault('related_nodes', [])
        for field in RELATED_FIELDS:
            for obligation_id in _ids(row.get(field)):
                candidates = obligation_ids.get(obligation_id, [])
                if len(candidates) != 1:
                    values = metadata.setdefault('missing_relations', [])
                    reference = 'obligation_id:' + obligation_id
                    if reference not in values: values.append(reference)
                    errors.append(spec['id'] + ': ' + ('Ambiguous' if candidates else 'Missing')
                                  + ' proof-obligation relationship: ' + obligation_id)
                    continue
                relation = {'target': candidates[0]['id'], 'relation': 'addresses'}
                if relation not in related: related.append(relation)
        if not related: metadata.pop('related_nodes', None)

    # Sources precede entries that cite them, and evidence entries precede the
    # claims that use their IDs, regardless of filesystem enumeration order.
    ordered, done, visiting = [], set(), set()
    def visit(node_id):
        if node_id in done: return
        if node_id in visiting: raise ValueError('Cyclic automatic knowledge index')
        visiting.add(node_id)
        spec = by_id[node_id]
        for dep in spec.get('dependencies', []):
            if dep in by_id: visit(dep)
        visiting.remove(node_id)
        done.add(node_id)
        ordered.append(spec)
    for spec in result: visit(spec['id'])
    return ordered, errors
