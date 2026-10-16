"""Versioned mathematical claims with transitive invalidation and scoped reviews."""
from __future__ import annotations
import copy
import configuration
from research_quality import CORE_TYPES, hash_file, local_file, read_object, validate_technical_review
from .common import (STORE, evidence, fresh, goal_binding, identifier, object_hash,
                     policy, stamp, strings, text)
from .problem_compiler import get_problem


def load(project):
    return configuration.load_json(project / STORE / 'CLAIM_GRAPH.json',
        {'schema_version': 1, 'claims': [], 'events': []})


def save(project, data):
    configuration.atomic_json(project / STORE / 'CLAIM_GRAPH.json', data)


def get(project, claim_id):
    identifier(claim_id)
    item = next((c for c in load(project)['claims'] if c['id'] == claim_id), None)
    if item is None: raise ValueError('Unknown claim: ' + claim_id)
    if item.get('formal_receipt'): item['formal_receipt_sha256'] = object_hash(item['formal_receipt'])
    return item


def import_claim(project, spec, reason):
    if not isinstance(spec, dict) or spec.get('schema_version') != 1: raise ValueError('Claim schema_version must be 1')
    cid = identifier(spec.get('id'))
    for key in ('statement', 'proposer', 'nontriviality_argument'): text(spec.get(key), key)
    strings(spec.get('assumptions'), 'assumptions')
    strings(spec.get('dependencies'), 'dependencies', empty=True)
    if 'knowledge_dependencies' in spec:
        strings(spec['knowledge_dependencies'], 'knowledge_dependencies', empty=True)
        if len(spec['knowledge_dependencies']) != len(set(spec['knowledge_dependencies'])):
            raise ValueError('Duplicate knowledge dependency')
    strings(spec.get('obligation_ids'), 'obligation_ids')
    if spec.get('contribution_type') not in CORE_TYPES: raise ValueError('Claim requires a theoretical contribution type')
    if spec.get('verification_mode') not in {'FORMAL_REQUIRED', 'INDEPENDENT_MANUAL'}:
        raise ValueError('Claim must declare FORMAL_REQUIRED or INDEPENDENT_MANUAL verification_mode')
    text(spec.get('formal_applicability_reason'), 'formal_applicability_reason')
    if spec.get('verification_mode') == 'FORMAL_REQUIRED' and not isinstance(spec.get('formal_target'), dict):
        raise ValueError('FORMAL_REQUIRED needs formal_target file/declaration')
    if 'formal_target' in spec:
        target = spec['formal_target']
        if not isinstance(target, dict) or set(target) != {'file', 'declaration'}: raise ValueError('Invalid formal_target')
        source = local_file(project, target['file'], roots={'proofs'})
        source.relative_to((project / 'proofs/lean').resolve())
        if source.suffix != '.lean': raise ValueError('formal_target must name a Lean source')
        text(target['declaration'], 'formal declaration')
    text(reason, 'claim import reason')
    problem = get_problem(project, spec.get('problem_id'), spec.get('problem_version'))
    if spec.get('problem_version') != problem['version']: raise ValueError('Claim must pin an exact problem_version')
    if not set(spec['obligation_ids']) <= {o['id'] for o in problem['spec']['obligations']}:
        raise ValueError('Claim lists obligations outside its problem')
    if 'machine_statement' in spec:
        from .falsification import validate_statement
        validate_statement(spec['machine_statement'])
    bindings = evidence(project, spec.get('evidence_paths'))
    graph = load(project); by_id = {c['id']: c for c in graph['claims']}
    if len(spec['dependencies']) != len(set(spec['dependencies'])): raise ValueError('Duplicate claim dependency')
    for dep in spec['dependencies']:
        identifier(dep)
        if dep not in by_id: raise ValueError('Import dependencies first: ' + dep)
    proposed = {key: value['spec']['dependencies'] for key, value in by_id.items()}
    proposed[cid] = spec['dependencies']
    visiting = set(); done = set()
    def visit(key):
        if key in visiting: raise ValueError('Claim dependency graph must be acyclic')
        if key in done: return
        visiting.add(key)
        for dep in proposed[key]: visit(dep)
        visiting.remove(key); done.add(key)
    for key in proposed: visit(key)
    old = by_id.get(cid)
    digest = object_hash(spec)
    dep_pins = {d: {'revision': by_id[d]['revision'], 'spec_sha256': by_id[d]['spec_sha256']} for d in spec['dependencies']}
    knowledge_pins = {}
    if spec.get('knowledge_dependencies'):
        from .knowledge_graph import pin_dependencies
        knowledge_pins = pin_dependencies(project, spec['knowledge_dependencies'])
    current_binding = goal_binding(project)
    if old and old['spec_sha256'] == digest and old['evidence'] == bindings and old['dependency_pins'] == dep_pins and old.get('knowledge_pins', {}) == knowledge_pins and old['binding'] == current_binding and not old.get('invalidated'):
        raise ValueError('Unchanged claim; no artificial revision')
    item = {'id': cid, 'revision': old['revision'] + 1 if old else 1,
        'spec': copy.deepcopy(spec), 'spec_sha256': digest, 'evidence': bindings,
        'binding': current_binding, 'problem_sha256': problem['spec_sha256'],
        'dependency_pins': dep_pins,
        'reviews': {}, 'invalidated': None, 'formal_receipt': None, 'counterexample_receipt': None,
        'imported_at': stamp(),
        'history': (old.get('history', []) + [{k: copy.deepcopy(v) for k, v in old.items() if k != 'history'}]) if old else []}
    if 'knowledge_dependencies' in spec:
        item['knowledge_pins'] = knowledge_pins
    if old:
        graph['claims'][graph['claims'].index(old)] = item
    else: graph['claims'].append(item)
    graph['events'].append({'type': 'CLAIM_REVISED' if old else 'CLAIM_IMPORTED', 'id': cid,
                            'revision': item['revision'], 'reason': reason, 'at': stamp()})
    save(project, graph)
    refresh(project)
    return item


def receipt_fresh(project, item, receipt):
    if isinstance(receipt, dict) and receipt.get('output_file'):
        try:
            path = __import__('pathlib').Path(receipt['output_file'])
            path.resolve().relative_to((configuration.ROOT / 'logs').resolve())
            if hash_file(path) != receipt.get('output_sha256'): return False
        except (OSError, ValueError): return False
    return (isinstance(receipt, dict) and receipt.get('claim_revision') == item['revision']
            and receipt.get('claim_sha256') == item['spec_sha256']
            and fresh(project, receipt.get('source_bindings', {})))


def status(project):
    graph = load(project); by_id = {c['id']: c for c in graph['claims']}; results = {}
    binding = goal_binding(project) if by_id else None
    visiting = set()
    def compute(cid):
        if cid in results: return results[cid]
        if cid in visiting: raise ValueError('Corrupt cyclic claim graph')
        visiting.add(cid)
        item = by_id[cid]; spec = item['spec']; reasons = []
        if item.get('invalidated'): reasons.append(item['invalidated']['reason'])
        if object_hash(spec) != item['spec_sha256']: reasons.append('CLAIM_DIGEST_CHANGED')
        if binding != item['binding']: reasons.append('GOAL_OR_CONSTRAINTS_CHANGED')
        if not fresh(project, item['evidence']): reasons.append('EVIDENCE_CHANGED')
        knowledge_pins = item.get('knowledge_pins', {})
        if not isinstance(knowledge_pins, dict):
            reasons.append('KNOWLEDGE_BINDING_INVALID')
            knowledge_pins = {}
        if set(knowledge_pins) != set(spec.get('knowledge_dependencies', [])):
            reasons.append('KNOWLEDGE_BINDING_MISMATCH')
        if knowledge_pins:
            from .knowledge_graph import dependency_reasons
            reasons.extend(dependency_reasons(project, knowledge_pins, graph=graph))
        try:
            problem = get_problem(project, spec['problem_id'], spec['problem_version'])
            if problem['spec_sha256'] != item['problem_sha256'] or not fresh(project, problem['source_bindings']):
                reasons.append('PROBLEM_OR_SOURCE_CHANGED')
        except (OSError, ValueError, KeyError): reasons.append('PROBLEM_UNAVAILABLE')
        for dep, pin in item['dependency_pins'].items():
            parent = by_id.get(dep)
            if parent is None: reasons.append('DEPENDENCY_MISSING:' + dep); continue
            if pin != {'revision': parent['revision'], 'spec_sha256': parent['spec_sha256']}:
                reasons.append('DEPENDENCY_REVISED:' + dep)
            if compute(dep)['proof_status'] != 'INDEPENDENTLY_REVIEWED':
                reasons.append('DEPENDENCY_NOT_VALID:' + dep)
        reviews = item['reviews']
        def reviewed(kind):
            r = reviews.get(kind, {})
            return bool(r) and r.get('claim_sha256') == item['spec_sha256'] and fresh(project, r.get('evidence', {}))
        counterexample = item.get('counterexample_receipt')
        if counterexample and receipt_fresh(project, item, counterexample): reasons.append('MACHINE_STATEMENT_REFUTED')
        formal = item.get('formal_receipt')
        tool_ok = receipt_fresh(project, item, formal) and formal.get('status') == 'TOOL_PASSED_AUDIT_PENDING'
        formal_review = reviews.get('formal_audit', {})
        formal_ok = tool_ok and reviewed('formal_audit') and formal_review.get('receipt_sha256') == object_hash(formal)
        manual_ok = reviewed('proof') and reviewed('statement')
        proven = not reasons and (formal_ok or manual_ok)
        novelty_ok = reviewed('novelty') and not reasons
        required_formal = policy(project)['formal_verification'] == 'required' or spec['verification_mode'] == 'FORMAL_REQUIRED'
        if required_formal and not formal_ok: proven = False
        accepted = proven and novelty_ok and (formal_ok or not required_formal)
        result = {'id': cid, 'revision': item['revision'], 'spec_sha256': item['spec_sha256'],
            'problem_id': spec['problem_id'], 'problem_version': spec['problem_version'],
            'statement': spec['statement'], 'obligation_ids': spec['obligation_ids'],
            'proof_status': 'INDEPENDENTLY_REVIEWED' if proven else 'PENDING_REVALIDATION' if reasons else 'CANDIDATE',
            'formal_status': 'AUDITED_TOOL_CHECK' if formal_ok and not reasons else 'TOOL_CHECKED_STATEMENT_PENDING' if tool_ok else 'NOT_VERIFIED',
            'novelty_status': 'REVIEWED_THEORETICAL_CONTRIBUTION' if novelty_ok else 'PENDING',
            'accepted_contribution': accepted, 'invalidation_reasons': reasons,
            'review_scope': 'Operator-attested review; automated structure checks do not prove research truth'}
        results[cid] = result; visiting.remove(cid)
        return result
    for cid in by_id: compute(cid)
    return {'schema_version': 1, 'claims': [results[c['id']] for c in graph['claims']]}


def refresh(project):
    graph = load(project)
    current = status(project)
    changed = False
    for result in current['claims']:
        item = next(c for c in graph['claims'] if c['id'] == result['id'])
        summary = {'proof_status': result['proof_status'], 'reasons': result['invalidation_reasons']}
        if item.get('last_validity') != summary:
            item['last_validity'] = summary; changed = True
            graph['events'].append({'type': 'VALIDITY_CHANGED', 'id': result['id'], **summary, 'at': stamp()})
    if changed: save(project, graph)
    return current


def review(project, claim_id, kind, evidence_path, reviewer, reason):
    if kind == 'proof_and_statement':
        review(project, claim_id, 'proof', evidence_path, reviewer, reason)
        return review(project, claim_id, 'statement', evidence_path, reviewer, reason)
    text(reviewer, 'reviewer'); text(reason, 'review reason')
    graph = load(project); item = next((c for c in graph['claims'] if c['id'] == claim_id), None)
    if item is None: raise ValueError('Unknown claim')
    if reviewer.strip().casefold() == item['spec']['proposer'].strip().casefold():
        raise ValueError('Claim proposer cannot attest its own independent review')
    if kind not in {'proof', 'statement', 'novelty', 'formal_audit'}: raise ValueError('Invalid review kind')
    bindings = evidence(project, [evidence_path])
    receipt_sha = None
    if kind == 'novelty':
        report = read_object(local_file(project, evidence_path))
        if report.get('claim_id') != claim_id or report.get('claim_sha256') != item['spec_sha256']:
            raise ValueError('Novelty review must bind exact claim ID and spec_sha256')
        if report.get('verdict') != 'NEW_THEORETICAL_CONTRIBUTION': raise ValueError('Novelty is unresolved or covered')
        for field in ('nontriviality_argument', 'novelty_mechanism', 'search_scope'): text(report.get(field), field)
        paths = strings(report.get('technical_reviews'), 'technical_reviews')
        for rel in paths:
            technical = validate_technical_review(project, rel, claim_id)
            if technical.get('fulltext_status') != 'TECHNICALLY_CHECKED' or technical['coverage_verdict'] in {'COVERS', 'CONTRADICTS', 'UNVERIFIED'}:
                raise ValueError('Novelty requires full technical comparison without known coverage/conflict')
            refs = [rel, technical['paper']['source_file']] + technical.get('derivation_paths', [])
            bindings.update(evidence(project, refs))
    if kind == 'formal_audit':
        formal = item.get('formal_receipt')
        if not receipt_fresh(project, item, formal) or formal.get('status') != 'TOOL_PASSED_AUDIT_PENDING':
            raise ValueError('No current successful formal verifier receipt to audit')
        report = read_object(local_file(project, evidence_path))
        receipt_sha = object_hash(formal)
        if report.get('claim_id') != claim_id or report.get('receipt_sha256') != receipt_sha:
            raise ValueError('Formal audit must bind the exact verifier receipt')
        if report.get('verdict') != 'MATCHED_AND_AUDITED': raise ValueError('Formal statement/axioms audit not passed')
        for field in ('statement_mapping', 'axioms_argument', 'dependency_scope'): text(report.get(field), field)
        strings(report.get('allowed_axioms'), 'allowed_axioms', empty=True)
        if any('sorry' in a.casefold() for a in report['allowed_axioms']): raise ValueError('sorryAx is never allowed')
    item['reviews'][kind] = {'reviewer': reviewer, 'reason': reason, 'at': stamp(),
        'claim_sha256': item['spec_sha256'], 'evidence': bindings, 'receipt_sha256': receipt_sha}
    graph['events'].append({'type': 'INDEPENDENT_REVIEW', 'id': claim_id, 'kind': kind, 'reviewer': reviewer, 'at': stamp()})
    save(project, graph)
    return refresh(project)


def invalidate(project, claim_id, reason):
    text(reason, 'invalidation reason')
    graph = load(project)
    item = next((c for c in graph['claims'] if c['id'] == claim_id), None)
    if item is None: raise ValueError('Unknown claim')
    item['invalidated'] = {'reason': reason, 'at': stamp()}
    graph['events'].append({'type': 'CLAIM_INVALIDATED', 'id': claim_id, 'reason': reason, 'at': stamp()})
    save(project, graph)
    return refresh(project)


def record_tool(project, claim_id, field, receipt):
    graph = load(project); item = next(c for c in graph['claims'] if c['id'] == claim_id)
    if receipt['claim_sha256'] != item['spec_sha256'] or receipt['claim_revision'] != item['revision']:
        raise ValueError('Claim changed during verification')
    item[field] = receipt
    graph['events'].append({'type': 'TOOL_RESULT', 'id': claim_id, 'status': receipt['status'], 'at': stamp()})
    save(project, graph)
    return refresh(project)


def require_theory_claim(project, claim_id):
    graph = load(project)
    if not graph['claims']:
        from .problem_compiler import pool
        if pool(project)['problems']: raise ValueError('Discovery problems exist but no independently reviewed claim is registered')
        return None
    current = status(project)['claims']
    item = next((c for c in current if c['id'] == claim_id), None)
    if item is None or not item['accepted_contribution']:
        raise ValueError('Discovery claim has not passed correctness, statement and theorem-level novelty review')
    problem = get_problem(project, item['problem_id'], item['problem_version'])
    covered = set()
    # Only declared dependencies of the approved claim can close its problem obligations.
    by_id = {c['id']: c for c in graph['claims']}; closure = set()
    def visit(cid):
        if cid in closure: return
        closure.add(cid)
        for dep in by_id[cid]['spec']['dependencies']: visit(dep)
    visit(claim_id)
    for candidate in current:
        if candidate['id'] in closure and candidate['proof_status'] == 'INDEPENDENTLY_REVIEWED' and candidate['problem_id'] == item['problem_id'] and candidate['problem_version'] == item['problem_version']:
            covered.update(candidate['obligation_ids'])
    if covered != {o['id'] for o in problem['spec']['obligations']}:
        raise ValueError('Critical problem obligations remain open in the approved claim dependency closure')
    return item
