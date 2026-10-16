"""R01 deterministic project snapshots; never initialise state or call a model.

Only explicit scientific references and fixed instruction files are selected.
Text is untrusted data. Trust labels describe scoped controller receipts, not
independent mathematical verification performed by this reader.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re

import configuration
from research_focus import make_focus
from supervision_contracts import canonical_hash, load_defaults, validate_defaults

MAX_READ = 4 * 1024 * 1024
PER_FILE = 65536
RUN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,159}$')
TEXT = {'.md', '.json', '.txt', '.tex', '.bib', '.lean', '.py', '.csv', '.tsv', '.sage'}
ROOTS = {'proofs', 'research', 'literature', 'experiments', 'inputs', 'ideas', 'reports'}
FIXED = ('PROJECT.json', 'GOAL.md', 'AGENTS.md', 'prompts/continue.md', 'RESEARCH_PROFILE.json',
         'research/STATE.json', 'research/PROOF_OBLIGATIONS.json', 'research/THREAT_MODEL.md',
         'research/SECURITY_MODEL.md', 'research/SECURITY_DEFINITIONS.md',
         'research/discovery/CLAIM_GRAPH.json', 'research/discovery/PROBLEMS.json',
         'literature/NOVELTY_GAP.md', 'literature/RELATED_WORK.md', 'reports/LATEST.md',
         'inputs/CONTEXT.md', 'inputs/NOTATION.md')
CONTROL = {'state.json', 'round_review.json', 'route_signal.json', 'route_verdict.json',
           'run_result.json', 'supervision_report.md', 'checkpoint.json', 'theory_readiness.json'}


def _path(root, relative):
    if (not isinstance(relative, str) or not relative or relative != relative.strip()
            or '\\' in relative or ':' in relative or '\x00' in relative
            or PurePosixPath(relative).is_absolute()
            or any(part in {'', '.', '..'} or part.endswith((' ', '.')) for part in relative.split('/'))):
        raise ValueError('Unsafe snapshot path')
    from runner_core import project_link
    path = Path(root).absolute()
    for component in [*reversed(path.parents), path]:
        if project_link(component): raise ValueError('Snapshot root cannot traverse a link or junction')
    for part in relative.split('/'):
        path = path / part
        if project_link(path): raise ValueError('Snapshot source cannot traverse a link or junction')
    path.resolve().relative_to(Path(root).resolve())
    return path


def _source_path(project, relative, *, fixed=False):
    path = _path(project, relative)
    parts = PurePosixPath(relative).parts
    forbidden = {'.env', '.env.local', '.env.production', 'credentials.json', 'secrets.json',
                 'auth.json', 'id_rsa', 'id_ed25519', 'config.toml'}
    if (any(part.casefold() in forbidden or part.casefold().startswith('.env.') for part in parts)
            or path.suffix.casefold() in {'.pem', '.key', '.pfx', '.p12'}):
        raise ValueError('Credentials and environment files cannot enter a snapshot')
    if not fixed:
        lowered = relative.casefold()
        if (parts[0] not in ROOTS or path.name.casefold() in CONTROL
                or lowered.startswith(('research/discovery/', 'research/supervision/'))):
            raise ValueError('Source is outside the scientific snapshot whitelist')
    return path


def _read(path):
    """Hash the whole source, keeping only bounded bytes for optional text."""
    digest, size, prefix = hashlib.sha256(), 0, bytearray()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(65536), b''):
            digest.update(block); size += len(block)
            if len(prefix) <= MAX_READ: prefix.extend(block[:MAX_READ + 1 - len(prefix)])
    return {'path_object': path, 'sha256': digest.hexdigest(), 'size_bytes': size, 'raw': bytes(prefix)}


def _json(source, label):
    if source['size_bytes'] > MAX_READ: raise ValueError('Required structured source exceeds read bound: ' + label)
    try: return json.loads(source['raw'].decode('utf-8-sig'))
    except (ValueError, UnicodeError) as exc: raise ValueError('Invalid structured snapshot source: ' + label) from exc


def _accepted(ledger, state):
    if (not isinstance(ledger, dict) or type(ledger.get('schema_version')) is not int
            or ledger['schema_version'] != 1 or not isinstance(ledger.get('epochs'), list)):
        raise ValueError('Invalid route receipt ledger')
    epochs = ledger['epochs']
    if not epochs: raise ValueError('Persisted route ledger has no real epoch')
    epoch = epochs[-1]
    if (not isinstance(epoch, dict) or type(epoch.get('epoch')) is not int or epoch['epoch'] < 1
            or epoch.get('route') != state.get('research_route')):
        raise ValueError('Route receipt does not match current research route')
    values = epoch.get('counted_run_ids')
    if values is None:
        values = [event.get('run_id') for event in ledger.get('events', [])
                  if event.get('type') == 'RESEARCH_ROUND' and event.get('route', epoch['route']) == epoch['route']]
    if not isinstance(values, list): raise ValueError('Invalid accepted run receipts')
    result = []
    for run in values:
        if not isinstance(run, str) or not RUN.fullmatch(run) or '..' in run:
            raise ValueError('Invalid accepted run ID')
        if run not in result: result.append(run)
    if (type(epoch.get('effective_rounds')) is not int or epoch['effective_rounds'] < len(result)
            or epoch.get('last_processed_run') != state.get('last_run')
            or type(epoch.get('review_pending', False)) is not bool):
        raise ValueError('Accepted route receipts conflict with round counts or current STATE')
    return epoch, result


def build_snapshot(project, *, last_n=3, defaults=None):
    """Read a project without creating ledgers, locks, caches or claim records.

    The canonical manifest and input hash omit filesystem times and capture
    clocks. GOAL is always complete; optional bodies have exact byte omissions.
    """
    if type(last_n) is not int or not 1 <= last_n <= 3: raise ValueError('last_n must be 1..3')
    defaults = load_defaults() if defaults is None else validate_defaults(defaults)
    controller = configuration.ROOT.resolve()
    project = Path(project).absolute()
    manifest_path = _path(project, 'PROJECT.json')
    if not manifest_path.is_file(): raise ValueError('Snapshot requires PROJECT.json identity')
    identity = _read(manifest_path); manifest = _json(identity, 'PROJECT.json')
    project_id = manifest.get('id') if isinstance(manifest, dict) else None
    if (not isinstance(project_id, str) or not configuration.ID_RE.fullmatch(project_id)
            or project.resolve() != controller / 'projects' / project_id):
        raise ValueError('Snapshot project identity differs from registered project path')
    selected, missing, expected = {}, [], {'PROJECT.json': identity['sha256']}
    selected['PROJECT.json'] = {**identity, 'path': 'PROJECT.json', 'scope': 'PROJECT',
        'trust': 'UNVERIFIED', 'evidence_eligible': False, 'verification_scopes': []}

    def add(relative, *, fixed=False, trust='UNVERIFIED', evidence=False, required=False):
        path = _source_path(project, relative, fixed=fixed)
        if not path.is_file():
            if required: raise ValueError('Required snapshot source missing: ' + relative)
            entry = {'scope': 'PROJECT', 'path': relative, 'reason': 'MISSING'}
            if entry not in missing: missing.append(entry)
            return None
        if relative not in selected:
            selected[relative] = {**_read(path), 'path': relative, 'scope': 'PROJECT',
                'trust': trust, 'evidence_eligible': evidence, 'verification_scopes': []}
        elif evidence:
            selected[relative]['evidence_eligible'] = True
            if selected[relative]['trust'] == 'UNVERIFIED': selected[relative]['trust'] = trust
        if len(selected) > 500: raise ValueError('Snapshot source count exceeds 500; narrow the declared evidence')
        return selected[relative]

    def external(relative):
        path = _path(controller, relative)
        if not path.is_file():
            missing.append({'scope': 'CONTROLLER', 'path': relative, 'reason': 'MISSING'})
            return None
        return {**_read(path), 'path': relative, 'scope': 'CONTROLLER', 'trust': 'UNVERIFIED',
                'evidence_eligible': False, 'verification_scopes': [], 'metadata_only': True}

    goal = add('GOAL.md', fixed=True, required=True, trust='USER_FROZEN')
    if not goal['size_bytes'] or goal['size_bytes'] > defaults['max_snapshot_bytes']:
        raise ValueError('Frozen GOAL cannot be read completely within the snapshot bound')
    try: goal['raw'].decode('utf-8-sig')
    except UnicodeError as exc: raise ValueError('Frozen GOAL must be complete UTF-8') from exc
    state = _json(add('research/STATE.json', fixed=True, required=True), 'research/STATE.json')
    if not isinstance(state, dict): raise ValueError('STATE must be a real object')
    add('PROJECT.json', fixed=True, required=True)
    for relative in FIXED:
        if relative not in selected: add(relative, fixed=True)

    controller_sources = []
    route_source = external('state/routes/' + project_id + '.json')
    if route_source:
        controller_sources.append(route_source)
        ledger = _json(route_source, route_source['path'])
        if not isinstance(ledger, dict) or ledger.get('project_id') != project_id:
            raise ValueError('Route ledger identity differs from project')
        epoch, accepted = _accepted(ledger, state)
        focus = epoch.get('focus') or make_focus(project, state)
        if focus != make_focus(project, state, focus.get('core_problem')):
            raise ValueError('Frozen route focus is stale or malformed')
        route = {'present': True, 'route_epoch': epoch['epoch'], 'route': epoch['route'],
            'accepted_run_ids': accepted[-last_n:], 'effective_rounds': epoch.get('effective_rounds'),
            'stagnation': epoch.get('stagnation'), 'extensions_used': epoch.get('extensions_used'),
            'review_pending': epoch.get('review_pending', False)}
    else:
        ledger, accepted = {}, []
        focus = make_focus(project, state)
        route = {'present': False, 'route_epoch': None, 'route': state.get('research_route'),
            'accepted_run_ids': [], 'effective_rounds': None, 'stagnation': None,
            'extensions_used': None, 'review_pending': False}
    for run in accepted[-last_n:]:
        report = add('reports/' + run + '.md', trust='MODEL_CANDIDATE', evidence=True)
        if report:
            if report['size_bytes'] > MAX_READ: raise ValueError('Accepted report exceeds structured read bound')
            try: report_text = report['raw'].decode('utf-8-sig')
            except UnicodeError as exc: raise ValueError('Accepted report is not UTF-8') from exc
            if not re.search(r'(?m)^RUN_ID: ' + re.escape(run) + r'\s*$', report_text):
                raise ValueError('Accepted report RUN_ID does not match its receipt')
    for event in ledger.get('events', []):
        if event.get('type') == 'RESEARCH_ROUND' and event.get('run_id') in accepted[-last_n:]:
            refs = event.get('changed_evidence_paths', [])
            if not isinstance(refs, list): raise ValueError('Invalid accepted evidence paths')
            for relative in refs: add(relative, trust='MODEL_CANDIDATE', evidence=True)

    for relative in ('config/defaults.json', 'config/supervision_defaults.json',
                     'config/discovery_defaults.json', 'config/research_policy.json',
                     'config/route_policy.json', 'config/supervision_policy.json',
                     'config/projects/' + project_id + '.json'):
        source = external(relative)
        if source: controller_sources.append(source)
    settings = configuration.settings_for(project)
    profile = selected.get('RESEARCH_PROFILE.json')
    if profile:
        profile_data = _json(profile, profile['path'])
        if not isinstance(profile_data, dict) or not isinstance(profile_data.get('read_order', []), list):
            raise ValueError('Invalid project read order')
        for relative in profile_data.get('read_order', []):
            if relative in FIXED: continue
            add(relative, trust='USER_FROZEN' if relative.startswith('inputs/') else 'UNVERIFIED')
    pins = ([state['selected_idea']] if state.get('selected_idea') is not None else [])
    pins += state.get('supporting_ideas', [])
    if pins:
        index_source = add('ideas/INDEX.json', required=True)
        index = _json(index_source, index_source['path'])
        for pin in pins:
            if (not isinstance(pin, dict) or set(pin) != {'id', 'version'}
                    or type(pin['version']) is not int or pin['version'] < 1):
                raise ValueError('Invalid exact user idea pin')
            card = next((c for c in index.get('ideas', []) if c.get('id') == pin['id']), None)
            revision = next((r for r in card.get('revisions', []) if r.get('version') == pin['version']), None) if card else None
            if not revision or not revision.get('sha256'): raise ValueError('Pinned idea has no exact revision and hash')
            source = add(revision.get('file'), trust='USER_FROZEN', required=True)
            if not source['path'].startswith('ideas/'): raise ValueError('Idea revision must remain in ideas/')
            if source['path'] in expected and expected[source['path']] != revision['sha256']:
                raise ValueError('Pinned versions disagree about the same source path')
            expected[source['path']] = revision['sha256']

    # Frozen problem sources exist independently of candidate claims.
    problem_bindings = []
    problems_source = selected.get('research/discovery/PROBLEMS.json')
    if problems_source:
        problems = _json(problems_source, problems_source['path'])
        for problem in problems.get('problems', []):
            for revision in problem.get('revisions', []):
                spec = revision['spec']
                if canonical_hash(spec) != revision['spec_sha256']:
                    raise ValueError('Frozen problem digest differs from its declaration')
                for relative in revision.get('source_bindings', {}): add(relative)
                problem_bindings.append({'problem_id': problem['id'], 'problem_version': revision['version'],
                    'spec_sha256': revision['spec_sha256'],
                    'goal_sha256': revision.get('goal_sha256'),
                    'goal_binding_current': revision.get('goal_sha256') == goal['sha256'],
                    'obligation_ids': [o['id'] for o in spec.get('obligations', [])],
                    'verification_status': 'UNVERIFIED', 'active': False})
    attempt_source = external('state/discovery/' + project_id + '.json')
    if attempt_source:
        controller_sources.append(attempt_source)
        attempts = _json(attempt_source, attempt_source['path'])
        active = next((a for a in attempts.get('attempts', []) if a.get('id') == attempts.get('active_attempt')), None)
        if attempts.get('active_attempt') and active is None: raise ValueError('Frozen active attempt is missing')
        if active:
            pinned = next((p for p in problem_bindings if p['problem_id'] == active.get('problem_id')
                and p['problem_version'] == active.get('problem_version')
                and p['spec_sha256'] == active.get('problem_sha256')), None)
            if pinned is None: raise ValueError('Active attempt has no matching frozen problem version')
            if not pinned['goal_binding_current']: raise ValueError('Active problem belongs to a stale GOAL version')
            pinned['active'] = True

    # Bounded name-based selection is declared as a heuristic, never full-text
    # coverage or scientific relevance. Explicit paper/derivation refs stay bound.
    review_candidates = []
    literature = _path(project, 'literature')
    if literature.is_dir():
        from runner_core import project_link
        if project_link(literature): raise ValueError('Literature root cannot be linked')
        review_candidates = sorted(p.relative_to(project).as_posix() for p in literature.glob('*.json')
                                   if 'review' in p.name.casefold())
        review_dir = _path(project, 'literature/technical_reviews')
        if review_dir.is_dir():
            review_candidates += sorted(p.relative_to(project).as_posix() for p in review_dir.glob('*.json'))
    for relative in sorted(set(review_candidates))[:12]:
        source = add(relative)
        record = _json(source, relative)
        if not isinstance(record, dict): raise ValueError('Technical review must be a JSON object')
        paper = record.get('paper', {})
        if isinstance(paper, dict) and paper.get('source_file'):
            add(paper['source_file'])
        paths = record.get('derivation_paths', [])
        if not isinstance(paths, list): raise ValueError('Technical review derivation paths must be explicit')
        for relative in paths: add(relative)
    for relative in sorted(set(review_candidates))[12:]:
        missing.append({'scope': 'PROJECT', 'path': relative, 'reason': 'NOT_SELECTED_TECHNICAL_REVIEW_LIMIT_12'})

    graph_source = selected.get('research/discovery/CLAIM_GRAPH.json')
    claim_status = {'present': False, 'claims': []}
    if graph_source:
        graph = _json(graph_source, graph_source['path'])
        from engine.claim_graph import status as current_claim_status
        raw_claims = graph.get('claims') if isinstance(graph, dict) else None
        if not isinstance(raw_claims, list): raise ValueError('Invalid canonical claim graph')
        # The canonical goal binding hashes all inputs. Preflight that tree so
        # its read-only status computation cannot follow an unselected link or
        # consult an unbound credential/environment file.
        inputs = _path(project, 'inputs')
        if inputs.is_dir() and raw_claims:
            for base, dirs, files in os.walk(inputs, followlinks=False):
                for name in [*dirs, *files]:
                    relative = (Path(base) / name).relative_to(project).as_posix()
                    path = _source_path(project, relative)
                    if name in files: add(relative, trust='USER_FROZEN')
        for claim in raw_claims:
            groups = [claim.get('evidence', {}), claim.get('binding', {}).get('files', {})]
            groups += [r.get('evidence', {}) for r in claim.get('reviews', {}).values()]
            groups += [(claim.get('formal_receipt') or {}).get('source_bindings', {}),
                       (claim.get('counterexample_receipt') or {}).get('source_bindings', {})]
            for bindings in groups:
                if not isinstance(bindings, dict): raise ValueError('Invalid claim source bindings')
                for relative in bindings: add(relative, fixed=relative in FIXED, evidence=relative not in FIXED)
            for receipt_name in ('formal_receipt', 'counterexample_receipt'):
                output = (claim.get(receipt_name) or {}).get('output_file')
                if output:
                    output_path = Path(output)
                    if not output_path.is_absolute(): raise ValueError('Verifier log must have an absolute controller path')
                    relative = output_path.relative_to(controller).as_posix()
                    if not relative.startswith('logs/'): raise ValueError('Verifier log is outside controller logs')
                    source = external(relative)
                    if source: controller_sources.append(source)
        memory = graph.get('memory', {})
        for node in memory.get('nodes', []):
            for relative in node.get('source_bindings', {}): add(relative, fixed=relative in FIXED)
        # Status comes solely from the existing authority; no refresh/save.
        statuses = current_claim_status(project)['claims']
        claim_status = {'present': True, 'claims': statuses}
        for claim in raw_claims:
            state_now = next(s for s in statuses if s['id'] == claim['id'])
            level = ('INDEPENDENTLY_REVIEWED' if state_now['proof_status'] == 'INDEPENDENTLY_REVIEWED'
                     else 'TOOL_CHECKED_AUDIT_PENDING' if state_now['formal_status'] == 'TOOL_CHECKED_STATEMENT_PENDING'
                     else 'MODEL_CANDIDATE')
            for relative in claim.get('evidence', {}):
                if relative in selected:
                    source = selected[relative]
                    # Whole files stay candidates; the exact claim/version
                    # review level belongs only to its receipt scope below.
                    source['trust'] = 'MODEL_CANDIDATE'
                    source['verification_scopes'].append({'claim_id': claim['id'], 'revision': claim['revision'],
                        'status': level, 'scope': 'Canonical controller receipt; no new mathematical review'})

    obligations_source = selected.get('research/PROOF_OBLIGATIONS.json')
    obligation_ids = []
    if obligations_source:
        obligations = _json(obligations_source, obligations_source['path'])
        values = obligations.get('obligations', []) if isinstance(obligations, dict) else obligations
        if isinstance(values, dict): obligation_ids = list(values)
        elif isinstance(values, list): obligation_ids = [o['id'] for o in values if isinstance(o, dict) and isinstance(o.get('id'), str)]
    obligation_ids += [oid for problem in problem_bindings if problem['active'] for oid in problem['obligation_ids']]
    derived = {'project_id': project_id, 'focus': focus, 'route_summary': route,
        'claim_status': claim_status, 'obligation_ids': sorted(set(obligation_ids)),
        'problem_bindings': problem_bindings,
        'technical_review_policy': 'Up to 12 named local review JSON files plus explicit receipt references; relevance and complete literature coverage are not inferred.',
        'critical_model': copy.deepcopy(settings['model_policy']['critical']),
        'goal_version': {'sha256': goal['sha256'], 'number': None,
                         'reason': 'GOAL has no numbered version registry; its complete content hash is the exact version.'}}
    derived_bytes = len(json.dumps(derived, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf8'))
    available = defaults['max_snapshot_bytes'] - derived_bytes
    if goal['size_bytes'] > available: raise ValueError('Complete GOAL and authoritative bindings exceed snapshot budget')
    source_manifest, bodies = [], []
    unique_controller = {s['path']: s for s in controller_sources}
    ordered = [goal] + [selected[k] for k in sorted(selected) if k != 'GOAL.md'] + [unique_controller[k] for k in sorted(unique_controller)]
    for source in ordered:
        captured, reason = '', None
        if source.get('metadata_only'): reason = 'CONTROLLER_METADATA_ONLY'
        elif source['size_bytes'] > MAX_READ: reason = 'SOURCE_TOO_LARGE_FOR_TEXT_EXTRACTION'
        elif source['path_object'].suffix.casefold() not in TEXT: reason = 'BINARY_OR_UNSUPPORTED_TEXT'
        else:
            try: decoded = source['raw'].decode('utf8')
            except UnicodeError:
                reason = 'NON_UTF8_TEXT'
            else:
                cap = source['size_bytes'] if source['path'] == 'GOAL.md' else min(PER_FILE, available)
                captured = decoded.encode('utf8')[:max(0, cap)].decode('utf8', errors='ignore')
                if len(captured.encode('utf8')) < source['size_bytes']: reason = 'TEXT_BYTE_BUDGET'
        count = len(captured.encode('utf8')); available -= count
        if captured: bodies.append({'scope': source['scope'], 'path': source['path'], 'content': captured})
        source_manifest.append({k: source[k] for k in ('scope', 'path', 'size_bytes', 'sha256', 'trust',
                                                      'evidence_eligible', 'verification_scopes')})
        source_manifest[-1].update(captured_bytes=count, omitted_bytes=source['size_bytes'] - count,
            truncated=count != source['size_bytes'], omission_reason=reason)
    # Detect concurrent content changes across extraction, including bindings.
    for source in ordered:
        root = project if source['scope'] == 'PROJECT' else controller
        if _read(_path(root, source['path']))['sha256'] != source['sha256']:
            raise ValueError('Snapshot source changed during extraction: ' + source['path'])
        if source['path'] in expected and source['sha256'] != expected[source['path']]:
            raise ValueError('Pinned source checksum differs from its registered revision')
    source_manifest.sort(key=lambda s: (s['scope'], s['path']))
    bodies.sort(key=lambda s: (s['scope'], s['path']))
    result = {'schema_version': 1, **derived, 'defaults': defaults,
        'source_manifest': source_manifest, 'source_manifest_sha256': canonical_hash(source_manifest),
        'sources': bodies, 'missing': sorted(missing, key=lambda s: (s['scope'], s['path'])),
        'limits': {'max_snapshot_bytes': defaults['max_snapshot_bytes'], 'per_file_bytes': PER_FILE,
                   'derived_bytes': derived_bytes, 'text_bytes': defaults['max_snapshot_bytes'] - available,
                   'omission_policy': 'Complete GOAL first, then sorted project files; controller sources metadata only.'}}
    # The transport envelope and manifest also count toward the hard limit.
    # Drop optional text deterministically, retaining every omission and GOAL.
    while True:
        result['source_manifest_sha256'] = canonical_hash(source_manifest)
        result['input_snapshot_sha256'] = '0' * 64
        for _ in range(4):
            size = len(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf8'))
            if result['limits'].get('serialized_bytes') == size: break
            result['limits']['serialized_bytes'] = size
        size = len(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf8'))
        if size <= defaults['max_snapshot_bytes']: break
        optional = next((body for body in reversed(bodies) if body['path'] != 'GOAL.md'), None)
        if optional is None: raise ValueError('Manifest and complete frozen GOAL exceed snapshot byte limit')
        raw = optional['content'].encode('utf8')
        kept = raw[:max(0, len(raw) - (size - defaults['max_snapshot_bytes']) - 256)].decode('utf8', errors='ignore')
        removed = len(raw) - len(kept.encode('utf8'))
        source = next(s for s in source_manifest if s['scope'] == optional['scope'] and s['path'] == optional['path'])
        source.update(captured_bytes=source['captured_bytes'] - removed,
            omitted_bytes=source['omitted_bytes'] + removed, truncated=True, omission_reason='SERIALIZED_BYTE_BUDGET')
        result['limits']['text_bytes'] -= removed
        if kept: optional['content'] = kept
        else: bodies.remove(optional)
    result['input_snapshot_sha256'] = canonical_hash({k: v for k, v in result.items() if k != 'input_snapshot_sha256'})
    return result
