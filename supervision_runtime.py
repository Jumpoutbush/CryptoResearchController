"""R05 opt-in orchestration. R02 owns costs; R04 owns guide transactions."""
from pathlib import Path

import configuration
import supervision
import supervision_executor as executor
import supervision_guide as guide
import supervision_ledger as queue
import supervision_scheduler as scheduler
from supervision_snapshot import _path
from route_budget import file_lock, load_ledger, needs_review, policy_for, state_read


def settings(controller, project):
    path = _path(controller, 'state/supervision/' + configuration.project_id(project) + '/automation.json')
    value = configuration.load_json(path, None)
    if value is None:
        owner = _path(controller, 'state/supervision/' + configuration.project_id(project) + '/r05-owner.json')
        if owner.exists(): raise ValueError('BLOCKED_MISSING_AUTOMATION: restore original configuration or explicitly disable')
        return {}
    if (not isinstance(value, dict) or set(value) != {'schema_version', 'project_id', 'enabled', 'backend', 'baseline_run_ids'}
            or value['schema_version'] != 1 or value['project_id'] != configuration.project_id(project)
            or type(value['enabled']) is not bool or value['backend'] not in {'codex', 'fake'}
            or not isinstance(value['baseline_run_ids'], list)
            or any(not isinstance(r, str) for r in value['baseline_run_ids'])):
        raise ValueError('Invalid supervision automation configuration')
    return value


def active(controller, project):
    return settings(controller, project).get('enabled', False)


def disabled(controller, project):
    value = settings(controller, project)
    return bool(value) and not value['enabled']


def preview_configuration(controller, project, *, enabled, backend='codex'):
    queue.home(controller, project)
    if enabled and backend == 'fake':
        try: guide._require_fixture(controller, project)
        except OSError as exc: raise ValueError('FAKE_NOT_DISPOSABLE_FIXTURE') from exc
    policy = supervision.policy_for(controller, project)
    if enabled: data = supervision._load(controller, project) or {}
    else:
        try: data = supervision._load(controller, project) or {}
        except (ValueError, OSError): data = {'attempts_used': None, 'seconds_used': None}
    return {'project_id': configuration.project_id(project), 'enabled': enabled, 'backend': backend,
        'max_reviews': policy['max_reviews'], 'max_seconds_per_call': policy['max_seconds'],
        'max_total_seconds': policy['max_total_seconds'], 'attempts_used': data.get('attempts_used', 0),
        'seconds_used': data.get('seconds_used', 0), 'calls_per_event': 1,
        'real_backend_blocked': True, 'historical_backfill': False}


def configure(controller, project, *, enabled, backend='codex'):
    preview = preview_configuration(controller, project, enabled=enabled, backend=backend)
    with scheduler._locks(controller, project, execution=True):
        try: old = settings(controller, project)
        except ValueError:
            if enabled: raise
            old = {}
        owner = _path(controller, 'state/supervision/' + configuration.project_id(project) + '/r05-owner.json')
        if not owner.exists():
            queue._write_immutable(owner, {'schema_version': 1, 'project_id': configuration.project_id(project),
                                           'protocol': 'R05_NO_LEGACY_FALLBACK'})
        if not enabled:
            # Emergency stop does not parse or repair cost/queue/guide history.
            value = {'schema_version': 1, 'project_id': configuration.project_id(project),
                'enabled': False, 'backend': old.get('backend', 'codex'),
                'baseline_run_ids': old.get('baseline_run_ids', [])}
            supervision._write(_path(controller, 'state/supervision/' + configuration.project_id(project) + '/automation.json'),
                               supervision._json_bytes(value))
            path = _path(controller, 'config/projects/' + configuration.project_id(project) + '.json')
            override = configuration.load_json(path, {})
            configuration.atomic_json(path, {**override, 'supervision_policy': {
                **override.get('supervision_policy', {}), 'enabled': False}})
            return preview
        if (old and old['enabled'] == enabled and (not enabled or old['backend'] == backend)
                and supervision.policy_for(controller, project)['enabled'] == enabled): return preview
        if enabled and backend == 'fake': guide._require_fixture(controller, project)
        data = supervision._load(controller, project)
        queue.reservations(controller, project)  # Missing cost authority must not re-enroll at zero.
        if enabled and data and data.get('pending_transaction'):
            raise ValueError('Legacy supervision transaction requires explicit recovery before enabling')
        state = state_read(Path(project))
        _, ledger, _ = load_ledger(Path(controller), Path(project), state)
        baseline = supervision._accepted(ledger)
        if state.get('last_run') and state['last_run'] not in baseline: baseline.append(state['last_run'])
        value = {'schema_version': 1, 'project_id': configuration.project_id(project),
            'enabled': enabled, 'backend': backend if enabled else old.get('backend', 'codex'),
            'baseline_run_ids': baseline}
        target = _path(controller, 'state/supervision/' + configuration.project_id(project) + '/automation.json')
        # Disable sentinel first: a crash must never fall into the legacy model
        # runner between the two activation gates. Existing costs stay intact.
        supervision._write(target, supervision._json_bytes({**value, 'enabled': False}))
        supervision.configure(controller, project, {'enabled': enabled})
        supervision._write(target, supervision._json_bytes(value))
    return preview


def queue_before(controller, project, ledger, epoch, *, route_lock_held=False, effective_route_policy=None):
    value = settings(controller, project)
    if value and not value['enabled']: return {'status': 'disabled', 'proceed': True}
    if value and state_read(Path(project)).get('last_run') in value['baseline_run_ids']:
        return {'status': 'enrollment_boundary', 'proceed': True}
    return scheduler.before_run(controller, project, ledger, epoch,
        review_required=bool(needs_review(epoch, effective_route_policy or policy_for(Path(controller), Path(project))[0])),
        route_lock_held=route_lock_held, effective_route_policy=effective_route_policy)


def process(controller, project, *, executor_override=None, dry_run=False):
    """Outside science locks. Replay original receipts; never rerun research."""
    value = settings(controller, project)
    if not value.get('enabled'): return {'status': 'disabled', 'proceed': True}
    if value['backend'] == 'fake' or executor_override is not None: guide._require_fixture(controller, project)
    view = scheduler.pending(controller, project)
    if dry_run: return {'status': 'DRY_RUN', 'proceed': True, 'queue': view, 'backend': value['backend']}
    restriction = scheduler.restrictions(controller, project)
    if not restriction['claim_allowed']:
        return {'status': 'blocked', 'proceed': False, 'reason': restriction['restrictions']}
    if 'ACTIVE_ATTEMPT_READONLY' in restriction['restrictions']:
        return {'status': 'deferred_to_fixed_attempt', 'proceed': True}
    # Original formal review has priority, including pending deferrals.
    # Recover the committed accepted boundary even when notification died before
    # the first event write. Existing missing immutable inputs were checked above.
    with file_lock(_path(controller, 'locks/route-' + configuration.project_id(project) + '.lock')):
        _, ledger, epoch = load_ledger(Path(controller), Path(project), state_read(Path(project)))
        queue_before(controller, project, ledger, epoch, route_lock_held=True)
    view = scheduler.pending(controller, project)
    if needs_review(epoch, policy_for(Path(controller), Path(project))[0]):
        return {'status': 'deferred_to_route_review', 'proceed': True}
    results = []
    for item in view['events']:
        event = item['event_id']; guidance = item.get('guidance') or {}
        if guidance.get('recovery_required'):
            result = guide.recover(controller, project, event)
        elif item['state'] == 'APPLIED' or guidance.get('state') in {'ROLLED_BACK', 'REJECTED_STALE'}:
            continue
        elif item['state'] in {'FAILED', 'REJECTED', 'CONFLICT'}:
            return {'status': 'blocked', 'proceed': False, 'event_id': event, 'reason': item['state']}
        else:
            backend = executor_override or (executor.FakeSupervisorExecutor() if value['backend'] == 'fake'
                                            else executor.CodexSupervisorExecutor())
            result = executor.execute(controller, project, event, executor=backend)
            if result.get('state') == 'PROPOSED' and result['status'] == 'COMPLETED':
                plan = guide.preview(controller, project, event)
                result = guide.apply(controller, project, event, expected_hash=plan['old_guide_sha256'])
        results.append({'event_id': event, **result})
        if result.get('status') not in {'APPLIED', 'ROLLED_BACK'}:
            return {'status': 'blocked', 'proceed': False, 'results': results,
                    'reason': result.get('reason', result.get('status')), 'automatic_retry_allowed': False}
    return {'status': 'completed' if results else 'idle', 'proceed': True, 'results': results}


def safely(controller, project):
    try: return process(controller, project)
    except Exception as exc: return {'status': 'failed', 'proceed': False, 'error': str(exc)}
