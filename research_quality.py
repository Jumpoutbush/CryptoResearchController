"""Evidence requirements for research receipts and route decisions.

Checks provenance, decision consistency and declared obligations; semantic
validity of cryptographic statements remains subject to technical review.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from configuration import settings_for

CORE_TYPES = {
    'CRYPTOGRAPHIC_PRIMITIVE', 'SECURITY_DEFINITION', 'PROTOCOL_CONSTRUCTION',
    'SECURITY_THEOREM', 'REDUCTION_OR_SEPARATION', 'COMPLEXITY_THEOREM',
    'LOWER_BOUND_OR_IMPOSSIBILITY',
}
WORK_KINDS = {'CORE_RESEARCH', 'LITERATURE_AUDIT', 'PROOF', 'COUNTEREXAMPLE',
              'COST_BOUND', 'ENGINEERING_SUPPORT', 'EXECUTION_DIAGNOSIS', 'SYSTEM_IMPLEMENTATION', 'SYSTEM_TEST'}
SUPPORT_KINDS = {'ENGINEERING_SUPPORT', 'EXECUTION_DIAGNOSIS'}
RESULTS = {'OPEN', 'CONDITIONAL', 'PROOF_PENDING_REVIEW', 'REFUTED',
           'TECHNICALLY_COMPARED', 'SUPPORT_ONLY', 'NO_PROGRESS'}
FAILURE_CLASSES = {'LITERATURE_COVERAGE', 'COUNTEREXAMPLE', 'SECURITY_BREAK',
                   'COST_OBSTRUCTION', 'PROOF_OPEN', 'BUDGET_EXHAUSTED',
                   'EXECUTION_FAILURE', 'INSUFFICIENT_EVIDENCE'}
DECISIVE_CLASSES = {'LITERATURE_COVERAGE', 'COUNTEREXAMPLE', 'SECURITY_BREAK', 'COST_OBSTRUCTION'}
DIMENSIONS = {'functionality', 'adversary', 'assumptions', 'output_interface', 'parameters', 'cost'}
RELATIONS = {'MATCH', 'PAPER_STRONGER', 'IDEA_STRONGER', 'INCOMPARABLE', 'UNRESOLVED', 'NOT_APPLICABLE'}
COVERAGE = {'UNVERIFIED', 'RELATED', 'PARTIAL_OVERLAP', 'COVERS', 'CONTRADICTS', 'INCOMPARABLE'}


def read_object(path):
    value = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict): raise ValueError(f'Expected JSON object: {path}')
    return value


def present(value):
    return isinstance(value, str) and bool(value.strip())


def local_file(project, relative, *, roots=None):
    if not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative:
        raise ValueError('Evidence must use a project-relative forward-slash path')
    path = (project / relative).resolve()
    path.relative_to(project.resolve())
    if Path(relative).is_absolute() or path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
        raise ValueError('Evidence file missing or invalid: ' + relative)
    if roots and path.relative_to(project.resolve()).parts[0] not in roots:
        raise ValueError('Evidence is outside scientific evidence directories: ' + relative)
    return path


def hash_file(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()


def policy_for(project):
    return settings_for(project)['research_policy']


def scientific_files(project, paths):
    if not isinstance(paths, list) or not paths:
        raise ValueError('At least one scientific evidence file is required')
    denied = {'STATE.json', 'ROUND_REVIEW.json', 'ROUTE_SIGNAL.json', 'ROUTE_VERDICT.json'}
    found = []
    for relative in paths:
        path = local_file(project, relative, roots={'proofs', 'experiments', 'literature', 'research'})
        if path.name in denied:
            raise ValueError('A scheduling receipt cannot be its own scientific evidence')
        found.append((relative, path))
    return found


def validate_round(project, run_id, before_hashes=None):
    policy = policy_for(project)
    path = project / 'research/ROUND_REVIEW.json'
    if not policy['require_round_review']:
        return {'required': False, 'work_kind': 'UNCLASSIFIED', 'result_status': 'OPEN'}
    record = read_object(path)
    if record.get('schema_version') != 1 or record.get('run_id') != run_id:
        raise ValueError('ROUND_REVIEW must bind this run_id and schema_version=1')
    if record.get('work_kind') not in WORK_KINDS: raise ValueError('Unknown research work_kind')
    if record.get('result_status') not in RESULTS: raise ValueError('Unknown research result_status')
    for key in ('core_problem', 'theoretical_obligation', 'nontriviality_argument'):
        if not present(record.get(key)): raise ValueError('ROUND_REVIEW missing ' + key)
    kind = record.get('contribution_type')
    if kind not in CORE_TYPES | {'NONE'}: raise ValueError('Unknown contribution_type')
    if record['work_kind'] in {'SYSTEM_IMPLEMENTATION','SYSTEM_TEST'}:
        from theory_gate import require_system_ready
        approval = require_system_ready(project)
        if approval is not None and record.get('supports_claim') != approval['claim_id']:
            raise ValueError('System work must name the operator-approved claim')
    if record['work_kind'] in SUPPORT_KINDS | {'SYSTEM_IMPLEMENTATION','SYSTEM_TEST'}:
        if record['result_status'] not in {'SUPPORT_ONLY', 'NO_PROGRESS'} or kind != 'NONE':
            raise ValueError('Engineering work must stay SUPPORT_ONLY/NO_PROGRESS with contribution_type=NONE')
        for key in ('supports_claim', 'blocking_obligation'):
            if not present(record.get(key)): raise ValueError('Supporting work requires ' + key)
    if record['result_status'] == 'NO_PROGRESS':
        if record.get('evidence_paths') not in ([], None): scientific_files(project, record['evidence_paths'])
    else:
        files = scientific_files(project, record.get('evidence_paths'))
        if before_hashes is not None and not any(hash_file(p) != before_hashes.get(rel) for rel, p in files):
            raise ValueError('ROUND_REVIEW cites no new or changed scientific evidence')
    return record


def validate_technical_review(project, relative, claim_id=None, *, decisive=False):
    path = local_file(project, relative, roots={'literature'})
    record = read_object(path)
    if record.get('schema_version') != 1: raise ValueError('Technical review schema_version must be 1')
    for field in ('claim_id', 'author_claim', 'technical_statement', 'source_location',
                  'construction_mapping', 'reduction_argument', 'limitations'):
        if not present(record.get(field)): raise ValueError('Technical review missing ' + field)
    if claim_id is not None and record.get('claim_id') != claim_id:
        raise ValueError('Technical review addresses a different claim')
    paper = record.get('paper', {})
    if not isinstance(paper, dict) or not all(present(paper.get(k)) for k in ('title', 'version', 'source_file', 'sha256')):
        raise ValueError('Paper identity needs title/version/source_file/sha256')
    source = local_file(project, paper['source_file'], roots={'literature'})
    if source == path: raise ValueError('Technical review cannot serve as its own primary source')
    if hash_file(source) != paper['sha256']: raise ValueError('Primary-source hash mismatch')
    rows = record.get('comparison', [])
    if not isinstance(rows, list): raise ValueError('Technical comparison must be a list')
    mapped = {}
    for row in rows:
        if not isinstance(row, dict) or row.get('dimension') not in DIMENSIONS:
            raise ValueError('Invalid technical comparison dimension')
        if row['dimension'] in mapped: raise ValueError('Duplicate comparison dimension')
        if row.get('relation') not in RELATIONS: raise ValueError('Invalid comparison relation')
        if not all(present(row.get(k)) for k in ('idea', 'paper', 'source_location', 'argument')):
            raise ValueError('Each dimension needs both technical statements, source location and argument')
        mapped[row['dimension']] = row
    if set(mapped) != DIMENSIONS: raise ValueError('Technical review must compare all six dimensions')
    verdict = record.get('coverage_verdict')
    if verdict not in COVERAGE: raise ValueError('Unknown technical coverage verdict')
    # Store related papers in the baseline without using them to kill a claim.
    if decisive:
        if record.get('fulltext_status') != 'TECHNICALLY_CHECKED':
            raise ValueError('A literature pivot requires technical full-text review')
        if verdict not in {'COVERS', 'CONTRADICTS'}:
            raise ValueError('Related or partial overlap cannot justify a literature pivot')
        if verdict == 'COVERS' and any(mapped[d]['relation'] == 'NOT_APPLICABLE' for d in ('functionality','adversary','assumptions','output_interface')):
            raise ValueError('Core coverage dimensions must be technically compared')
        if verdict == 'COVERS' and any(r['relation'] in {'IDEA_STRONGER', 'INCOMPARABLE', 'UNRESOLVED'} for r in mapped.values()):
            raise ValueError('Unresolved/stronger idea conditions contradict full coverage')
        if verdict == 'CONTRADICTS':
            if not present(record.get('contradicted_statement')):
                raise ValueError('A contradiction needs the exact contradicted statement')
            if any(mapped[d]['relation'] in {'INCOMPARABLE', 'UNRESOLVED'} for d in ('functionality','adversary','assumptions','output_interface')):
                raise ValueError('Contradiction has unresolved core assumptions')
        derived = scientific_files(project, record.get('derivation_paths'))
        if any(p == path or p == source for _, p in derived):
            raise ValueError('Coverage requires a separate derivation artifact')
    return record


def validate_candidate(project, candidate):
    if not policy_for(project)['require_theory_candidate_for_pivot']: return
    contribution = candidate.get('theoretical_contribution')
    if not isinstance(contribution, dict) or contribution.get('type') not in CORE_TYPES:
        raise ValueError('Candidate needs an allowed theoretical_contribution type')
    for field in ('statement', 'novelty_mechanism', 'closest_prior_work', 'nontriviality_argument', 'proof_obligation'):
        if not present(contribution.get(field)): raise ValueError('Theoretical candidate missing ' + field)
    scientific_files(project, contribution.get('evidence_paths'))


def validate_route_decision(project, verdict):
    policy = policy_for(project)
    if verdict.get('outcome') not in {'PIVOT_PROVISIONAL', 'REJECT_SCOPE_LIMITED'}:
        return
    if not policy['require_decisive_evidence_for_pivot']: return
    category = verdict.get('failure_class')
    if category not in DECISIVE_CLASSES:
        raise ValueError('Budget exhaustion, open proof or execution failure cannot automatically reject/pivot the main route')
    for field in ('failed_claim', 'failure_scope', 'scope_argument'):
        if not present(verdict.get(field)): raise ValueError('Route rejection missing ' + field)
    if verdict['failure_scope'] != 'CORE_ROUTE':
        raise ValueError('A subclaim conflict cannot automatically replace the whole main route')
    if not present(verdict.get('dependency_argument')):
        raise ValueError('A route pivot must explain why the failed claim is necessary to the core route')
    scientific_files(project, verdict.get('evidence_paths'))
    if category == 'LITERATURE_COVERAGE':
        validate_technical_review(project, verdict.get('technical_review'), verdict['failed_claim'], decisive=True)
    else:
        required = ('satisfied_preconditions', 'violated_conclusion') if category in {'COUNTEREXAMPLE','SECURITY_BREAK'} else ('cost_model', 'baseline_comparison', 'obstruction_argument')
        for field in required:
            if not present(verdict.get(field)): raise ValueError('Decisive witness missing ' + field)


def prompt_contract(*, technical_review=False):
    content = '''# Research quality receipt (required this round)
Save research/ROUND_REVIEW.json with schema_version=1 and this run_id.
Fields: work_kind (CORE_RESEARCH/LITERATURE_AUDIT/PROOF/COUNTEREXAMPLE/COST_BOUND/ENGINEERING_SUPPORT/EXECUTION_DIAGNOSIS/SYSTEM_IMPLEMENTATION/SYSTEM_TEST), core_problem, theoretical_obligation, nontriviality_argument, contribution_type (CRYPTOGRAPHIC_PRIMITIVE/SECURITY_DEFINITION/PROTOCOL_CONSTRUCTION/SECURITY_THEOREM/REDUCTION_OR_SEPARATION/COMPLEXITY_THEOREM/LOWER_BOUND_OR_IMPOSSIBILITY/NONE), result_status (OPEN/CONDITIONAL/PROOF_PENDING_REVIEW/REFUTED/TECHNICALLY_COMPARED/SUPPORT_ONLY/NO_PROGRESS), evidence_paths.
For support work also supply supports_claim and blocking_obligation; use contribution_type=NONE and SUPPORT_ONLY/NO_PROGRESS. Never manufacture a primitive/theorem to fill this receipt. State the unresolved obligation precisely. If no scientific evidence was produced, use NO_PROGRESS with evidence_paths=[].
Follow the controller focus anchor: include goal_impact with anchor_id, scope (CORE/DIRECT_DEPENDENCY/SUPPORT), target_obligation, before, after, next_mainline_task. DIRECT_DEPENDENCY also needs consumer_claim and dependency_argument identifying a direct use in the main construction or its decisive exclusion. SUPPORT_ONLY cannot reset mainline stagnation even when work_kind is PROOF or COUNTEREXAMPLE. A necessary core refutation or intermediate proof may keep contribution_type=NONE; explain its actual impact without inventing novelty. The controller verifies bindings, not semantic relevance or mathematical truth.
Theory-first: before user-approved theory readiness, do not write system implementations, integration harnesses or benchmarks. System phases IMPLEMENTATION/SYSTEM_TEST/EXPERIMENT require research/THEORY_READINESS.json created by the operator's theory approve command. You cannot approve yourself or edit this file. Minimal mathematical checks only: proofs/checks/ or experiments/math_checks/, with research/MATH_CHECK_PLAN.json (question,why_code_is_necessary,success_criterion,failure_criterion,files,max_seconds), at most 2 changed source files,160 lines total,10 seconds per check by default. Prefer a direct proof or counterexample derivation when it suffices.
Candidate route pivots require a theoretical_contribution object: type, statement, novelty_mechanism, closest_prior_work, nontriviality_argument, proof_obligation, evidence_paths. Standard compilation, background substitution, parameter tuning, benchmarks and implementation integration alone are support work.
For PIVOT_PROVISIONAL/REJECT_SCOPE_LIMITED also provide failure_class (LITERATURE_COVERAGE/COUNTEREXAMPLE/SECURITY_BREAK/COST_OBSTRUCTION), failed_claim, failure_scope=CORE_ROUTE, scope_argument, dependency_argument, evidence_paths. Counterexample/security failure requires satisfied_preconditions and violated_conclusion; cost obstruction requires cost_model, baseline_comparison and obstruction_argument.
Literature pivots additionally name technical_review (JSON under literature/): schema_version=1, claim_id matching failed_claim, paper {title,version,source_file,sha256}, fulltext_status=TECHNICALLY_CHECKED, author_claim, technical_statement, source_location, comparison (six rows: functionality,adversary,assumptions,output_interface,parameters,cost; each row has idea,paper,relation,source_location,argument), construction_mapping,reduction_argument,limitations,coverage_verdict,derivation_paths. Relations: MATCH/PAPER_STRONGER/IDEA_STRONGER/INCOMPARABLE/UNRESOLVED/NOT_APPLICABLE. Coverage: UNVERIFIED/RELATED/PARTIAL_OVERLAP/COVERS/CONTRADICTS/INCOMPARABLE; CONTRADICTS also needs contradicted_statement.
A paper's own novelty or security claim is not evidence of coverage. Compare the actual construction, theorem, proof conditions and costs. A related paper may enter the baseline before coverage is established. Unknown/fulltext-pending/partial overlap preserves the current main idea and schedules targeted verification. Budget exhaustion permits review, extension or pause, not an unsupported scientific rejection.
'''
    if technical_review: return content
    return content[:content.index('Candidate route pivots require')] + '\nRoute decisions and literature coverage use method/12 and method/15; a full decision schema is loaded during technical-literature and route-review rounds.\n'
