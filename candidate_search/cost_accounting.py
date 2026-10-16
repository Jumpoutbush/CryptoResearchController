"""Read existing research/attempt/supervision authority; never count a new round."""
from __future__ import annotations
import copy
import configuration
import research_acceptance
import route_budget
from engine import discovery_scheduler
from engine.common import identifier, ledger, ledger_path
from research_quality import hash_file, read_object
from . import catalog, validate

UNKNOWN_PHASES = frozenset({'RESERVED', 'PENDING_WRAPPER', 'SETTLING', 'SETTLEMENT_READY'})


def _sha(path):
    path = catalog._unlinked(path)
    return hash_file(path) if path.is_file() else None


def discovery(project):
    catalog._unlinked(ledger_path(project))
    value = ledger(project)
    try:
        if value['schema_version'] != 1 or not isinstance(value['attempts'], list): raise ValueError('Invalid discovery ledger')
        owners = set(); runs = set()
        for attempt in value['attempts']:
            identifier(attempt['id'])
            if attempt['id'] in owners: raise ValueError('Duplicate discovery owner')
            owners.add(attempt['id'])
            if not isinstance(attempt['calls'], list): raise ValueError('Invalid discovery calls')
            for call in attempt['calls']:
                identifier(call['run_id'])
                if call['run_id'] in runs: raise ValueError('Ambiguous discovery run owner')
                runs.add(call['run_id'])
                if call['status'] not in UNKNOWN_PHASES | {'ACCEPTED', 'FAILED'}:
                    raise ValueError('Unknown discovery call phase')
        if value.get('active_attempt') is not None and value['active_attempt'] not in owners:
            raise ValueError('Discovery active owner is missing')
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError('Corrupt original discovery ledger; explicit audit required') from exc
    return value


def read(project):
    project, key = catalog._project(project)
    current = catalog.anchor(project)
    state = read_object(validate.safe(project, 'research/STATE.json'))
    route_path, route, epoch = route_budget.load_ledger(configuration.ROOT, project, state)
    policy, _, _ = route_budget.policy_for(configuration.ROOT, project)
    data = discovery(project)
    active = next((a for a in data['attempts'] if a['id'] == data.get('active_attempt')), None)
    unresolved = [{'attempt_id':a['id'], 'run_id':c['run_id'], 'phase':c['status']}
                  for a in data['attempts'] for c in a['calls'] if c['status'] in UNKNOWN_PHASES]
    acceptance_path = catalog._unlinked(research_acceptance.path_for(configuration.ROOT, project))
    acceptance = research_acceptance.load(configuration.ROOT, project)
    pending = bool(acceptance and acceptance['phase'] in {'STARTED', 'COMMIT_DECIDED'})
    if active:
        try: discovery_scheduler.check(project); attempt_preflight = 'READY'
        except ValueError as exc: attempt_preflight = str(exc)
    else: attempt_preflight = 'NO_ACTIVE_ATTEMPT'
    import supervision_ledger
    supervision_path = catalog._unlinked(configuration.ROOT / 'state/supervision' / key / 'ledger.json')
    supervision_data, reservations = supervision_ledger.reservations(configuration.ROOT, project)
    review_reason = route_budget.needs_review(epoch, policy)
    total = route_budget.total_budget(epoch, policy)
    snapshot = {**current, 'last_processed_run': epoch['last_processed_run'],
        'route_sha256': _sha(route_path), 'route_registry_sha256': _sha(route_budget.registry_path(route_path)),
        'discovery_sha256': _sha(ledger_path(project)), 'catalog_sha256': _sha(catalog.path(project)),
        'acceptance_sha256': _sha(acceptance_path), 'supervision_sha256': _sha(supervision_path),
        'route_policy_sha256': _sha(configuration.ROOT / 'config/route_policy.json'),
        'project_policy_sha256': _sha(configuration.ROOT / 'config/projects' / (key + '.json')),
        'discovery_policy_sha256': _sha(configuration.ROOT / 'config/discovery_defaults.json'),
        'defaults_sha256': _sha(configuration.ROOT / 'config/defaults.json'),
        'candidate_policy_sha256': _sha(configuration.ROOT / 'config/candidate_policy.json'),
        'supervision_operations_sha256': _sha(supervision_ledger.home(configuration.ROOT, project) / 'events.jsonl'),
        'stop_requested': (project / '.control/STOP_REQUESTED').exists(),
        'project_manifest': research_acceptance.manifest(project),
        'route_counted_run_ids': list(epoch['counted_run_ids']),
        'known_discovery_run_ids': [c['run_id'] for a in data['attempts'] for c in a['calls']]}
    return {'snapshot':snapshot, 'state':state, 'route':route, 'epoch':epoch,
        'route_budget': {'source':route_path.relative_to(configuration.ROOT).as_posix(),
            'effective_rounds':epoch['effective_rounds'], 'total_budget':total,
            'remaining_rounds':max(0,total-epoch['effective_rounds']), 'review_reason':review_reason,
            'extensions_used':epoch['extensions_used'], 'authoritative':True},
        'attempt_budget': {'source':ledger_path(project).relative_to(configuration.ROOT).as_posix(),
            'active_attempt_id':active['id'] if active else None,
            'calls_consumed':len(active['calls']) if active else 0,
            'budget':active['budget'] if active else None,
            'remaining_calls':max(0,active['budget']-len(active['calls'])) if active else None,
            'failed_calls':[c['run_id'] for a in data['attempts'] for c in a['calls'] if c['status']=='FAILED'],
            'unresolved_calls':unresolved, 'preflight':attempt_preflight},
        'supervision_budget': {'source':supervision_path.relative_to(configuration.ROOT).as_posix(),
            'enrolled':supervision_data is not None,
            'attempts_used':supervision_data['attempts_used'] if supervision_data else None,
            'seconds_used':supervision_data['seconds_used'] if supervision_data else None,
            'event_reservations':{key:{'state':value['state'],'call_count':value['call_count']}
                                  for key,value in reservations.items()},
            'accounting':'SEPARATE_EXISTING_LEDGER_ONLY'},
        'active':copy.deepcopy(active), 'acceptance_pending':pending, 'unresolved':unresolved,
        'route_state_drift':state.get('last_run')!=epoch['last_processed_run'],
        'discovery':data}


def trusted_run(project, run_id, attempt_id):
    """Require the original owner-bound terminal receipt, including failed calls."""
    identifier(run_id); identifier(attempt_id)
    data = discovery(project)
    owners = [(a,c) for a in data['attempts'] for c in a['calls'] if c['run_id']==run_id]
    if len(owners) != 1 or owners[0][0]['id'] != attempt_id: raise ValueError('Original run/attempt owner mismatch')
    attempt, call = owners[0]
    if call['status'] not in {'ACCEPTED','FAILED'}:
        raise ValueError('UNKNOWN_EXTERNAL_OUTCOME: pending original call cannot be mapped or retried')
    receipt_path = catalog._unlinked(discovery_scheduler._settlement_path(project, attempt_id, run_id))
    catalog._unlinked(receipt_path.with_suffix('.started.json'))
    discovery_scheduler._verify_terminal(project, attempt, call, required=True, accepted=call['status']=='ACCEPTED')
    receipt = discovery_scheduler.settlement_observation(project, attempt_id, run_id)
    view = read(project)
    route_event = None; acceptance_epochs=[]
    if call['status']=='ACCEPTED':
        events = [event for event in view['route']['events']
                  if event.get('type')=='RESEARCH_ROUND' and event.get('run_id')==run_id]
        counted = [e for e in view['route']['epochs'] if run_id in e['counted_run_ids']]
        if len(events)!=1 or not counted: raise ValueError('Original accepted route receipt is unavailable')
        route_event=events[0]
        # A post-binding accepted run must have the original wrapper's durable
        # COMPLETE receipt. Legacy strings alone cannot invent acceptance.
        latest=research_acceptance.path_for(configuration.ROOT,project)
        archive=latest.parent/configuration.project_id(project)
        paths=([latest] if latest.is_file() else [])+list(archive.glob('*.json'))
        if len(paths)>10000: raise ValueError('Acceptance receipt history limit exceeded')
        matches=[]
        from engine.common import object_hash
        for path in paths:
            catalog._unlinked(path)
            journal=configuration.load_json(path)
            if not isinstance(journal,dict): raise ValueError('Invalid original acceptance archive')
            if journal.get('run_id')!=run_id: continue
            if (type(journal.get('schema_version')) is not int or journal['schema_version']!=1
                    or journal.get('project_id')!=configuration.project_id(project)
                    or journal.get('phase')!='COMPLETE'
                    or journal.get('discovery_owner_attempt_id')!=attempt_id
                    or journal.get('journal_sha256')!=research_acceptance.digest({
                        k:v for k,v in journal.items() if k!='journal_sha256'})):
                raise ValueError('Original COMPLETE acceptance receipt binding is invalid')
            after=journal.get('route_after',{})
            archived_events=[e for e in after.get('events',[]) if e.get('type')=='RESEARCH_ROUND' and e.get('run_id')==run_id]
            if (len(archived_events)!=1 or archived_events[0]!=route_event
                    or not any(run_id in e.get('counted_run_ids',[]) for e in after.get('epochs',[]))):
                raise ValueError('Original COMPLETE acceptance route image changed')
            matches.append(journal)
        if not matches or any(record!=matches[0] for record in matches):
            raise ValueError('Original COMPLETE acceptance receipt is missing or ambiguous')
        acceptance_epochs=copy.deepcopy(matches[0]['route_after']['epochs'])
    elif any(run_id in e['counted_run_ids'] for e in view['route']['epochs']):
        raise ValueError('Failed original call cannot be counted as an accepted research round')
    return {'attempt':attempt, 'call':copy.deepcopy(call), 'settlement_sha256':receipt['receipt_sha256'],
            'route_event':copy.deepcopy(route_event), 'acceptance_route_epochs':acceptance_epochs,
            'ledger_sha256':view['snapshot']['discovery_sha256']}
