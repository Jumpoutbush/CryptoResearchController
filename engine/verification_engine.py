"""Ingest new candidates and run bounded, independent checks after round acceptance."""
from __future__ import annotations
from research_quality import local_file, read_object
from .common import fresh, policy
from . import claim_graph as graph


def process_candidates(project, checkpoint):
    if not checkpoint: return []
    results = []
    if not fresh(project, checkpoint.get('evidence', {})):
        return [{'status': 'STALE_CHECKPOINT', 'accepted_as_proof': False}]
    config = policy(project)
    for relative in checkpoint.get('candidate_claim_files', []):
        record = {'file': relative, 'accepted_as_proof': False}
        try:
            spec = read_object(local_file(project, relative))
            # A model may propose a new node; an existing reviewed node cannot be
            # silently revised by proposing the same ID in a later round.
            if any(c['id'] == spec.get('id') for c in graph.load(project)['claims']):
                raise ValueError('Existing claim ID; operator claim import required for a revision')
            spec['proposer'] = 'codex:' + checkpoint['run_id']
            item = graph.import_claim(project, spec, 'Candidate proposed by accepted attempt ' + checkpoint['attempt_id'])
            record.update(claim_id=item['id'], status='CANDIDATE_IMPORTED')
            if config['automatic_falsification'] and 'machine_statement' in spec:
                from .falsification import search
                record['counterexample_check'] = search(project, item['id'])
            target = spec.get('formal_target')
            if target:
                from .formal_verifier import run
                record['formal_check'] = run(project, item['id'], target['file'], target['declaration'])
            # Even a successful Lean call never creates a proof/novelty review.
        except (ValueError, OSError, KeyError, RuntimeError) as exc:
            record.update(status='CANDIDATE_REQUIRES_REVIEW', reason=str(exc))
        results.append(record)
    return results
