#!/usr/bin/env python3
"""Controller-owned route budget and audit policy; no third-party dependencies.

Only syntactic and provenance validation is automated. A machine-generated
proof, novelty judgement or route verdict must NEVER be presented as a verified
scientific fact solely on the basis of this module.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
POLICY_DEFAULTS = {
    "schema_version": 1,
    "initial_round_budget": 6,
    "stagnation_rounds": 3,
    "extension_round_budget": 4,
    "max_extensions": 2,
    "automatic_falsification": True,
    "automatic_route_review": True,
    "automatic_candidate_discovery": True,
    "require_approval_for_goal_change": True,
    "max_rounds_per_invocation": 8,
}
INT_FIELDS = {
    "initial_round_budget": (1, 500),
    "stagnation_rounds": (1, 500),
    "extension_round_budget": (1, 500),
    "max_extensions": (0, 30),
    "max_rounds_per_invocation": (1, 30),
}
BOOL_FIELDS = {
    "automatic_falsification", "automatic_route_review",
    "automatic_candidate_discovery", "require_approval_for_goal_change",
}
STOP_DECISIONS = {"PAUSE", "STOP", "NEEDS_REVIEW"}
VALID_PROGRESS = {"NO_PROGRESS", "REFINEMENT", "COUNTEREXAMPLE", "CONSTRUCTION", "PROOF_STEP", "COST_BOUND", "PRIOR_ART", "REPRODUCIBLE_TEST"}
SUBSTANTIVE = {"COUNTEREXAMPLE", "CONSTRUCTION", "PROOF_STEP", "COST_BOUND", "PRIOR_ART", "REPRODUCIBLE_TEST"}
VALID_VERDICTS = {"EXTEND", "REFOCUS", "PIVOT_PROVISIONAL", "PAUSE_FOR_REVIEW", "REJECT_SCOPE_LIMITED"}
ROUTE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,79}$")


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def project_key(project: Path) -> str:
    """Managed projects retain identity and research budget when moved."""
    from configuration import project_id
    return project_id(project)


def atom_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".route-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"Must be a JSON object: {path}")
    return data


def validate_policy(obj: dict, *, partial: bool = False) -> dict:
    if not isinstance(obj, dict):
        raise ValueError("route policy must be a JSON object")
    fields = set(POLICY_DEFAULTS)
    extra = set(obj) - fields
    if extra:
        raise ValueError(f"unknown route policy keys: {sorted(extra)}")
    checked = {} if partial else dict(POLICY_DEFAULTS)
    checked.update(obj)
    if checked.get("schema_version", 1) != 1:
        raise ValueError("route policy schema_version must be 1")
    for key, (low, high) in INT_FIELDS.items():
        if key in checked:
            val = checked[key]
            if type(val) is not int or not low <= val <= high:
                raise ValueError(f"{key}: expected integer from {low} to {high}")
    for key in BOOL_FIELDS:
        if key in checked and type(checked[key]) is not bool:
            raise ValueError(f"{key}: expected boolean")
    return checked


def policy_for(controller: Path, project: Path, cli: dict | None = None) -> tuple[dict, dict, Path]:
    default_path = controller / "config" / "route_policy.json"
    project_path = controller / "config" / "projects" / f"{project_key(project)}.json"
    global_policy = validate_policy(read_json(default_path)) if default_path.exists() else validate_policy({})
    stored = read_json(project_path) if project_path.exists() else {}
    override = validate_policy(stored.get('route_policy', {}), partial=True)
    explicit = {k: v for k, v in (cli or {}).items() if v is not None}
    validate_policy(explicit, partial=True)
    effective = validate_policy({**global_policy, **override, **explicit})
    origin = {k: ("command_line" if k in explicit else "project_override" if k in override else "global")
              for k in POLICY_DEFAULTS if k != "schema_version"}
    return effective, origin, project_path


def set_project_override(controller: Path, project: Path, updates: dict):
    path = controller / 'config/projects' / f'{project_key(project)}.json'
    config = read_json(path) if path.exists() else {'schema_version': 1}
    old = validate_policy(config.get('route_policy', {}), partial=True)
    config['route_policy'] = validate_policy({**old, **updates}, partial=True)
    atom_json(path, config)
    return path


@contextmanager
def file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as f:
        try:
            f.seek(0)
            f.write(b"0")
            f.flush()
            f.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            raise RuntimeError(f"Another route controller instance is running: {path}") from exc
        try:
            yield
        finally:
            f.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def state_path(project: Path) -> Path:
    return project / "research" / "STATE.json"


def state_read(project: Path) -> dict:
    data = read_json(state_path(project))
    for k in ("phase", "decision", "next_task", "priority_problem"):
        if not isinstance(data.get(k), str) or not data[k].strip():
            raise ValueError(f"research/STATE.json: invalid {k}")
    from runner_core import PHASES, DECISIONS
    if data['phase'] not in PHASES or data['decision'] not in DECISIONS:
        raise ValueError('STATE.json contains unsupported phase or decision')
    if not isinstance(data.get("last_run"), (str, type(None))):
        raise ValueError("research/STATE.json: invalid last_run")
    return data


def selected_route(state: dict) -> str:
    route = state.get("research_route")
    if not isinstance(route, str) or not route.strip():
        return "UNSPECIFIED"
    return route.strip()


def make_epoch(route: str, epoch_id: int, before_run: str | None) -> dict:
    return {"epoch": epoch_id, "route": route, "started": stamp(), "baseline_run": before_run,
            "effective_rounds": 0, "stagnation": 0, "extensions_used": 0,
            "review_pending": False, "review_reason": None, "review_count": 0,
            "last_processed_run": before_run, "counted_run_ids": [], "closed": False}


def registry_path(path: Path) -> Path:
    """Independent route registration witness; never stored inside the project."""
    path = Path(path)
    if path.parent.name != 'routes':
        raise ValueError('Route authority must live in state/routes')
    return path.parent.parent / 'route_registry' / path.name


def _ledger_bytes(data: dict) -> bytes:
    return (json.dumps(data, indent=2, ensure_ascii=False) + '\n').encode('utf8')


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha(path: Path):
    return _sha(path.read_bytes()) if path.is_file() else None


def _validate_ledger(data: dict, identity: str) -> None:
    if (not isinstance(data, dict) or data.get('schema_version') != 1
            or data.get('project_id', identity) != identity):
        raise ValueError('Route ledger version or project identity mismatch')
    if not isinstance(data.get('epochs'), list) or not data['epochs'] or not isinstance(data.get('events'), list):
        raise ValueError('Route ledger authority is empty or incomplete; explicit recovery is required')
    for epoch in data['epochs']:
        if not isinstance(epoch, dict) or not isinstance(epoch.get('route'), str) or not epoch['route']:
            raise ValueError('Route ledger epoch identity is invalid')
        for name in ('effective_rounds', 'stagnation', 'extensions_used'):
            if type(epoch.get(name)) is not int or epoch[name] < 0:
                raise ValueError('Route ledger consumption is invalid: ' + name)
        ids = epoch.get('counted_run_ids')
        if (not isinstance(ids, list) or any(not isinstance(run, str) or not run for run in ids)
                or len(ids) != len(set(ids)) or len(ids) > epoch['effective_rounds']):
            raise ValueError('Route ledger counted run authority is invalid')


def _registry(path: Path):
    witness = registry_path(path)
    if not witness.exists(): return None
    data = read_json(witness)
    registration = data.get('budget_registration_id')
    if (data.get('schema_version') != 1 or data.get('project_id') != path.stem
            or not {'committed', 'pending'} <= set(data)
            or not isinstance(registration, str) or not re.fullmatch(r'[0-9a-f]{64}', registration)):
        raise ValueError('Route registration witness is invalid')
    committed = data.get('committed')
    if committed is not None:
        if (not isinstance(committed, dict) or type(committed.get('sequence')) is not int
                or committed['sequence'] < 1 or not isinstance(committed.get('ledger_sha256'), str)
                or not re.fullmatch(r'[0-9a-f]{64}', committed['ledger_sha256'])):
            raise ValueError('Route registration committed witness is invalid')
    pending = data.get('pending')
    if pending is not None:
        if (not isinstance(pending, dict) or not isinstance(pending.get('afterimage'), dict)
                or type(pending.get('sequence')) is not int
                or pending.get('sequence') != (committed['sequence'] + 1 if committed else 1)
                or not (pending.get('from_sha256') is None or
                    isinstance(pending['from_sha256'], str) and re.fullmatch(r'[0-9a-f]{64}', pending['from_sha256']))
                or committed is not None and pending.get('from_sha256') != committed['ledger_sha256']
                or pending.get('to_sha256') != _sha(_ledger_bytes(pending['afterimage']))
                or pending['afterimage'].get('budget_registration_id') != registration):
            raise ValueError('Route registration pending transition is invalid')
        _validate_ledger(pending['afterimage'], path.stem)
    elif committed is None:
        raise ValueError('Route registration has no committed authority')
    return data


def _validate_authority(path: Path, ledger: dict, witness) -> None:
    registration = ledger.get('budget_registration_id')
    if witness is None:
        if registration is not None:
            raise ValueError('Route registration witness is missing; do not re-register or clear consumption')
        return
    if witness.get('pending') is not None:
        raise ValueError('Route authority has a pending transition; explicit recover-ledger is required')
    if registration != witness['budget_registration_id']:
        raise ValueError('Route ledger registration marker is missing or mismatched')
    if _file_sha(path) != witness['committed']['ledger_sha256']:
        raise ValueError('Route ledger SHA differs from latest registered authority; stale backup or corruption')


def _no_budget_regression(before: dict, after: dict) -> None:
    for old in before['epochs']:
        matching = [epoch for epoch in after['epochs'] if epoch['route'] == old['route']]
        if not matching:
            raise ValueError('Route authority cannot discard a historical route budget')
        for name in ('effective_rounds', 'extensions_used', 'operator_added_rounds'):
            if max(epoch.get(name, 0) for epoch in matching) < old.get(name, 0):
                raise ValueError('Route authority cannot roll back consumed or added budget: ' + name)
        retained = {run for epoch in matching for run in epoch['counted_run_ids']}
        if not set(old['counted_run_ids']) <= retained:
            raise ValueError('Route authority cannot discard counted run IDs')


def load_ledger(controller: Path, project: Path, state: dict) -> tuple[Path, dict, dict]:
    path = controller / "state" / "routes" / (project_key(project) + ".json")
    witness = _registry(path)
    if path.exists():
        ledger = read_json(path)
        _validate_ledger(ledger, project_key(project))
        _validate_authority(path, ledger, witness)
    else:
        if witness is not None:
            raise ValueError('Registered route ledger authority is missing; explicit recovery is required')
        if state.get('last_run') is not None:
            raise ValueError('Existing research history requires an explicit operator budget baseline registration')
        ledger = {"schema_version": 1, "project_id": project_key(project), "project": str(project.resolve()), "epochs": [],
                  "events": [], "created": stamp()}
    ledger['project_id'] = project_key(project)
    ledger['project'] = str(project.resolve())
    route = selected_route(state)
    if not ledger["epochs"] or ledger["epochs"][-1]["route"] != route:
        if ledger["epochs"]:
            ledger["epochs"][-1]["closed"] = True
        epoch = make_epoch(route, len(ledger["epochs"]) + 1, state.get("last_run"))
        # Switching B -> C -> B must not silently reset the original route
        # budget. Reopen exactly matching route identifiers with prior totals.
        former = next((e for e in reversed(ledger["epochs"]) if e["route"] == route), None)
        if former is not None:
            for field in ("effective_rounds", "stagnation", "extensions_used", "review_pending", "review_reason"):
                epoch[field] = former[field]
            import copy
            for field in ('focus', 'support_rounds', 'mainline_fingerprints', 'operator_added_rounds'):
                if field in former:
                    epoch[field] = copy.deepcopy(former[field])
            epoch["counted_run_ids"] = list(former["counted_run_ids"])
            ledger["events"].append({"type": "ROUTE_REVISITED", "route": route,
                                     "inherited_effective_rounds": epoch["effective_rounds"],
                                     "at": stamp()})
        else:
            ledger["events"].append({"type": "NEW_ROUTE_EPOCH", "route": route, "at": stamp()})
        ledger["epochs"].append(epoch)
    from research_focus import ensure_focus
    ensure_focus(project, ledger['epochs'][-1], state)
    return path, ledger, ledger["epochs"][-1]


def _complete_pending(path: Path, witness: dict) -> None:
    pending = witness['pending']
    actual = _file_sha(path)
    if actual not in {pending['from_sha256'], pending['to_sha256']}:
        raise ValueError('Pending route recovery inputs changed; restore exact witnessed authority first')
    if actual != pending['to_sha256']:
        atom_json(path, pending['afterimage'])
    if _file_sha(path) != pending['to_sha256']:
        raise ValueError('Route ledger did not match the pending afterimage')
    witness['committed'] = {'sequence': pending['sequence'], 'ledger_sha256': pending['to_sha256']}
    witness['pending'] = None
    atom_json(registry_path(path), witness)


def recover_ledger(path: Path, reason: str | None = None) -> dict:
    """Finish only an already prepared local afterimage; never infer missing costs."""
    path = Path(path)
    witness = _registry(path)
    if witness is None:
        return {'status': 'NO_REGISTERED_TRANSITION'}
    if witness.get('pending') is None:
        if not path.is_file():
            raise ValueError('Registered route ledger authority is missing; restore latest witnessed backup')
        ledger = read_json(path); _validate_ledger(ledger, path.stem)
        _validate_authority(path, ledger, witness)
        return {'status': 'ALREADY_COMMITTED', 'ledger_sha256': _file_sha(path)}
    target = witness['pending']['to_sha256']
    _complete_pending(path, witness)
    if reason is not None:
        witness.setdefault('recoveries', []).append({'at': stamp(), 'reason': reason,
            'ledger_sha256': target, 'kind': 'PREPARED_LOCAL_AFTERIMAGE'})
        atom_json(registry_path(path), witness)
    return {'status': 'RECOVERED_LOCAL_AFTERIMAGE', 'ledger_sha256': target}


def save_ledger(path: Path, ledger: dict) -> None:
    path = Path(path)
    _validate_ledger(ledger, path.stem)
    # Display-history truncation is unchanged. Counted run identities remain intact.
    if len(ledger['events']) > 3000:
        ledger['events'] = ledger['events'][-3000:]
    witness = _registry(path)
    if witness is not None:
        registration = witness['budget_registration_id']
        if ledger.get('budget_registration_id', registration) != registration:
            raise ValueError('Route ledger registration identity changed')
        ledger['budget_registration_id'] = registration
        desired = _sha(_ledger_bytes(ledger))
        if witness.get('pending') is not None:
            if witness['pending']['to_sha256'] != desired:
                raise ValueError('Another pending route afterimage must be recovered first')
            _complete_pending(path, witness)
            return
        if not path.is_file():
            raise ValueError('Registered route ledger authority is missing; explicit restore required')
        current = read_json(path); _validate_ledger(current, path.stem)
        _validate_authority(path, current, witness)
        _no_budget_regression(current, ledger)
        if desired == witness['committed']['ledger_sha256']: return
    else:
        if ledger.get('budget_registration_id') is not None:
            raise ValueError('Route registration witness is missing; refusing to reset its high-water mark')
        if path.exists():
            current = read_json(path); _validate_ledger(current, path.stem)
            if current.get('budget_registration_id') is not None:
                raise ValueError('Route registration witness is missing')
            _no_budget_regression(current, ledger)
        registration = _sha(_ledger_bytes(ledger))
        ledger['budget_registration_id'] = registration
        witness = {'schema_version': 1, 'project_id': path.stem,
                   'budget_registration_id': registration, 'registered_at': stamp(),
                   'committed': None, 'pending': None}
        desired = _sha(_ledger_bytes(ledger))
    sequence = witness['committed']['sequence'] + 1 if witness['committed'] else 1
    import copy
    witness['pending'] = {'sequence': sequence, 'from_sha256': _file_sha(path),
        'to_sha256': desired, 'afterimage': copy.deepcopy(ledger), 'prepared_at': stamp()}
    atom_json(registry_path(path), witness)
    _complete_pending(path, witness)


def register_baseline(controller: Path, project: Path, baseline: dict, reason: str) -> dict:
    """Explicit operator migration only; it cannot overwrite an existing authority."""
    import copy
    if not isinstance(reason, str) or len(reason.strip()) < 12:
        raise ValueError('Budget registration requires an explicit operator reason of at least 12 characters')
    path = Path(controller) / 'state/routes' / (project_key(project) + '.json')
    if path.exists() or registry_path(path).exists():
        raise ValueError('Budget authority is already present or registered; baseline cannot reset it')
    baseline = copy.deepcopy(baseline)
    _validate_ledger(baseline, project_key(project))
    if baseline.get('budget_registration_id') is not None:
        raise ValueError('A baseline cannot import an existing registration identity')
    state = state_read(project)
    if (baseline['epochs'][-1]['route'] != selected_route(state)
            or baseline['epochs'][-1].get('last_processed_run') != state.get('last_run')):
        raise ValueError('Operator baseline must bind the current route and exact last_run')
    baseline.update(project_id=project_key(project), project=str(project.resolve()))
    baseline['events'].append({'type': 'OPERATOR_BUDGET_BASELINE', 'reason': reason.strip(), 'at': stamp(),
        'scope': 'OPERATOR_CONFIRMED_HISTORICAL_CONSUMPTION_NOT_RECONSTRUCTED'})
    save_ledger(path, baseline)
    return {'status': 'BASELINE_REGISTERED', 'ledger_sha256': _file_sha(path),
            'budget_registration_id': baseline['budget_registration_id']}


def restore_registered_ledger(controller: Path, project: Path, backup: Path, reason: str) -> dict:
    if not isinstance(reason, str) or len(reason.strip()) < 12:
        raise ValueError('Budget restoration requires an explicit operator reason of at least 12 characters')
    path = Path(controller) / 'state/routes' / (project_key(project) + '.json')
    witness = _registry(path)
    if witness is None:
        raise ValueError('No independent route witness exists; explicit baseline registration is required')
    source = Path(backup).read_bytes()
    expected = (witness['pending']['to_sha256'] if witness.get('pending') else witness['committed']['ledger_sha256'])
    if _sha(source) != expected:
        raise ValueError('Backup SHA must equal the latest route witness; old backup rollback is forbidden')
    data = json.loads(source.decode('utf-8-sig'))
    _validate_ledger(data, project_key(project))
    if data.get('budget_registration_id') != witness['budget_registration_id']:
        raise ValueError('Backup registration identity differs from witness')
    # Preserve damaged bytes for operator audit; never rewrite project state or evidence.
    if path.exists() and _file_sha(path) != expected:
        import uuid
        saved = Path(controller) / 'backups/route-authority' / (path.stem + '-' + uuid.uuid4().hex + '.json')
        saved.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(path, saved)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.route-restore-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(source); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    if witness.get('pending') is not None:
        _complete_pending(path, witness)
        witness = _registry(path)
    witness.setdefault('recoveries', []).append({'at': stamp(), 'reason': reason.strip(), 'ledger_sha256': expected})
    atom_json(registry_path(path), witness)
    return {'status': 'EXACT_WITNESSED_BACKUP_RESTORED', 'ledger_sha256': expected}


def total_budget(epoch: dict, policy: dict) -> int:
    return (policy["initial_round_budget"] + epoch["extensions_used"] * policy["extension_round_budget"]
            + epoch.get('operator_added_rounds', 0))


def needs_review(epoch: dict, policy: dict) -> str | None:
    if epoch["review_pending"]:
        return epoch["review_reason"] or "scheduled"
    if epoch["effective_rounds"] >= total_budget(epoch, policy):
        return "budget_exhausted"
    if epoch["stagnation"] >= policy["stagnation_rounds"]:
        return "stagnation"
    return None


def evidence_path(project: Path, raw: str) -> Path | None:
    if not isinstance(raw, str) or not raw.strip() or raw.startswith(('/', '\\')) or ':' in raw:
        return None
    path = project.joinpath(raw)
    try:
        resolved = path.resolve()
        resolved.relative_to(project.resolve())
    except (OSError, ValueError):
        return None
    if path.is_symlink() or not resolved.is_file():
        return None
    parts = resolved.relative_to(project.resolve()).parts
    relative = resolved.relative_to(project.resolve()).as_posix().casefold()
    if relative == 'research/supervision_report.md' or relative.startswith('research/supervision/'):
        return None
    if not parts or parts[0] not in {"proofs", "experiments", "literature", "research"}:
        return None
    excluded = {"STATE.json", "ROUTE_SIGNAL.json", "ROUTE_VERDICT.json",
                "ROUTE_DIRECTIVE.md", "RUN_RESULT.json", "ROUTE_HISTORY.jsonl", "ROUND_REVIEW.json"}
    if parts[-1] in excluded or "_upgrade_proposals" in parts or "pdfs" in parts:
        return None
    if resolved.stat().st_size > 4_000_000:
        return None
    return resolved


def evidence_snapshot(project: Path) -> dict[str, str]:
    selected_dirs = ["proofs", "experiments", "literature", "research"]
    deny = {"STATE.json", "ROUTE_SIGNAL.json", "ROUTE_VERDICT.json", "ROUTE_DIRECTIVE.md", "RUN_RESULT.json", "ROUND_REVIEW.json"}
    out = {}
    for folder in selected_dirs:
        parent = project / folder
        if not parent.is_dir():
            continue
        for p in parent.rglob("*"):
            if not p.is_file() or p.is_symlink() or p.name in deny:
                continue
            if "_upgrade_proposals" in p.parts or "pdfs" in p.parts or p.stat().st_size > 4_000_000:
                continue
            rel = p.relative_to(project).as_posix()
            if rel.casefold() == 'research/supervision_report.md' or rel.casefold().startswith('research/supervision/'):
                continue
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def check_signal(project: Path, run_id: str, before: dict[str, str]):
    path = project / "research" / "ROUTE_SIGNAL.json"
    if not path.exists():
        return False, "NO_SIGNAL", [], False
    try:
        signal = read_json(path)
        if signal.get("run_id") != run_id:
            return False, "STALE_SIGNAL", [], False
        mode = signal.get("progress_type", "NO_PROGRESS")
        if mode not in VALID_PROGRESS:
            return False, "INVALID_SIGNAL", [], False
        files = signal.get("evidence_paths")
        if not isinstance(files, list) or len(files) > 30:
            return False, "INVALID_EVIDENCE_LIST", [], False
        updated = evidence_snapshot(project)
        real = []
        for item in files:
            pp = evidence_path(project, item)
            if pp is None:
                continue
            key = pp.relative_to(project.resolve()).as_posix()
            if key in updated and updated[key] != before.get(key):
                real.append(key)
        reason = signal.get("reason")
        qualified = (mode in SUBSTANTIVE and len(real) > 0 and
                     isinstance(reason, str) and len(reason.strip()) >= 24)
        blocked_value = signal.get('route_blocked', False)
        if type(blocked_value) is not bool:
            return False, 'INVALID_BLOCKER_FLAG', [], False
        blocker = blocked_value and qualified
        return qualified, mode, real, blocker
    except (OSError, ValueError, TypeError):
        return False, "MALFORMED_SIGNAL", [], False


def load_verdict(project: Path, run_id: str) -> dict:
    p = project / "research" / "ROUTE_VERDICT.json"
    verdict = read_json(p)
    if verdict.get("run_id") != run_id:
        raise ValueError("ROUTE_VERDICT.run_id is stale or missing")
    if verdict.get("outcome") not in VALID_VERDICTS:
        raise ValueError("Invalid ROUTE_VERDICT.outcome")
    reason = verdict.get("reason")
    if not isinstance(reason, str) or len(reason.strip()) < 24:
        raise ValueError("Route verdict needs a substantive reason")
    paths = verdict.get("evidence_paths", [])
    if not isinstance(paths, list) or not paths:
        raise ValueError("Route verdict requires evidence_paths")
    if not any(evidence_path(project, item) for item in paths):
        raise ValueError("Route verdict evidence_paths must reference existing project files")
    if verdict.get("requires_goal_change") is not False:
        # Explicit false is required; absent fields cannot be interpreted as authorization.
        verdict["unapproved_goal_change"] = True
    else:
        verdict["unapproved_goal_change"] = False
    from research_quality import validate_route_decision
    validate_route_decision(project, verdict)
    return verdict


def choose_candidate(project: Path, verdict: dict):
    candidates = verdict.get("candidates", [])
    if not isinstance(candidates, list):
        raise ValueError("verdict.candidates must be an array")
    qualified = []
    for pos, c in enumerate(candidates):
        if not isinstance(c, dict):
            continue
        route = c.get("route")
        if not isinstance(route, str) or not ROUTE_PATTERN.fullmatch(route):
            continue
        if c.get("requires_goal_change") is not False or c.get("goal_compatible") is not True:
            continue
        if c.get("novelty_question_identified") is not True:
            continue
        if not (isinstance(c.get("priority_problem"), str) and len(c["priority_problem"].strip()) >= 24):
            continue
        if not (isinstance(c.get("next_task"), str) and len(c["next_task"].strip()) >= 24):
            continue
        evidence = c.get("evidence_paths", [])
        if not isinstance(evidence, list) or not any(evidence_path(project, x) for x in evidence):
            continue
        rank = c.get("priority", 999)
        if type(rank) is not int or rank < 1 or rank > 100:
            rank = 999
        from research_quality import validate_candidate
        try:
            validate_candidate(project, c)
        except (ValueError, OSError, KeyError):
            continue
        qualified.append((rank, pos, c))
    if not qualified:
        return None
    qualified.sort(key=lambda x: (x[0], x[1]))
    return qualified[0][2]


def generate_directive(route: str, epoch: dict, policy: dict, review: bool, reason: str | None, original_task: str) -> str:
    intro = ("【CryptoResearchController 调度指令】本指令来自科研预算控制器。"
             "遵守 GOAL.md 与现有科研门禁；不得改变不可放宽条件、不得自行确认证明或新颖性。\n")
    if not review:
        intro += (f"当前路线：{route}；有效研究轮次：{epoch['effective_rounds']}；"
                  f"本阶段预算：{total_budget(epoch, policy)}；无实质进展连续轮数：{epoch['stagnation']}。\n"
                  "本轮先按当前任务证伪或闭合证明，再填写 research/ROUTE_SIGNAL.json："
                  "JSON 对象含 run_id（本轮控制器注入的 RUN_ID）、progress_type（NO_PROGRESS/REFINEMENT/COUNTEREXAMPLE/CONSTRUCTION/PROOF_STEP/COST_BOUND/PRIOR_ART/REPRODUCIBLE_TEST）、"
                  "reason（具体变化）、evidence_paths（本轮新增或修改的 proof/experiment/literature/research 证据文件相对路径）、route_blocked（true/false）。"
                  "只有新增实质证据才能标注进展；尚未独立验证的证明不得写作已证明。"
                  "当当前路线被证据否定时，注明 route_blocked=true，维持 decision=CONTINUE 以供控制器触发单独路线复评；"
                  "涉及必须人工停止的安全问题应保留 NEEDS_REVIEW。\n")
    else:
        intro += (f"【强制路线复评，原因：{reason}】当前路线：{route}。"
                  "本轮只做路线与任务复评，禁止仅沿用上一轮旁支任务。明确区分结构性否定、已有文献覆盖、成本无效、证据不充分和暂时未突破。"
                  "针对现有及可能的新候选，要求符合现有 GOAL，不得无授权改变输出语义或安全目标。\n"
                  "必须建立 research/ROUTE_VERDICT.json，字段：run_id（本轮注入 RUN_ID），"
                  "outcome（REFOCUS/EXTEND/PIVOT_PROVISIONAL/PAUSE_FOR_REVIEW/REJECT_SCOPE_LIMITED），"
                  "reason（至少 24 字符），evidence_paths（项目相对证据路径列表），"
                  "requires_goal_change（布尔值），candidates（数组）。"
                  "candidate 项含 route、goal_compatible、requires_goal_change、"
                  "novelty_question_identified、priority（正整数，值小优先）、"
                  "priority_problem、next_task、evidence_paths。"
                  "PIVOT_PROVISIONAL 只代表下一条路线的可行性预研，绝不能宣称当前路线数学上普遍不可能。"
                  "D 等需要修改 GOAL 的路线仅允许在现有目标下作可行性比较，禁止自动批准改变目标。"
                  "先判断最近任务对核心目标的必要性。旁支尚未审完不自动暂停全项目；"
                  "预算尚有余额且有具体核心任务时选择 REFOCUS，保留已用轮次；"
                  "预算耗尽但有新的直接核心任务时可选择有界 EXTEND。"
                  "REFOCUS/EXTEND 必须填写 next_task 和 next_goal_impact（与 goal_impact 同结构，"
                  "before 为当前缺口、after 为拟检验的明确结果，next_mainline_task 与 next_task 完全一致），"
                  "并设置 STATE.decision=CONTINUE。只有阻断核心任务的外部输入、目标决策、资源或必要审查"
                  "无法解决时选择 PAUSE_FOR_REVIEW，写明阻断的核心义务及原因。\n")
    from research_focus import prompt as focus_prompt
    if epoch.get('focus'):
        intro += focus_prompt(epoch['focus'])
    label = '【此前任务，仅供复评其必要性，不要求继续完成】' if review else '【此前候选任务，执行前核对主线关联】'
    return intro + label + original_task
