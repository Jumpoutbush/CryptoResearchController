"""Pure, read-only snapshots of exact claim/memory dependency revisions.

These snapshots preserve recorded provenance. They do not check current files or
attest mathematical correctness, even when the canonical current claim is reviewed.
"""
from __future__ import annotations

import copy
import re

from .common import identifier, object_hash


def _catalog(graph):
    result = {}
    if not isinstance(graph, dict): return result
    memory = graph.get('memory') or {}
    groups = [('claim', graph.get('claims', [])),
              ('memory', memory.get('nodes', []) if isinstance(memory, dict) else [])]
    for namespace, nodes in groups:
        if not isinstance(nodes, list): continue
        for node in nodes:
            if not isinstance(node, dict) or not isinstance(node.get('id'), str): continue
            result.setdefault((namespace, node['id']), []).append(node)
    return result


def _version_key(namespace, node_id, revision):
    return namespace + ':' + node_id + '@r' + str(revision)


def _resolve(catalog, namespace, node_id, revision=None, digest=None):
    owners = catalog.get((namespace, node_id), [])
    if not owners: return None, False, 'NODE_MISSING'
    if len(owners) != 1: return None, False, 'NODE_AMBIGUOUS'
    current = owners[0]
    wanted = current.get('revision') if revision is None else revision
    if type(wanted) is not int or wanted < 1: return None, False, 'REVISION_INVALID'
    history = current.get('history', [])
    if not isinstance(history, list): return None, False, 'HISTORY_INVALID'
    versions = [n for n in [current, *history]
                if isinstance(n, dict) and type(n.get('revision')) is int and n['revision'] == wanted]
    if not versions: return None, False, 'REVISION_MISSING'
    if len(versions) != 1: return None, False, 'REVISION_AMBIGUOUS'
    record = versions[0]; spec = record.get('spec')
    if record.get('id') != node_id or not isinstance(spec, dict) or spec.get('id') != node_id:
        return None, False, 'RECORD_ID_MISMATCH'
    if object_hash(spec) != record.get('spec_sha256'):
        return None, False, 'SPEC_DIGEST_MISMATCH'
    if digest is not None and record['spec_sha256'] != digest:
        return None, False, 'PIN_DIGEST_MISMATCH'
    if namespace == 'memory':
        provenance = {key: record.get(key) for key in
                      ('id', 'revision', 'invalidated', 'source_bindings', 'sources',
                       'dependency_pins', 'goal_sha256')}
        if object_hash(provenance) != record.get('provenance_sha256'):
            return None, False, 'PROVENANCE_DIGEST_MISMATCH'
    return record, record is not current, None


def _snapshot(namespace, record, historical):
    spec = record['spec']
    result = {'key': _version_key(namespace, record['id'], record['revision']),
              'id': record['id'], 'kind': 'claim' if namespace == 'claim' else spec.get('kind', 'evidence'),
              'revision': record['revision'], 'spec_sha256': record['spec_sha256'],
              'title': spec.get('title', spec.get('statement', record['id'])),
              'statement': spec.get('statement', ''), 'spec': copy.deepcopy(spec),
              'historical': historical,
              'validity': 'HISTORICAL_REVISION' if historical else 'FROZEN_REVISION_SNAPSHOT',
              'verification_status': 'UNVERIFIED_SOURCE'}
    # No history, review attestations, or verifier receipts are copied into a
    # snapshot. Original source hashes and the revision's own pins remain exact.
    for key in ('sources', 'source_bindings', 'evidence', 'dependency_pins', 'knowledge_pins',
                'invalidated', 'goal_sha256', 'provenance_sha256'):
        if key in record: result[key] = copy.deepcopy(record[key])
    return result


def historical_nodes(graph):
    """Return searchable past revisions, without changing the canonical graph."""
    catalog = _catalog(graph); result = []
    for (namespace, node_id), owners in sorted(catalog.items()):
        if len(owners) != 1 or not isinstance(owners[0].get('history', []), list): continue
        for old in owners[0].get('history', []):
            if not isinstance(old, dict): continue
            record, historical, error = _resolve(catalog, namespace, node_id, old.get('revision'))
            if not error and historical: result.append(_snapshot(namespace, record, True))
    return sorted(result, key=lambda n: (n['kind'], n['id'], n['revision']))


def pinned_trace(graph, root_key):
    """Trace exact recorded revisions, never replacing a missing pin with latest."""
    catalog = _catalog(graph); nodes, edges, unresolved = {}, [], []
    active = set()

    def missing(source, target, pin, reason):
        unresolved.append({'from': source, 'to': target, 'pin': copy.deepcopy(pin), 'reason': reason})

    def visit(namespace, node_id, revision=None, digest=None, source=None, pin=None):
        target = namespace + ':' + node_id if revision is None else _version_key(namespace, node_id, revision)
        record, historical, error = _resolve(catalog, namespace, node_id, revision, digest)
        if error:
            missing(source, target, pin, error); return
        key = _version_key(namespace, node_id, record['revision'])
        if key in active:
            missing(source, key, pin, 'DEPENDENCY_CYCLE'); return
        if source is not None:
            edge = {'from': source, 'to': key, 'relation': 'depends_on', 'pin': copy.deepcopy(pin)}
            if edge not in edges: edges.append(edge)
        if key in nodes: return
        nodes[key] = _snapshot(namespace, record, historical)
        active.add(key)
        groups = [('dependency_pins', 'dependencies', namespace)]
        if namespace == 'claim': groups.append(('knowledge_pins', 'knowledge_dependencies', 'memory'))
        for field, declared_field, parent_namespace in groups:
            pins = record.get(field, {})
            declared = record['spec'].get(declared_field, [])
            if (not isinstance(pins, dict) or not isinstance(declared, list)
                    or not all(isinstance(dep, str) for dep in declared)
                    or set(pins) != set(declared)):
                missing(key, field, None, 'DEPENDENCY_BINDING_INVALID')
                if not isinstance(pins, dict): continue
            for dep, parent_pin in pins.items():
                try: identifier(dep)
                except ValueError:
                    missing(key, parent_namespace + ':' + str(dep), parent_pin, 'DEPENDENCY_ID_INVALID'); continue
                if (not isinstance(parent_pin, dict) or set(parent_pin) != {'revision', 'spec_sha256'}
                        or type(parent_pin['revision']) is not int or parent_pin['revision'] < 1
                        or not isinstance(parent_pin['spec_sha256'], str)
                        or not re.fullmatch(r'[0-9a-f]{64}', parent_pin['spec_sha256'])):
                    missing(key, parent_namespace + ':' + dep, parent_pin, 'PIN_INVALID'); continue
                visit(parent_namespace, dep, parent_pin['revision'], parent_pin['spec_sha256'], key, parent_pin)
        active.remove(key)

    match = re.fullmatch(r'(memory|claim):([A-Za-z0-9][A-Za-z0-9_.-]{0,79})(?:@r([1-9][0-9]*))?', root_key) if isinstance(root_key, str) else None
    if match:
        namespace, node_id, revision = match.groups()
        try: identifier(node_id)
        except ValueError: missing(None, root_key, None, 'ROOT_ID_INVALID')
        else: visit(namespace, node_id, int(revision) if revision else None)
    else: missing(None, root_key, None, 'ROOT_KEY_INVALID')
    return {'frozen_nodes': list(nodes.values()), 'frozen_edges': edges, 'unresolved_pins': unresolved}
