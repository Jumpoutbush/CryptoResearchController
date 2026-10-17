"""Read candidate disposition archives without importing scientific authority."""
from pathlib import Path
import re

from supervision_snapshot import _path


def controller_paths(controller, project_id, project=None):
    """Missing archives leave the legacy manifest byte-for-byte unchanged."""
    if (not isinstance(project_id, str) or not project_id or '/' in project_id
            or '\\' in project_id or ':' in project_id or project_id in {'.', '..'}):
        raise ValueError('Invalid candidate archive project identity')
    result = []
    for name in ('history.json', 'history.registry.json'):
        relative = 'state/candidates/' + project_id + '/' + name
        path = _path(Path(controller), relative)
        if path.exists():
            if not path.is_file():
                raise ValueError('Candidate archive source must be an ordinary file')
            result.append(relative)
    if result and project is not None:
        from candidate_search import history
        prefix = 'state/candidates/' + project_id + '/verification/'
        for record in history.projection_records(project):
            for relative, digest in record.get('controller_bindings', {}).items():
                if (not isinstance(relative, str) or not relative.startswith(prefix)
                        or not re.fullmatch(r'V-[0-9a-f]{64}\.(request|started|receipt)\.json', relative[len(prefix):])
                        or not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest)):
                    raise ValueError('Candidate archive controller evidence must name its own frozen verifier receipt')
                path = _path(Path(controller), relative)
                if path.exists() and not path.is_file():
                    raise ValueError('Candidate verification source must be an ordinary file')
                # A missing registered receipt remains in the input manifest
                # with a null digest, so deletion invalidates the archive.
                result.append(relative)
    return sorted(set(result))


def project(g, claim_nodes):
    if not controller_paths(g.controller, g.project_id):
        return
    # Old projection-only fixtures need no candidate package. A registered
    # archive, including an orphan registry, must instead validate or stop.
    from candidate_search import history
    relative = 'state/candidates/' + g.project_id + '/history.json'
    for record in history.projection_records(g.project):
        status = record['status']
        if status not in {'REFUTED', 'COVERED', 'RETIRED', 'CONDITIONAL'}:
            raise ValueError('Unknown candidate archive disposition')
        pins = record.get('evidence_bindings', {})
        authority_pins = record.get('authority_bindings', {})
        controller_pins = record.get('controller_bindings', {})
        if any(path != 'research/discovery/CLAIM_GRAPH.json' for path in authority_pins):
            raise ValueError('Candidate canonical review snapshot has an unexpected authority source')
        stale = [path for path, digest in pins.items() if g.digest(path) != digest]
        stale += ['AUTHORITY:' + path for path, digest in authority_pins.items()
                  if g.digest(path) != digest]
        stale += ['CONTROLLER:' + path for path, digest in controller_pins.items()
                  if g.digest(path, 'CONTROLLER') != digest]
        if record.get('goal_sha256') != g.goal:
            stale.append('GOAL.md')
        validity = 'PENDING_REVALIDATION' if stale else 'SOURCE_BOUND'
        rid = record.get('resolution_id', record.get('id'))
        if not isinstance(rid, str) or not rid:
            raise ValueError('Candidate resolution identity missing')
        uid = g.node('EXPLORATION_NODE' if status == 'CONDITIONAL' else 'FAILED_BRANCH',
            'candidate-resolution/' + rid, 1, relative, scope='CONTROLLER',
            origin_role='CANDIDATE_RESOLUTION', resolution_id=rid,
            candidate_id=record['candidate_id'], candidate_revision=record['candidate_revision'],
            candidate_spec_sha256=record['candidate_spec_sha256'], status=status,
            goal_sha256=record['goal_sha256'], goal_anchor_id=record.get('goal_anchor_id'),
            problem_id=record.get('problem_id'), problem_version=record.get('problem_version'),
            problem_sha256=record.get('problem_sha256'), historical=True,
            conclusion_scope=record['scope'], assumptions=record.get('assumptions', []),
            failure_reason=record['reason'], restart_conditions=record['restart_conditions'],
            used_research_rounds=record['route_effective_rounds'], route_epoch=record['route_epoch'],
            open_obligations=record.get('open_obligations', []),
            reusable_lemmas=record.get('reusable_lemmas', []), evidence_bindings=pins,
            authority_bindings=authority_pins,
            controller_evidence_bindings=controller_pins,
            validity=validity, stale_sources=sorted(set(stale)),
            verified_status='SCOPED_BRANCH_ARCHIVE_NOT_GLOBAL_RESULT',
            positive_basis=False, scientific_acceptance=False, family_refuted=False)
        for path, digest in pins.items():
            source = g.source(path, digest)
            if source:
                g.edge(uid, source, 'USES_SOURCE', relative, scope='CONTROLLER',
                    provenance='FROZEN_CANDIDATE_DISPOSITION', verified=validity,
                    evidence_sha256=digest)
        for path, digest in controller_pins.items():
            actual = g.digest(path, 'CONTROLLER')
            source = g.node('SOURCE_VERSION', path, digest, path, scope='CONTROLLER',
                pinned_sha256=digest, current_sha256=actual,
                validity='SOURCE_BOUND' if actual == digest else 'PENDING_REVALIDATION')
            g.edge(uid, source, 'USES_SOURCE', relative, scope='CONTROLLER',
                provenance='FROZEN_MACHINE_CERTIFICATE_AUDIT', verified=validity,
                evidence_sha256=digest)
        for path, digest in authority_pins.items():
            source = g.source(path, digest)
            if source:
                g.edge(uid, source, 'USES_SOURCE', relative, scope='CONTROLLER',
                    provenance='CANONICAL_REVIEW_STATE_SNAPSHOT', verified=validity,
                    evidence_sha256=digest, scientific_acceptance=False)
        for lemma in record.get('reusable_lemmas', []):
            classification = lemma['scope']
            if classification not in {'DIRECT_DEPENDENCY', 'SUPPORT'}:
                raise ValueError('Invalid reusable lemma classification')
            target = claim_nodes.get((lemma['id'], lemma['revision']))
            if target and g.nodes[target]['spec_sha256'] == lemma['spec_sha256']:
                g.edge(uid, target, 'USES_SOURCE', relative, scope='CONTROLLER',
                    provenance='SCOPED_LEMMA_REUSE_SUGGESTION', verified='REFERENCE_ONLY',
                    classification=classification, scientific_acceptance=False)
            else:
                g.gaps.add('UNMAPPED_REUSABLE_LEMMA:' + lemma['id'])
