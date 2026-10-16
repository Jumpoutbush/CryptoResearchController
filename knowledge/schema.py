"""Versioned derived graph vocabulary and deterministic identities."""
from urllib.parse import quote
from supervision_contracts import canonical_hash

SCHEMA_VERSION = 1
BUILDER_VERSION = 'R07.1'
KINDS = {'PROJECT', 'GOAL', 'PROBLEM_VERSION', 'OBLIGATION', 'CLAIM_REVISION',
         'EVIDENCE_FILE', 'SOURCE_VERSION', 'THEOREM_SPAN', 'RESEARCH_RUN', 'EXPLORATION_NODE', 'FAILED_BRANCH'}
RELATIONS = {'REQUIRES', 'SUPPORTS', 'REFUTES', 'DERIVED_FROM', 'REVIEWED_BY', 'USES_SOURCE', 'SUPERSEDES'}


def identity(project, kind, source_id, revision):
    if kind not in KINDS: raise ValueError('Unknown projection node kind')
    return ':'.join(quote(str(x), safe='') for x in (project, kind, source_id, revision))


def validate(graph):
    if (not isinstance(graph,dict) or type(graph.get('schema_version')) is not int
            or graph.get('schema_version') != SCHEMA_VERSION or graph.get('builder_version') != BUILDER_VERSION):
        raise ValueError('Unsupported derived graph version')
    ids = set()
    for node in graph['nodes']:
        if (node['id'] in ids or node['kind'] not in KINDS or node['project_id'] != graph['project_id']
                or node['id'] != identity(graph['project_id'], node['kind'], node['source_id'], node['revision'])):
            raise ValueError('Invalid or duplicate projection identity')
        ids.add(node['id'])
        if not {'source_path', 'source_sha256', 'goal_sha256', 'verified_status'} <= node.keys():
            raise ValueError('Missing node provenance')
        if node['kind'] != 'CLAIM_REVISION' and node.get('proof_status') == 'INDEPENDENTLY_REVIEWED':
            raise ValueError('Only canonical current claims can inherit proof status')
    seen = set()
    for edge in graph['edges']:
        digest = canonical_hash(edge)
        if (digest in seen or edge['from'] not in ids or edge['to'] not in ids
                or edge['relation'] not in RELATIONS or not {'provenance_kind', 'source_path',
                    'source_sha256', 'scope', 'verified_status'} <= edge.keys()):
            raise ValueError('Invalid derived edge')
        seen.add(digest)
    unsigned = {k:v for k,v in graph.items() if k != 'graph_sha256'}
    if graph.get('graph_sha256') != canonical_hash(unsigned): raise ValueError('Corrupt derived graph digest')
    return graph
