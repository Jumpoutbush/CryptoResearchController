"""Portable controller settings. Only Python standard library is required."""
from __future__ import annotations
import copy
import json
import os
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ID_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')
EFFORTS = {'low', 'medium', 'high', 'xhigh', 'max', 'ultra'}


def load_json(path: Path, default=None):
    if not Path(path).is_file():
        return copy.deepcopy(default)
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def atomic_json(path: Path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.write-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
            out.write('\n'); out.flush(); os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def project_id(project: Path) -> str:
    project = Path(project).resolve()
    manifest = load_json(project / 'PROJECT.json', {})
    identifier = manifest.get('id', project.name) if isinstance(manifest, dict) else None
    if not isinstance(identifier, str) or not ID_RE.fullmatch(identifier):
        raise ValueError('PROJECT.json id must use lowercase letters, numbers, underscores or hyphens (1..64)')
    return identifier


def deep_merge(base, override):
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def validate_settings(settings):
    model = settings['model_policy']
    if not isinstance(model, dict) or set(model) - {'routine', 'critical', 'critical_phases'}:
        raise ValueError('Invalid model_policy keys')
    for name in ['routine', 'critical']:
        tier = model.get(name)
        if not isinstance(tier, dict) or set(tier) != {'model', 'effort'}:
            raise ValueError('Model tier must contain model and effort')
        if not isinstance(tier['model'], str) or not tier['model'].strip() or '\n' in tier['model']:
            raise ValueError('Model must be a nonempty identifier')
        if tier['effort'] not in EFFORTS:
            raise ValueError('Invalid reasoning effort')
    if not isinstance(model.get('critical_phases'), list) or any(not isinstance(p, str) for p in model['critical_phases']):
        raise ValueError('critical_phases must be a list of phase names')
    execution = settings['execution']
    if not isinstance(execution, dict) or set(execution) - {'max_seconds', 'pause_seconds', 'max_rounds', 'network_access', 'web_search'}:
        raise ValueError('Invalid execution keys')
    for name, low, high in [('max_seconds',30,86400),('pause_seconds',0,60),('max_rounds',1,10000)]:
        if type(execution.get(name)) is not int or not low <= execution[name] <= high:
            raise ValueError(f'{name} must be an integer in {low}..{high}')
    if type(execution.get('network_access')) is not bool:
        raise ValueError('network_access must be boolean')
    if execution.get('web_search') not in {'live','cached','disabled'}:
        raise ValueError('web_search must be live/cached/disabled')
    literature = settings['literature']
    allowed = {'automatic_pdf_download','max_pdf_downloads_per_round','max_pdf_mb'}
    if not isinstance(literature, dict) or set(literature) - allowed:
        raise ValueError('Invalid literature settings')
    if type(literature.get('automatic_pdf_download')) is not bool:
        raise ValueError('automatic_pdf_download must be boolean')
    for name,low,high in [('max_pdf_downloads_per_round',0,5),('max_pdf_mb',1,80)]:
        if type(literature.get(name)) is not int or not low <= literature[name] <= high:
            raise ValueError(f'Invalid {name}')
    return settings


def settings_for(project: Path | None = None):
    default = load_json(ROOT / 'config/defaults.json')
    if not isinstance(default, dict) or default.get('schema_version') != 1:
        raise ValueError('Missing/invalid config/defaults.json')
    allowed = {'schema_version','model_policy','execution','literature','route_policy'}
    if set(default) - allowed:
        raise ValueError('Unknown global settings')
    settings = copy.deepcopy(default)
    settings['route_policy'] = load_json(ROOT / 'config/route_policy.json', {})
    if project is not None:
        override = load_json(ROOT / 'config/projects' / (project_id(project) + '.json'), {})
        if not isinstance(override, dict) or set(override) - allowed:
            raise ValueError('Unknown project settings')
        settings = deep_merge(settings, override)
    return validate_settings(settings)
