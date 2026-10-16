#!/usr/bin/env python3
"""Safe front controller: delegates original research work to runner_core.py.

Controller-owned configuration has the precedence:
 command-line (this invocation) > persisted project override > global defaults.
The original runner, model selection, literature tools, safety checks and Git
checkpoint logic are not reimplemented by this overlay.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from route_budget import (
    atom_json, check_signal, choose_candidate, evidence_path, evidence_snapshot,
    file_lock, generate_directive, load_ledger, load_verdict, needs_review,
    policy_for, project_key, read_json, save_ledger, selected_route,
    set_project_override, stamp, state_path, state_read, STOP_DECISIONS,
    total_budget,
)

HERE = Path(__file__).resolve().parent
CORE = HERE / "runner_core.py"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="CryptoResearchController with persistent multi-project research-route budgets",
        add_help=True)
    parser.add_argument("--project", required=True, help="Research Git project directory")
    parser.add_argument("--rounds", type=int, default=1,
                        help="Maximum actual core research/review rounds THIS invocation")
    parser.add_argument("--route-budget", type=int, default=None,
                        help="Temporary initial budget override; does not persist")
    parser.add_argument("--stagnation-rounds", type=int, default=None,
                        help="Temporary consecutive non-progress threshold")
    parser.add_argument("--extension-round-budget", type=int, default=None)
    parser.add_argument("--max-extensions", type=int, default=None)
    parser.add_argument("--set-route-budget", type=int, default=None,
                        help="Persist per-project initial budget in controller config")
    parser.add_argument("--set-stagnation-rounds", type=int, default=None)
    parser.add_argument("--set-extension-round-budget", type=int, default=None)
    parser.add_argument("--set-max-extensions", type=int, default=None)
    parser.add_argument("--route-status", action="store_true")
    parser.add_argument("--route-sync", action="store_true",
                        help="Explicitly accept external last_run drift without charging budget")
    parser.add_argument("--clear-project-route-policy", action="store_true",
                        help="Back up and delete the stored project budget override; restore global defaults")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fetch-only", action="store_true")
    parser.add_argument("--prepare-pro", action="store_true")
    parser.add_argument("--max-seconds", type=int, default=None)
    parser.add_argument("--no-fetch", action="store_true")
    known, unknown = parser.parse_known_args(argv)
    if known.rounds < 1:
        parser.error("--rounds must be positive")
    return parser, known, unknown


def args_to_core(args, unknown, *, dry_run=False, fetch_only=False, prepare_pro=False):
    command = [sys.executable, str(CORE), "--project", str(Path(args.project).resolve())]
    if args.max_seconds is not None:
        command.extend(["--max-seconds", str(args.max_seconds)])
    if args.no_fetch:
        command.append("--skip-fetch")
    if dry_run or args.dry_run:
        command.append("--dry-run")
    if fetch_only or args.fetch_only:
        command.append("--fetch-only")
    if prepare_pro or args.prepare_pro:
        command.append("--prepare-pro")
    command.extend(unknown)
    return command


def run_child(command) -> int:
    if not CORE.exists():
        raise FileNotFoundError(f"Original controller missing: {CORE} (restore from backup)")
    # Run a separate interpreter to preserve the old process's imports, argument
    # parser, model routing, evidence checks, status logs, and local Git behavior.
    env = os.environ.copy()
    env.update({"CRC_DEFER_CHECKPOINT": "1", "CRC_TRANSACTION_EXTERNAL": "1"})
    proc = subprocess.Popen(command, cwd=HERE, env=env,
                            start_new_session=(os.name != "nt"),
                            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0))
    try:
        return proc.wait()
    except KeyboardInterrupt:
        from runner_core import kill_process_tree
        kill_process_tree(proc)
        raise


def print_status(project: Path, policy: dict, origins: dict, epoch: dict, ledger_path: Path):
    print("PROJECT:", project)
    print("ROUTE:", epoch["route"])
    print("ROUTE_EPOCH:", epoch["epoch"])
    print("ROUTE_EFFECTIVE_ROUNDS:", epoch["effective_rounds"])
    print("ROUTE_STAGNATION:", epoch["stagnation"])
    print("ROUTE_EXTENSIONS:", epoch["extensions_used"], "/", policy["max_extensions"])
    print("ROUTE_BUDGET:", total_budget(epoch, policy))
    print("ROUTE_PENDING_REVIEW:", needs_review(epoch, policy) or "none")
    print("ROUTE_POLICY_SOURCES:", json.dumps(origins, ensure_ascii=False))
    print("ROUTE_LEDGER:", ledger_path)


def restore_preflight(project: Path, original: dict, preflight: dict):
    # Do not erase concurrent or partial research outcomes with changed last_run.
    try:
        present = state_read(project)
    except Exception:
        return False
    if present.get("last_run") != original.get("last_run"):
        return False
    # A failed native execution cannot advance the accepted research state.
    # Preserve any partial agent edits in the controller's failure archive
    # before restoring the preflight snapshot.
    if present != preflight:
        archive = HERE / "state" / "failed_preflight" / project_key(project)
        archive.mkdir(parents=True, exist_ok=True)
        import uuid
        atom_json(archive / ("failed-" + uuid.uuid4().hex + ".json"), present)
    atom_json(state_path(project), original)
    return True


def core_completed(project: Path, previous: dict) -> tuple[bool, dict | None, str]:
    try:
        after = state_read(project)
    except Exception as exc:
        return False, None, "Cannot load state after core: " + str(exc)
    run_id = after.get("last_run")
    if not run_id or run_id == previous.get("last_run"):
        return False, after, "Native runner did not create a fresh last_run"
    # Reject path traversal from an untrusted agent-supplied run ID.
    if not isinstance(run_id, str) or '/' in run_id or '\\' in run_id or '..' in run_id:
        return False, after, "Invalid last_run file name"
    report = project / "reports" / f"{run_id}.md"
    if not report.is_file() or report.stat().st_size < 120:
        return False, after, "Native-run report missing/too short"
    return True, after, run_id


def mark_review(epoch: dict, ledger: dict, reason: str):
    epoch["review_pending"] = True
    epoch["review_reason"] = reason
    ledger["events"].append({"type": "REVIEW_SCHEDULED", "route": epoch["route"],
                             "reason": reason, "effective_rounds": epoch["effective_rounds"], "at": stamp()})


def record_round(project: Path, ledger: dict, epoch: dict, policy: dict,
                 after: dict, before_hashes: dict):
    run_id = after["last_run"]
    if run_id in epoch["counted_run_ids"]:
        raise ValueError("Duplicate run_id; refusing double-charge")
    progress, kind, artifacts, blocked = check_signal(project, run_id, before_hashes)
    epoch["counted_run_ids"].append(run_id)
    epoch["last_processed_run"] = run_id
    from research_quality import validate_round, policy_for as quality_policy, SUPPORT_KINDS
    review = validate_round(project, run_id, before_hashes)
    from research_focus import ensure_focus, assess_progress
    ensure_focus(project, epoch, state_read(project))
    relevance = assess_progress(project, epoch, review, artifacts)
    if relevance['mainline_progress'] and not progress:
        relevance.update(mainline_progress=False,
                         reason='ROUTE_SIGNAL lacks a substantive progress claim with fresh evidence')
    progress = progress and relevance['mainline_progress']
    support = (review.get('work_kind') in SUPPORT_KINDS
               or review.get('result_status') == 'SUPPORT_ONLY'
               or relevance['scope'] in {'SUPPORT', 'UNCLASSIFIED'})
    epoch['support_rounds'] = epoch.get('support_rounds', 0) + 1 if support else 0
    if support or review.get('result_status') == 'NO_PROGRESS' or not progress:
        progress, blocked = False, False
    if progress:
        epoch.setdefault('mainline_fingerprints', []).append(relevance['fingerprint'])
    epoch["effective_rounds"] += 1
    epoch["stagnation"] = 0 if progress else epoch["stagnation"] + 1
    # Preserve per-round content hashes at acceptance. Current files cannot be
    # used later to invent the content of a historical research receipt.
    accepted_hashes = evidence_snapshot(project)
    ledger["events"].append({"type": "RESEARCH_ROUND", "route": epoch["route"],
                             "run_id": run_id, "effective_rounds": epoch["effective_rounds"],
                             "substantive_progress_claim": progress, "evidence_type": kind,
                             "changed_evidence_paths": artifacts, "at": stamp(),
                             "goal_alignment": relevance,
                             "anchor_id": epoch['focus']['anchor_id'],
                             "work_kind": review.get('work_kind'), "result_status": review.get('result_status'),
                             "evidence_hashes": {rel: accepted_hashes[rel] for rel in artifacts if rel in accepted_hashes},
                             "note": "Progress is only a procedural signal; proofs and novelty remain unverified."})
    print('MAINLINE_SCOPE:', relevance['scope'], 'MAINLINE_PROGRESS:', progress,
          'REASON:', relevance['reason'])
    if epoch['support_rounds'] >= quality_policy(project)['max_consecutive_support_rounds']:
        mark_review(epoch, ledger, 'support_work_without_theoretical_progress')
    elif blocked and policy["automatic_falsification"]:
        mark_review(epoch, ledger, "evidence_backed_route_blocker")
    else:
        reason = needs_review(epoch, policy)
        if reason:
            mark_review(epoch, ledger, reason)
    return progress, kind


def decision_pause(project: Path, verdict: dict, message: str) -> None:
    state = state_read(project)
    state["decision"] = "NEEDS_REVIEW"
    state["next_task"] = ("等待对科研路线裁决的人工审查。" + message +
                          "；审查 research/ROUTE_VERDICT.json 及本轮报告后再恢复。")
    atom_json(state_path(project), state)


def apply_review(project: Path, ledger: dict, epoch: dict, policy: dict, after: dict) -> str:
    run_id = after["last_run"]
    epoch["last_processed_run"] = run_id
    epoch["review_count"] += 1
    ledger["events"].append({"type": "ROUTE_REVIEW", "run_id": run_id,
                             "route": epoch["route"], "at": stamp()})
    try:
        verdict = load_verdict(project, run_id)
        if verdict['outcome'] in {'REFOCUS', 'EXTEND'}:
            from research_focus import validate_next_task
            validate_next_task(verdict, epoch['focus'])
    except (ValueError, OSError) as exc:
        decision_pause(project, {}, "裁决文件缺失或格式错误：" + str(exc))
        ledger["events"].append({"type": "ROUTE_REVIEW_INVALID", "run_id": run_id,
                                 "error": str(exc), "at": stamp()})
        epoch["review_pending"] = False
        return "PAUSED_INVALID_VERDICT"

    outcome = verdict["outcome"]
    if after.get("decision") in STOP_DECISIONS:
        ledger["events"].append({"type": "NATIVE_REVIEW_HALT", "run_id": run_id,
                                 "decision": after.get("decision"), "at": stamp()})
        epoch["review_pending"] = False
        return "PAUSED_NATIVE_REVIEW_HALT"
    ledger["events"].append({"type": "ROUTE_VERDICT_RECORDED", "run_id": run_id,
                             "outcome": outcome, "reason": verdict["reason"], "at": stamp(),
                             "scope": "PROVISIONAL_UNVERIFIED"})
    if verdict.get("unapproved_goal_change") and policy["require_approval_for_goal_change"]:
        decision_pause(project, verdict, "候选要求改变 GOAL 的不可放宽条件")
        epoch["review_pending"] = False
        return "PAUSED_GOAL_CHANGE"
    if outcome == 'REFOCUS':
        if epoch['effective_rounds'] >= total_budget(epoch, policy):
            decision_pause(project, verdict, '剩余预算为零；REFOCUS 不追加预算，需有界延期裁决')
            epoch['review_pending'] = False
            return 'PAUSED_REFOCUS_BUDGET_EXHAUSTED'
        epoch.update(review_pending=False, review_reason=None, stagnation=0, support_rounds=0)
        revised = state_read(project)
        revised.update(decision='CONTINUE', phase='FALSIFICATION', next_task=verdict['next_task'])
        atom_json(state_path(project), revised)
        ledger['events'].append({'type': 'MAINLINE_REFOCUSED', 'run_id': run_id,
                                'effective_rounds': epoch['effective_rounds'], 'at': stamp()})
        return 'REFOCUSED'
    if outcome == "EXTEND":
        if epoch["extensions_used"] >= policy["max_extensions"]:
            decision_pause(project, verdict, "已达到最大延期次数")
            epoch["review_pending"] = False
            return "PAUSED_EXTENSIONS_EXHAUSTED"
        epoch["extensions_used"] += 1
        epoch["review_pending"] = False
        epoch["review_reason"] = None
        epoch["stagnation"] = 0
        epoch['support_rounds'] = 0
        revised = state_read(project)
        revised["decision"] = "CONTINUE"
        revised['phase'] = 'FALSIFICATION'
        revised["next_task"] = verdict['next_task']
        atom_json(state_path(project), revised)
        ledger["events"].append({"type": "EXTENSION_GRANTED", "route": epoch["route"],
                                 "new_total_budget": total_budget(epoch, policy), "at": stamp()})
        return "EXTENDED"
    if outcome in {"PIVOT_PROVISIONAL", "REJECT_SCOPE_LIMITED"}:
        if not policy["automatic_candidate_discovery"]:
            decision_pause(project, verdict, "自动候选发现已关闭")
            epoch["review_pending"] = False
            return "PAUSED_DISCOVERY_DISABLED"
        chosen = choose_candidate(project, verdict)
        if chosen is None:
            decision_pause(project, verdict, "候选路线没有通过证据、目标兼容和新命题检查")
            epoch["review_pending"] = False
            return "PAUSED_NO_ELIGIBLE_CANDIDATE"
        target = chosen["route"].rstrip("/")
        if target == epoch["route"] or target.split("/")[0] == epoch["route"].split("/")[0]:
            decision_pause(project, verdict, "候选仍属当前路线，无有效跨路线转移")
            epoch["review_pending"] = False
            return "PAUSED_NO_ROUTE_CHANGE"
        state = state_read(project)
        state["phase"] = "FALSIFICATION"
        state["decision"] = "CONTINUE"
        previous_idea = state.get('selected_idea')
        if previous_idea is not None:
            state['origin_idea'] = previous_idea
        state['selected_idea'] = None
        # Active cards remain versioned; the old card no longer governs a pivoted task.
        index_path = project / 'ideas/INDEX.json'
        if index_path.is_file():
            idea_index = read_json(index_path)
            idea_index['active_idea'] = None
            idea_index.setdefault('events', []).append({'type': 'AUTO_ROUTE_PIVOT',
                'origin_idea': previous_idea, 'route': target, 'at': stamp()})
            atom_json(index_path, idea_index)
        state["research_route"] = target if "/" in target else target + "/FEASIBILITY"
        state["priority_problem"] = chosen["priority_problem"]
        state["next_task"] = chosen["next_task"]
        # Keep verified_results/publication_status/GOAL unchanged.
        atom_json(state_path(project), state)
        epoch["review_pending"] = False
        epoch["closed"] = True
        ledger["events"].append({"type": "PROVISIONAL_ROUTE_PIVOT", "from": epoch["route"],
                                 "to": state["research_route"], "origin_idea": previous_idea, "at": stamp(),
                                 "note": "Comparative feasibility work, not a universal impossibility proof."})
        return "PIVOT_PROVISIONAL"
    decision_pause(project, verdict, "审查结论为 PAUSE_FOR_REVIEW")
    epoch["review_pending"] = False
    return "PAUSED_FOR_REVIEW"


def finish_status(project: Path, *, accepted: bool, outcome: str, run_id=None, archive=None,
                  supervision_result=None, knowledge_result=None):
    from runner_core import git_checkpoint
    status_path = HERE / 'logs' / project_key(project) / 'latest-status.json'
    status = read_json(status_path) if status_path.exists() else {}
    status.update({'wrapper_accepted': accepted, 'route_outcome': outcome})
    if supervision_result is not None:
        status['supervision'] = supervision_result
    if knowledge_result is not None:
        status['knowledge_index'] = knowledge_result
    if not accepted:
        status['status'] = 'INCOMPLETE'
        status['failure_archive'] = archive
        status['git_checkpoint'] = 'SKIPPED_UNSUCCESSFUL_ROUND'
    elif run_id:
        status['git_checkpoint'] = git_checkpoint(project, run_id)
    atom_json(status_path, status)
    if status.get('run_id'):
        atom_json(status_path.parent / (status['run_id'] + '.status.json'), status)


def supervise_safely(project: Path, ledger: dict, epoch: dict, policy: dict) -> dict:
    # Lock contention, invalid policy, or journal recovery can fail before the
    # supervisor creates its own attempt. They still block the next model call,
    # while an already accepted research round retains its accepted status.
    try:
        from supervision_scheduler import enabled, before_run
        from supervision_runtime import disabled, queue_before
        if disabled(HERE, project): return {'status': 'disabled', 'proceed': True}
        if enabled(HERE, project):
            return queue_before(HERE, project, ledger, epoch,
                route_lock_held=True, effective_route_policy=policy)
        from supervision import maybe_supervise
        return maybe_supervise(HERE, project, ledger,
            budget_reason=('budget_exhausted'
                           if epoch['effective_rounds'] >= total_budget(epoch, policy) else None))
    except Exception as exc:
        print('SUPERVISION_ERROR:', str(exc), file=sys.stderr, flush=True)
        return {'status': 'failed', 'proceed': False, 'error': str(exc)}


def queue_supervision_after_accept(project, ledger, epoch, policy, run_id, *, reviewed):
    try:
        from supervision_scheduler import record_postaccept
        return record_postaccept(HERE, project, ledger, epoch, run_id, reviewed=reviewed,
            review_required=bool(needs_review(epoch, policy)), route_lock_held=True, effective_route_policy=policy)
    except Exception as exc:
        print('SUPERVISION_QUEUE_ERROR:', str(exc), file=sys.stderr, flush=True)
        return {'status': 'failed', 'proceed': False, 'error': str(exc)}


def refresh_knowledge(project: Path, *, execution_lock_held=False) -> dict:
    """Materialise accepted sources under the execution lock, without a model."""
    try:
        from engine.knowledge_graph import refresh
        from contextlib import nullcontext
        with (nullcontext() if execution_lock_held else file_lock(HERE / 'locks' / (project_key(project) + '.lock'))):
            return {'status': 'refreshed', **refresh(project)}
    except Exception as exc:
        print('KNOWLEDGE_INDEX_ERROR:', str(exc), file=sys.stderr, flush=True)
        return {'status': 'failed', 'error': str(exc)}


def continue_accepted(project, policy, journal):
    """Roll forward a committed run; never call the research model here."""
    import research_acceptance as acceptance
    from engine import discovery_scheduler as discovery
    owner=journal.get('discovery_owner_attempt_id')
    if owner is not None and journal.get('step_active')=='discovery':
        try:
            observation=discovery.settlement_observation(project,owner,journal['run_id'])
        except ValueError:
            # An unknown check has no trusted afterimage. The step below will
            # stop rather than repeat it; unrelated project edits still fail CAS.
            observation=None
        if observation is not None:
            if (journal['expected_manifest'] not in (observation['project_before_checks'],observation['project_after_checks'])
                    or acceptance.manifest(project)!=observation['project_after_checks']):
                raise ValueError('ACCEPTANCE_PROJECT_CHANGED: completed local check afterimage mismatch')
            journal['expected_manifest']=observation['project_after_checks']
            acceptance.write(HERE,project,journal)
    acceptance.verify_project(project, journal)
    ledger_path = HERE / journal['route_path']
    def route_commit():
        from route_budget import recover_ledger
        recover_ledger(ledger_path)
        current = read_json(ledger_path) if ledger_path.exists() else None
        if current not in (journal['route_before'], journal['route_after']):
            raise ValueError('ACCEPTANCE_ROUTE_CHANGED: retain both authorities; no new research')
        if current != journal['route_after']:
            save_ledger(ledger_path, journal['route_after'])
        return {'run_id': journal['run_id'], 'ledger_sha256': acceptance.digest(read_json(ledger_path))}
    acceptance.step(HERE, project, journal, 'route', route_commit)
    acceptance.fault_hook('ROUTE_SAVED')
    ledger = read_json(ledger_path)
    epoch = ledger['epochs'][-1]
    if not journal.get('route_output_done'):
        if journal['reviewed']:
            print('ROUTE_DECISION:', journal['outcome'])
        else:
            print('ROUTE_PROGRESS:', journal.get('progress_kind'), 'SUBSTANTIVE_SIGNAL:', journal.get('progress'),
                  'EFFECTIVE_ROUNDS:', epoch['effective_rounds'], 'STAGNATION:', epoch['stagnation'])
        journal['route_output_done'] = True
        acceptance.write(HERE, project, journal)
    if journal['initialization']:
        acceptance.step(HERE, project, journal, 'initialization',
            lambda: __import__('engine.initialization', fromlist=['finalize']).finalize(project, journal['run_id']))
    acceptance.fault_hook('BEFORE_DISCOVERY')
    def discovery_commit():
        from engine.common import ledger as discovery_ledger
        if owner is not None:
            matches=[c for a in discovery_ledger(project)['attempts'] if a['id']==owner
                     for c in a['calls'] if c['run_id']==journal['run_id']]
            if len(matches)!=1: raise ValueError('DISCOVERY_OWNER_MISSING: '+journal['run_id'])
            if matches[0]['status']=='PENDING_WRAPPER' and matches[0]!=journal['discovery_call_before']:
                raise ValueError('DISCOVERY_CALL_CHANGED: '+journal['run_id'])
        discovery.finalize_wrapper(project, True, journal['run_id'],
            **({'expected_attempt_id':owner} if owner is not None else {}))
        if owner is None: return None
        matches=[c for a in discovery_ledger(project)['attempts'] if a['id']==owner
                 for c in a['calls'] if c['run_id']==journal['run_id']]
        if len(matches)!=1 or matches[0]['status']!='ACCEPTED': raise ValueError('DISCOVERY_OWNER_NOT_SETTLED')
        return {'attempt_id':owner,'run_id':journal['run_id'],'call_sha256':acceptance.digest(matches[0])}
    acceptance.step(HERE, project, journal, 'discovery',
                    discovery_commit)
    if owner is not None:
        from engine.common import ledger as discovery_ledger
        matches=[c for a in discovery_ledger(project)['attempts'] if a['id']==owner
                 for c in a['calls'] if c['run_id']==journal['run_id']]
        settled=journal['steps']['discovery']
        if len(matches)!=1 or acceptance.digest(matches[0])!=settled['call_sha256']:
            raise ValueError('DISCOVERY_SETTLED_OWNER_CHANGED')
    knowledge = journal['steps'].get('knowledge')
    if knowledge is None:
        failed_knowledge = None
        def maintain():
            nonlocal failed_knowledge
            result = refresh_knowledge(project, execution_lock_held=True)
            if result['status'] == 'failed':
                # No completion receipt: do not freeze or queue a failed index.
                failed_knowledge = result
                raise RuntimeError('KNOWLEDGE_INDEX_FAILED: ' + result.get('error', 'unknown'))
            return result
        try:
            knowledge = acceptance.step(HERE, project, journal, 'knowledge', maintain)
        except RuntimeError as exc:
            if not str(exc).startswith('KNOWLEDGE_INDEX_FAILED:'): raise
            finish_status(project, accepted=True, outcome=journal['outcome'], run_id=journal['run_id'],
                          knowledge_result=failed_knowledge)
            return 3, 'KNOWLEDGE_INDEX_FAILED'
    queued = acceptance.step(HERE, project, journal, 'queue',
        lambda: queue_supervision_after_accept(project, ledger, epoch, policy, journal['run_id'], reviewed=journal['reviewed']))
    if queued['status'] == 'failed':
        # Failed attempts are not completed queue steps and can be retried safely
        # by the R02 idempotent event API after its own recovery.
        journal['steps'].pop('queue', None)
        acceptance.write(HERE, project, journal)
        finish_status(project, accepted=True, outcome=journal['outcome'], run_id=journal['run_id'], supervision_result=queued)
        return 3, 'SUPERVISION_QUEUE_FAILED'
    supervised = supervise_safely(project, ledger, epoch, policy)
    finish_status(project, accepted=True, outcome=journal['outcome'], run_id=journal['run_id'],
                  supervision_result=supervised, knowledge_result=knowledge)
    acceptance.finish(HERE, project, journal)
    if not supervised.get('proceed', True): return 3, 'SUPERVISION_' + supervised['status'].upper()
    return 0, journal['outcome']


def recover_acceptance(project, policy):
    import research_acceptance as acceptance
    journal = acceptance.load(HERE, project)
    if not journal or journal['phase'] == 'ABORTED': return None
    if journal['phase'] == 'COMPLETE':
        acceptance.archive_complete(HERE, project, journal)
        return None
    # An old core may still own this lock after its wrapper died. In that case
    # recovery must stop before inspecting/restoring any mutable project files.
    with file_lock(HERE / 'locks' / (project_key(project) + '.lock')):
        journal = acceptance.load(HERE, project)
        if journal['phase'] == 'STARTED':
            raise ValueError('RESEARCH_OUTCOME_UNKNOWN: retained precommit snapshot; audit the original run, no automatic retry')
        result = continue_accepted(project, policy, journal)
        return (0, 'RECOVERED_ACCEPTED_ROUND') if result[0] == 0 else result


def advance_one(project: Path, policy: dict, ledger_path: Path, ledger: dict,
                epoch: dict, core_cmd: list[str]) -> tuple[int, str]:
    from runner_core import ProjectTransaction
    import research_acceptance as acceptance
    recovered = recover_acceptance(project, policy)
    if recovered is not None: return recovered
    if (project / '.control/STOP_REQUESTED').exists():
        return 0, 'SKIPPED_BY_STOP_REQUEST'
    before = state_read(project)
    if before['decision'] in STOP_DECISIONS or before['phase'] == 'DONE':
        return 0, 'SKIPPED_BY_RESEARCH_STATE'
    if epoch['last_processed_run'] != before.get('last_run'):
        return 3, ('ROUTE_STATE_DRIFT: a different runner or manual edit changed STATE.last_run. '
                   'Inspect evidence and rerun with --route-sync if intentional.')
    from research_focus import require_current
    require_current(project, epoch, before)
    reason = needs_review(epoch, policy)
    from engine import discovery_scheduler as discovery
    attempt = discovery.check(project)
    if attempt and (reason or epoch['review_pending'] or '--audit' in core_cmd):
        return 3, 'ATTEMPT_PAUSED_FOR_ROUTE_REVIEW: close the fixed attempt and review the route; no model call made'
    if before.get('initialization_required') and (reason or epoch['review_pending'] or '--audit' in core_cmd):
        return 3, 'INITIALIZATION_PAUSED_FOR_ROUTE_REVIEW: review existing route budget before reinitialization; no model call made'
    supervised = supervise_safely(project, ledger, epoch, policy)
    if not supervised.get('proceed', True):
        return 3, 'SUPERVISION_' + supervised['status'].upper()
    if reason and not epoch['review_pending']:
        mark_review(epoch, ledger, reason)
        save_ledger(ledger_path, ledger)
    reviewing = epoch['review_pending']
    if reviewing and not policy['automatic_route_review']:
        state = copy.deepcopy(before)
        state['decision'] = 'NEEDS_REVIEW'
        atom_json(state_path(project), state)
        return 0, 'PAUSED_ROUTE_REVIEW_DISABLED'
    from theory_gate import SYSTEM_PHASES, require_system_ready
    if before['phase'] in SYSTEM_PHASES and not reviewing and '--audit' not in core_cmd:
        require_system_ready(project)
    before_hashes = evidence_snapshot(project)
    # Persist the original authority before dispatch, including its registration
    # witness. A later accepted afterimage always retains this same identity.
    save_ledger(ledger_path, ledger)
    ledger_before = copy.deepcopy(ledger)
    epoch_before = copy.deepcopy(epoch)
    with file_lock(HERE / 'locks' / (project_key(project) + '.lock')):
        if state_read(project) != before:
            raise ValueError('RESEARCH_STATE_CHANGED_BEFORE_DISPATCH: no snapshot or rollback over another core')
        transaction = ProjectTransaction(project).capture()
        journal = acceptance.begin(HERE, project, transaction, ledger_path, ledger)
    accepted = False
    archive = None
    outcome = 'NATIVE_CORE_FAILED'
    pause_reason = None
    preflight = copy.deepcopy(before)
    execution_guard = None
    try:
        preflight['next_task'] = generate_directive(
            selected_route(before), epoch, policy, reviewing, epoch['review_reason'], before['next_task'])
        with file_lock(HERE / 'locks' / (project_key(project) + '.lock')):
            if state_read(project) != before:
                raise ValueError('RESEARCH_STATE_CHANGED_BEFORE_DISPATCH')
            atom_json(state_path(project), preflight)
        print('MODE:', 'ROUTE_REVIEW' if reviewing else 'RESEARCH', 'ROUTE:', epoch['route'],
              'USED:', epoch['effective_rounds'], 'BUDGET:', total_budget(epoch, policy), flush=True)
        command = list(core_cmd)
        if reviewing:
            command = [part for part in command if part != '--audit']
            command.append('--route-review')
        code = run_child(command)
        if code:
            outcome = f'NATIVE_CORE_FAILED exit_code={code}'
            return code, outcome
        # Validate and decide while excluding a directly invoked core as well
        # as other wrappers. No project afterimage may change in this interval.
        candidate_guard = file_lock(HERE / 'locks' / (project_key(project) + '.lock'))
        candidate_guard.__enter__()
        execution_guard = candidate_guard
        okay, after, detail = core_completed(project, before)
        if not okay:
            outcome = 'CORE_SUCCESS_WITHOUT_ACCEPTED_RESEARCH: ' + detail
            return 3, outcome
        if after['next_task'] == preflight['next_task']:
            pause_reason = '本轮未更新 next_task；本轮文件已归档并恢复上一接受状态。'
            outcome = 'NEXT_TASK_NOT_ADVANCED'
            return 3, outcome
        if (after.get('selected_idea') != before.get('selected_idea') or
                after.get('supporting_ideas', []) != before.get('supporting_ideas', [])):
            pause_reason = '本轮研究代理改动了已固定的研究想法版本；已恢复上一接受状态。'
            outcome = 'UNCONTROLLED_IDEA_CHANGE'
            return 3, outcome
        if selected_route(after) != selected_route(before):
            pause_reason = '本轮研究代理绕过路线裁决改动 research_route；已恢复上一接受状态。'
            outcome = 'UNCONTROLLED_ROUTE_CHANGE'
            return 3, outcome
        from research_quality import validate_round
        validate_round(project, after['last_run'], before_hashes)
        from theory_gate import validate_code_changes
        validate_code_changes(project, {rel:meta['sha256'] for rel,meta in transaction.manifest.items()})
        from engine.deep_reasoning import validate_checkpoint
        validate_checkpoint(project, after['last_run'])
        if before.get('initialization_required'):
            __import__('engine.initialization', fromlist=['validate']).validate(project, after['last_run'])
        if reviewing:
            outcome = apply_review(project, ledger, epoch, policy, after)
        else:
            progress, kind = record_round(project, ledger, epoch, policy, after, before_hashes)
            journal.update(progress=progress, progress_kind=kind)
            outcome = 'COUNTED_RESEARCH_ROUND'
        if len(ledger['events']) > 3000: ledger['events'] = ledger['events'][-3000:]
        acceptance.commit(HERE, project, journal, ledger, after['last_run'], outcome,
                          initialization=bool(before.get('initialization_required')), reviewed=reviewing)
        transaction.accept()
        accepted = True
        return continue_accepted(project, policy, journal)
    except KeyboardInterrupt:
        outcome = 'INTERRUPTED'
        raise
    finally:
        try:
            if not accepted and acceptance.committed(HERE, project, transaction.label):
                transaction.accept()
                accepted = True
            if not accepted:
                from contextlib import nullcontext
                with (nullcontext() if execution_guard else file_lock(HERE / 'locks' / (project_key(project) + '.lock'))):
                    archive = transaction.rollback(outcome)
                    ledger.clear(); ledger.update(ledger_before)
                    epoch.clear(); epoch.update(epoch_before)
                    acceptance.abort(HERE, project, journal, outcome)
                    if pause_reason: decision_pause(project, {}, pause_reason)
                    discovery.finalize_wrapper(project, False)
                    finish_status(project, accepted=False, outcome=outcome, archive=archive)
        finally:
            if execution_guard is not None: execution_guard.__exit__(None, None, None)


def main(argv=None) -> int:
    parser, args, unknown = parse_args(argv)
    project = Path(args.project).expanduser().resolve()
    if not (project / "research" / "STATE.json").exists():
        parser.error("Project research/STATE.json is missing")
    if not CORE.is_file():
        parser.error("runner_core.py missing; installation incomplete")
    tmp = {"initial_round_budget": args.route_budget,
           "stagnation_rounds": args.stagnation_rounds,
           "extension_round_budget": args.extension_round_budget,
           "max_extensions": args.max_extensions}
    persistent = {"initial_round_budget": args.set_route_budget,
                  "stagnation_rounds": args.set_stagnation_rounds,
                  "extension_round_budget": args.set_extension_round_budget,
                  "max_extensions": args.set_max_extensions}
    if args.dry_run and (args.route_sync or args.clear_project_route_policy or any(x is not None for x in persistent.values())):
        parser.error('A dry-run cannot be combined with configuration/state changes')
    # Inspection creates no lock, runtime directory, or route ledger.
    if args.dry_run or (args.route_status and not any(x is not None for x in persistent.values()) and not args.route_sync):
        try:
            policy, origins, _ = policy_for(HERE, project, tmp)
            before = state_read(project)
            ledger_path, ledger, epoch = load_ledger(HERE, project, before)
            print_status(project, policy, origins, epoch, ledger_path)
            return run_child(args_to_core(args, unknown)) if args.dry_run else 0
        except (RuntimeError, OSError, ValueError) as exc:
            print('ROUTE_CONTROLLER_ERROR:', str(exc), file=sys.stderr)
            return 3
    lock_path = HERE / 'locks' / ('route-' + project_key(project) + '.lock')
    try:
        with file_lock(lock_path):
            if args.clear_project_route_policy:
                if any(x is not None for x in persistent.values()):
                    parser.error("Cannot combine --clear-project-route-policy with --set-* options")
                _, _, project_policy_path = policy_for(HERE, project)
                if project_policy_path.exists():
                    import uuid
                    path_backup = HERE / "backups" / "route-policy-overrides" / (
                        project_policy_path.name + "." + uuid.uuid4().hex + ".bak")
                    path_backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(project_policy_path, path_backup)
                    existing = read_json(project_policy_path)
                    existing.pop('route_policy', None)
                    atom_json(project_policy_path, existing)
                    print("PROJECT_ROUTE_POLICY_CLEARED:", project_policy_path)
                    print("SAVED_OVERRIDE_BACKUP:", path_backup)
                else:
                    print("PROJECT_ROUTE_POLICY_ALREADY_DEFAULT")
                return 0
            if any(x is not None for x in persistent.values()):
                path = set_project_override(HERE, project, {k: v for k, v in persistent.items() if v is not None})
                print("ROUTE_PROJECT_OVERRIDE_UPDATED:", path)
            policy, origins, _ = policy_for(HERE, project, tmp)
            if args.rounds > policy["max_rounds_per_invocation"]:
                parser.error("--rounds exceeds max_rounds_per_invocation")
            before = state_read(project)
            recovered = recover_acceptance(project, policy)
            if recovered is not None:
                print('ROUND_OUTCOME:', recovered[1], flush=True)
                return recovered[0]
            ledger_path, ledger, epoch = load_ledger(HERE, project, before)
            if args.route_sync:
                if before["last_run"] != epoch["last_processed_run"]:
                    ledger["events"].append({"type": "EXTERNAL_STATE_SYNCHRONIZED", "route": epoch["route"],
                                             "previous": epoch["last_processed_run"],
                                             "new": before["last_run"], "at": stamp(),
                                             "note": "Uncounted: confirm external run manually."})
                    epoch["last_processed_run"] = before["last_run"]
            save_ledger(ledger_path, ledger)
            if args.route_status or args.dry_run:
                print_status(project, policy, origins, epoch, ledger_path)
            if args.route_status or any(x is not None for x in persistent.values()):
                return 0
            if args.dry_run or args.fetch_only or args.prepare_pro:
                return run_child(args_to_core(args, unknown))
        # Science keeps the original route/core locks. Consumption must occur
        # outside those non-reentrant locks and outside ProjectTransaction.
        from supervision_runtime import active, safely
        with file_lock(HERE / 'locks' / ('run-loop-' + project_key(project) + '.lock')):
            for count in range(args.rounds):
                with file_lock(lock_path):
                    state = state_read(project)
                    ledger_path, ledger, epoch = load_ledger(HERE, project, state)
                    if (project / '.control/STOP_REQUESTED').exists() or state['decision'] in STOP_DECISIONS or state['phase'] == 'DONE':
                        return 0
                    if active(HERE, project) and state['decision'] not in STOP_DECISIONS and state['phase'] != 'DONE':
                        recovered = supervise_safely(project, ledger, epoch, policy)
                        if not recovered.get('proceed', True): return 3
                if active(HERE, project):
                    result = safely(HERE, project)
                    if not result['proceed']:
                        print('SUPERVISION_RESULT:', json.dumps(result, ensure_ascii=False), flush=True)
                        return 3
                with file_lock(lock_path):
                    state = state_read(project)
                    ledger_path, ledger, epoch = load_ledger(HERE, project, state)
                    if (project / '.control/STOP_REQUESTED').exists():
                        print('STOP_REQUESTED: stopping before the next round')
                        return 0
                    if state["decision"] in STOP_DECISIONS or state["phase"] == "DONE":
                        print("PROJECT_PAUSED_OR_DONE:", state["decision"], state["phase"])
                        save_ledger(ledger_path, ledger)
                        return 0
                    cmd = args_to_core(args, unknown)
                    # Consecutive executions delegate a *single* Codex round each.
                    code, outcome = advance_one(project, policy, ledger_path, ledger, epoch, cmd)
                    print("ROUND_OUTCOME:", outcome, flush=True)
                if code:
                    return code
                if active(HERE, project):
                    result = safely(HERE, project)
                    print('SUPERVISION_RESULT:', json.dumps(result, ensure_ascii=False), flush=True)
                    if not result['proceed']: return 3
                if outcome.startswith("PAUSED") or outcome.startswith("SKIPPED"):
                    return 0
        return 0
    except (RuntimeError, OSError, ValueError, json.JSONDecodeError) as exc:
        print("ROUTE_CONTROLLER_ERROR:", str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
