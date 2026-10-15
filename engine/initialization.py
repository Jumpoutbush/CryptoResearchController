"""Idea-driven initialization receipts. These checks verify completeness and provenance."""
from __future__ import annotations
import json
import configuration
from research_quality import hash_file, local_file, read_object
from .common import goal_binding, strings, text
from .problem_compiler import validate as validate_problem

DOCUMENTS = (
    'research/INTAKE.md', 'research/PROJECT_BRIEF.md', 'research/NOTATION.md',
    'research/CONTRIBUTION.md', 'research/THREAT_MODEL.md', 'research/COST_MODEL.md',
    'research/PROOF_OBLIGATIONS.json', 'research/BASELINES.md', 'research/OPEN_PROBLEMS.md',
    'research/PROBLEM_PROPOSAL.json', 'research/ROADMAP.md', 'literature/SEARCH_PLAN.json',
)


def input_bindings(project):
    binding = goal_binding(project)
    # Generated security/cost drafts are outputs, not user source evidence.
    sources = {rel: sha for rel, sha in binding['files'].items() if not rel.startswith('research/')}
    for path in (project / 'literature/pdfs').rglob('*'):
        if path.is_file(): sources[path.relative_to(project).as_posix()] = hash_file(path)
    return sources


def context(project, state):
    if state.get('initialization_required'):
        path = project / 'prompts/initialize_from_idea.md'
        if not path.is_file(): path = configuration.ROOT / 'templates/project/prompts/initialize_from_idea.md'
        source = path.read_text(encoding='utf-8-sig')
        return source + '\n\n# Exact initialization source hashes\n' + json.dumps(input_bindings(project), ensure_ascii=False, indent=2) + '\n\n# Required documents\n' + '\n'.join(DOCUMENTS)
    manifest = configuration.load_json(project / 'research/INITIALIZATION.json', None)
    if manifest is None: return ''
    from .common import fresh
    valid = manifest.get('source_bindings') == input_bindings(project)
    return ('# Derived project initialization (drafts require evidence and review)\n'
        + ('INPUTS_UNCHANGED: document hashes describe the initial snapshot; inspect current research files for later progress'
           if valid else 'INPUTS_CHANGED: review which initialized assumptions are affected')
        + '\n' + json.dumps(manifest, ensure_ascii=False, indent=2))


def validate(project, run_id):
    obj = read_object(project / 'research/INITIALIZATION.json')
    if obj.get('schema_version') != 1 or obj.get('run_id') != run_id: raise ValueError('Initialization needs this fresh run_id')
    if obj.get('status') not in {'READY_FOR_PROBLEM_REVIEW', 'NEEDS_INPUT'}:
        raise ValueError('Initialization may not certify a contribution or theorem')
    if obj.get('source_bindings') != input_bindings(project): raise ValueError('Initialization source bindings mismatch')
    docs = obj.get('documents')
    if not isinstance(docs, list) or {d.get('file') for d in docs if isinstance(d, dict)} != set(DOCUMENTS) or len(docs) != len(DOCUMENTS):
        raise ValueError('Initialization must cover every required document exactly once')
    for entry in docs:
        path = local_file(project, entry['file'])
        if path.stat().st_size < 80 or hash_file(path) != entry.get('sha256'): raise ValueError('Initialization document missing, too short or digest mismatch: ' + entry['file'])
        if entry.get('status') not in {'DRAFT', 'NEEDS_INPUT'}: raise ValueError('Generated docs must remain drafts or explicit gaps')
        refs = strings(entry.get('source_paths'), 'source_paths')
        if not set(refs) <= set(obj['source_bindings']): raise ValueError('Initialization sources must reference supplied user material/instructions')
    missing = obj.get('unresolved_inputs')
    if not isinstance(missing, list): raise ValueError('unresolved_inputs must be a list')
    for item in missing:
        text(item.get('question'), 'missing input question')
        if type(item.get('blocking')) is not bool: raise ValueError('Each input gap needs a blocking boolean')
    if any(d['status'] == 'NEEDS_INPUT' for d in docs) and not missing:
        raise ValueError('NEEDS_INPUT documents require explicit unresolved questions')
    if obj['status'] == 'READY_FOR_PROBLEM_REVIEW' and any(i['blocking'] for i in missing):
        raise ValueError('Blocking input gaps prevent READY_FOR_PROBLEM_REVIEW')
    if obj['status'] == 'NEEDS_INPUT' and not any(i['blocking'] for i in missing):
        raise ValueError('NEEDS_INPUT requires at least one explicit blocking question')
    if obj['status'] == 'READY_FOR_PROBLEM_REVIEW': validate_problem(read_object(project / 'research/PROBLEM_PROPOSAL.json'))
    obligations = read_object(project / 'research/PROOF_OBLIGATIONS.json')
    if not isinstance(obligations.get('obligations'), list) or not obligations['obligations']:
        raise ValueError('Initialization needs nonempty, unresolved proof obligations')
    for obligation in obligations['obligations']:
        if not isinstance(obligation, dict) or obligation.get('status') not in {'OPEN', 'NEEDS_INPUT'}:
            raise ValueError('Initialization cannot self-certify proof obligations')
        text(obligation.get('id'), 'obligation id'); text(obligation.get('statement'), 'obligation statement')
    search = read_object(project / 'literature/SEARCH_PLAN.json')
    queries = strings(search.get('queries'), 'search queries')
    if len(queries) > 8 or any(not 4 <= len(q) <= 300 for q in queries): raise ValueError('Need 1..8 bounded literature queries')
    state = read_object(project / 'research/STATE.json')
    if state.get('initialization_required') is not False or state.get('initialization_status') != obj['status']:
        raise ValueError('STATE must acknowledge completed initialization and its unresolved status')
    if state.get('phase') != 'INTAKE': raise ValueError('Initialization must keep INTAKE until the precise problem is reviewed')
    if obj['status'] == 'NEEDS_INPUT' and state.get('decision') != 'PAUSE':
        raise ValueError('Initialization with blocking uncertainty must pause for input')
    return obj


def finalize(project, run_id):
    obj = validate(project, run_id)
    path = project / 'literature/queries.json'
    current = configuration.load_json(path, {})
    if current.get('generated_initial_query') is True:
        search = read_object(project / 'literature/SEARCH_PLAN.json')
        current.update(queries=search['queries'], generated_initial_query=False,
                       initialized_from_run=run_id)
        configuration.atomic_json(path, current)
    return obj
