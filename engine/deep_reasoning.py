"""Restore verifiable mathematical state across bounded model invocations."""
from __future__ import annotations
import json
import configuration
from research_quality import read_object
from .common import evidence, fresh, identifier, strings, text
from .problem_compiler import get_problem
from .discovery_scheduler import active, check, slot


def context(project):
    item = active(project)
    if item is None: return ''
    problem = get_problem(project, item['problem_id'], item['problem_version'])
    mode = item['calls'][-1]['mode'] if item['calls'] and item['calls'][-1]['status'] == 'RESERVED' else slot(item)
    root = configuration.ROOT
    prompt = root / 'prompts' / ('adversarial_review.md' if mode == 'FALSIFICATION' else 'deep_proof.md')
    from .claim_graph import status
    graph = status(project)
    path = checkpoint_path(item)
    contract = {
        'schema_version': 1, 'attempt_id': item['id'], 'run_id': '<this run_id>',
        'problem_sha256': item['problem_sha256'],
        'outcome': 'OPEN|CANDIDATE_PROOF|COUNTEREXAMPLE_CANDIDATE|NO_PROGRESS',
        'obligations': [{'id': o['id'], 'status': 'OPEN', 'claim_id': None,
                         'gap': o['acceptance_criterion']} for o in problem['spec']['obligations']],
        'candidate_claim_ids': [], 'candidate_claim_files': [], 'evidence_paths': [],
        'next_action': 'A precise proof step, missing lemma, or falsifiable counterexample test',
    }
    return '\n\n'.join([
        '# Mathematical Discovery Engine: fixed-problem continuation',
        prompt.read_text(encoding='utf8') if prompt.is_file() else '',
        'ATTEMPT_ID: ' + item['id'] + '\nMODE: ' + mode,
        '# Frozen mathematical contract\n' + json.dumps(problem['spec'], ensure_ascii=False, indent=2),
        '# Last accepted mathematical checkpoint (candidate assertions remain unverified)\n'
        + json.dumps(item.get('checkpoint'), ensure_ascii=False, indent=2),
        '# Claim graph: current validity, not model self-certification\n' + json.dumps(graph, ensure_ascii=False, indent=2),
        '# Required mathematical checkpoint\nWrite ' + path + ' with this schema:\n'
        + json.dumps(contract, ensure_ascii=False, indent=2),
        'Use exactly the pinned obligation IDs. OPEN gaps remain explicit. CANDIDATE needs evidence and awaits review. '
        'DISCHARGED requires a valid independently reviewed claim from the graph; creating a proposed claim file cannot close a gap. '
        'Save new claim proposals separately in research/attempts/' + item['id'] + '/proposals/. '
        'List at most two new proposal files in candidate_claim_files and evidence_paths. The controller can import new IDs as unverified candidates, '
        'then run the registered exact-integer/Lean checks. Revisions of existing claims require operator claim import. '
        'Never edit research/discovery/ or controller state. '
        'Do not relax quantifiers, assumptions, security targets, output guarantees, or costs. '
        'Preserve the active route. Budget exhaustion and missing proofs are unresolved results, not impossibility theorems. '
        'Update the ordinary round report and ROUND_REVIEW contract too. Record mathematical derivations, certificates and gaps; '
        'no private internal reasoning trace is requested. Separate independent tool verification from adversarial model critique.',
    ])


def checkpoint_path(item):
    return 'research/attempts/' + identifier(item['id']) + '/CHECKPOINT.json'


def validate_checkpoint(project, run_id):
    item = active(project)
    if item is None: return None
    # Budget was charged before the call, so check() cannot be used at this point.
    from .common import goal_binding
    if goal_binding(project) != item['binding']: raise ValueError('Attempt binding changed during model execution')
    obj = read_object(project / checkpoint_path(item))
    if obj.get('schema_version') != 1 or obj.get('run_id') != run_id or obj.get('attempt_id') != item['id']:
        raise ValueError('Checkpoint must bind this attempt and fresh run_id')
    if obj.get('problem_sha256') != item['problem_sha256']: raise ValueError('Checkpoint weakened or changed the pinned problem')
    if obj.get('outcome') not in {'OPEN', 'CANDIDATE_PROOF', 'COUNTEREXAMPLE_CANDIDATE', 'NO_PROGRESS'}:
        raise ValueError('A model checkpoint cannot claim PROVED or VERIFIED')
    problem = get_problem(project, item['problem_id'], item['problem_version'])
    expected = {o['id'] for o in problem['spec']['obligations']}
    obligations = obj.get('obligations')
    if not isinstance(obligations, list) or len(obligations) != len(expected): raise ValueError('Proof obligations may not be dropped')
    seen = set()
    from .claim_graph import status as graph_status
    graph = {c['id']: c for c in graph_status(project)['claims']}
    for obligation in obligations:
        if not isinstance(obligation, dict) or obligation.get('id') not in expected or obligation['id'] in seen:
            raise ValueError('Unknown or duplicate proof obligation')
        seen.add(obligation['id'])
        if obligation.get('status') not in {'OPEN', 'CANDIDATE', 'DISCHARGED'}: raise ValueError('Invalid obligation status')
        text(obligation.get('gap'), 'obligation gap or discharge explanation')
        if obligation['status'] == 'DISCHARGED':
            claim = graph.get(obligation.get('claim_id'), {})
            if claim.get('proof_status') != 'INDEPENDENTLY_REVIEWED' or obligation['id'] not in claim.get('obligation_ids', []):
                raise ValueError('Discharge requires a current independently reviewed claim for this obligation')
            if claim.get('problem_id') != item['problem_id'] or claim.get('problem_version') != item['problem_version']:
                raise ValueError('Discharge claim belongs to a different problem revision')
    strings(obj.get('candidate_claim_ids'), 'candidate_claim_ids', empty=True)
    for cid in obj['candidate_claim_ids']: identifier(cid)
    text(obj.get('next_action'), 'next_action')
    obj['evidence'] = evidence(project, obj.get('evidence_paths', []), empty=obj['outcome'] == 'NO_PROGRESS')
    files = strings(obj.get('candidate_claim_files', []), 'candidate_claim_files', empty=True)
    if len(files) > 2 or len(files) != len(set(files)): raise ValueError('At most two unique candidate proposals per call')
    from research_quality import local_file
    for rel in files:
        path = local_file(project, rel)
        path.relative_to((project / 'research/attempts' / item['id'] / 'proposals').resolve())
        if rel not in obj['evidence']: raise ValueError('Candidate proposal must appear in evidence_paths')
        if path.stat().st_size > 40000: raise ValueError('Candidate proposal exceeds 40 KB')
        proposal = read_object(path)
        if proposal.get('problem_id') != item['problem_id'] or proposal.get('problem_version') != item['problem_version']:
            raise ValueError('Candidate proposal changed the pinned problem revision')
    if len(str(obj)) > 80000: raise ValueError('Checkpoint exceeds 80 KB; cite derivation files')
    return obj
