"""Distinguish candidate evidence changes from accepted mathematical results."""
from __future__ import annotations


def evaluate_checkpoint(project, current, previous=None):
    if not current: return {'procedural_progress': False, 'scientific_acceptance': False}
    previous = previous or {}
    changed = [p for p, sha in current.get('evidence', {}).items()
               if sha != previous.get('evidence', {}).get(p)]
    from .claim_graph import status, get, receipt_fresh
    from .common import object_hash
    graph = {c['id']: c for c in status(project)['claims']}
    accepted = [cid for cid in current.get('candidate_claim_ids', [])
                if graph.get(cid, {}).get('accepted_contribution')]
    ids = set(current.get('candidate_claim_ids', [])) | {o.get('claim_id') for o in current['obligations'] if o.get('status') == 'DISCHARGED'}
    fingerprints = {}
    for cid in ids:
        if cid not in graph: continue
        item = get(project, cid)
        if graph[cid]['proof_status'] == 'INDEPENDENTLY_REVIEWED':
            fingerprints[cid] = object_hash({'spec': item['spec_sha256'], 'evidence': item['evidence'],
                'reviews': {k: r['evidence'] for k, r in item['reviews'].items()},
                'dependencies': item['dependency_pins'],
                'formal_sources': (item.get('formal_receipt') or {}).get('source_bindings')})
        witness = item.get('counterexample_receipt')
        if witness and receipt_fresh(project, item, witness):
            fingerprints[cid + ':machine-witness'] = object_hash({'statement': witness['machine_statement_sha256'],
                                                                'assignment': witness['witness']['assignment']})
    prior = previous.get('verified_progress_fingerprints', {})
    new_results = [cid for cid, sha in fingerprints.items() if prior.get(cid) != sha]
    current['verified_progress_fingerprints'] = {**prior, **fingerprints}
    return {'procedural_progress': bool(new_results), 'new_checked_result_ids': new_results,
            'scientific_acceptance': bool(accepted), 'accepted_claim_ids': accepted,
            'changed_evidence_paths': changed,
            'candidate_artifacts_changed': bool(changed),
            'note': 'Only new reviewed results or exact machine witnesses reset stagnation; fresh text remains candidate evidence.'}
