"""Shared provenance and operator-owned discovery records (standard library)."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
import configuration
from research_quality import hash_file, local_file, read_object
from route_budget import stamp

ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$')
STORE = 'research/discovery'


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value) or '..' in value:
        raise ValueError('Discovery IDs require 1..80 letters, digits, dots, underscores or hyphens')
    return value


def object_hash(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Missing nonempty ' + field)
    return value


def strings(value, field, *, empty=False):
    if not isinstance(value, list) or (not empty and not value):
        raise ValueError(field + ' must be a list' + ('' if empty else ' with at least one item'))
    for item in value: text(item, field)
    return value


def evidence(project, paths, *, empty=False):
    strings(paths, 'evidence_paths', empty=empty)
    result = {}
    for rel in paths:
        path = _unlinked_file(project, rel, roots={'proofs', 'research', 'literature', 'experiments'})
        canonical = path.relative_to(project.resolve()).as_posix().casefold()
        if (canonical.startswith(STORE.casefold() + '/')
                or canonical == 'research/supervision_report.md'
                or canonical.startswith('research/supervision/')
                or path.name.casefold() in {'state.json', 'round_review.json', 'route_signal.json',
                    'route_verdict.json', 'checkpoint.json', 'theory_readiness.json'}):
            raise ValueError('Control records cannot certify their own scientific content')
        result[rel] = hash_file(path)
    return result


def _unlinked_file(project, relative, *, roots=None):
    path = local_file(project, relative, roots=roots)
    # resolve() alone hides a link to another location inside the same project.
    # Inspect the original components, including a link followed by "..".
    from runner_core import project_link
    component = project
    for part in Path(relative).parts:
        component = component / part
        if project_link(component):
            raise ValueError('Symlink or junction evidence is not accepted: ' + relative)
    return path


def fresh(project, bindings):
    if not isinstance(bindings, dict): return False
    try:
        return all(hash_file(_unlinked_file(project, rel)) == sha for rel, sha in bindings.items())
    except (OSError, ValueError): return False


def goal_binding(project):
    state = read_object(project / 'research/STATE.json')
    names = ['GOAL.md', 'AGENTS.md', 'RESEARCH_PROFILE.json', 'research/THREAT_MODEL.md',
             'research/SECURITY_MODEL.md', 'research/SECURITY_DEFINITIONS.md']
    paths = [project / name for name in names if (project / name).is_file()]
    paths += [p for p in (project / 'inputs').rglob('*') if p.is_file()]
    # Registering an unrelated idea must not invalidate a running proof attempt.
    pins = ([state['selected_idea']] if isinstance(state.get('selected_idea'), dict) else [])
    pins += state.get('supporting_ideas', [])
    index = configuration.load_json(project / 'ideas/INDEX.json', {'ideas': []})
    for pin in pins:
        card = next((c for c in index['ideas'] if c['id'] == pin['id']), None)
        revision = next((r for r in card.get('revisions', []) if r['version'] == pin['version']), None) if card else None
        if revision is None: raise ValueError('Pinned idea revision missing')
        paths.append(local_file(project, revision['file'], roots={'ideas'}))
    return {'files': {p.relative_to(project).as_posix(): hash_file(p) for p in paths},
            'research_route': state.get('research_route'),
            'selected_idea': state.get('selected_idea'),
            'supporting_ideas': state.get('supporting_ideas', [])}


def ledger_path(project):
    return configuration.ROOT / 'state/discovery' / (configuration.project_id(project) + '.json')


def ledger(project):
    from .discovery_authority import load
    return load(project)


def save_ledger(project, obj):
    from .discovery_authority import save
    save(project, obj)


def policy(project):
    return configuration.settings_for(project)['discovery_policy']
