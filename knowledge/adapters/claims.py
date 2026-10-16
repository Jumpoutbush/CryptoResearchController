"""Exact canonical revisions and statuses, including non-promoted historical pins."""
import copy
from engine import claim_graph
from supervision_contracts import canonical_hash


def read(project):
    graph = claim_graph.load(project)
    if (not isinstance(graph, dict) or graph.get('schema_version') != 1
            or not isinstance(graph.get('claims'), list) or not isinstance(graph.get('events'), list)):
        raise ValueError('Unsupported canonical claim graph')
    statuses = {c['id']:c for c in claim_graph.status(project)['claims']}
    records = []
    seen = set()
    for current in graph['claims']:
        for item in [*current.get('history', []), current]:
            key = (item['id'], item['revision'])
            if key in seen or type(item['revision']) is not int or item['revision'] < 1:
                raise ValueError('Duplicate or invalid canonical claim revision')
            seen.add(key)
            is_current = item is current
            if not is_current and canonical_hash(item['spec']) != item['spec_sha256']:
                raise ValueError('Corrupt historical claim specification')
            status = copy.deepcopy(statuses[current['id']]) if is_current else {
                'proof_status':'HISTORICAL_NOT_REVALIDATED', 'novelty_status':'HISTORICAL_NOT_REVALIDATED',
                'invalidation_reasons':['HISTORICAL_REVISION_NOT_REVALIDATED'], 'accepted_contribution':False}
            records.append((copy.deepcopy(item), status, is_current))
    return records
