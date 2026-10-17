"""Deterministic candidate advice, never a second research executor or budget."""
from __future__ import annotations
import contextlib
import copy
import json
import re
from pathlib import Path
import configuration
import route_budget
from engine import claim_graph, falsification
from engine.common import fresh, identifier, object_hash, text
from research_quality import hash_file
from . import catalog, cost_accounting as costs, model, validate


def history_path(project):
    return catalog._unlinked(catalog.path(project).parent / 'selections.json')


def registry_path(project):
    _, key = catalog._project(project)
    return catalog._unlinked(configuration.ROOT / 'state/candidate_selection_registry' / (key + '.json'))


def _empty(project):
    return {'schema_version':1, 'project_id':configuration.project_id(project), 'events':[]}


def _digest_file(path):
    return hash_file(path) if path.is_file() else None


def _validate_history(project, data):
    try:
        if (set(data)!={'schema_version','project_id','events'} or type(data['schema_version']) is not int
                or data['schema_version']!=1 or data['project_id']!=configuration.project_id(project)
                or not isinstance(data['events'],list) or len(data['events'])>20000):
            raise ValueError('Invalid candidate selection history')
        previous=None; selections={}; bindings={}; runs={}
        for number,event in enumerate(data['events'],1):
            if (type(event['sequence']) is not int or event['sequence']!=number or event['previous_sha256']!=previous
                    or event['sha256']!=object_hash({k:v for k,v in event.items() if k!='sha256'})):
                raise ValueError('Candidate selection event chain changed')
            text(event['reason'],'selection reason'); text(event['at'],'selection timestamp')
            item=event['payload']; kind=event['type']
            if kind=='SELECTED':
                sid=item['selection_id']; identifier(item['candidate_id'])
                validate.positive_integer(item['candidate_revision'],'candidate revision')
                if (sid in selections or item['snapshot_sha256']!=object_hash(item['snapshot'])
                        or item['scientific_acceptance'] is not False):
                    raise ValueError('Duplicate or corrupt selection identity')
                if sid!='S-'+object_hash({'candidate_id':item['candidate_id'],
                        'candidate_revision':item['candidate_revision'],'snapshot_sha256':item['snapshot_sha256']})[:32]:
                    raise ValueError('Invalid deterministic selection identity')
                selections[sid]=item
            elif kind=='ATTEMPT_BOUND':
                sid=item['selection_id']; aid=identifier(item['attempt_id'])
                if (sid not in selections or aid in bindings or item['calls_at_binding']!=[]
                        or item['attribution_scope']!='OPERATOR_ASSIGNED_SCHEDULING_PROVENANCE'
                        or item['candidate_injection_proven'] is not False):
                    raise ValueError('Invalid pre-dispatch candidate ownership history')
                bindings[aid]=item
            elif kind=='RUN_MAPPED':
                run=identifier(item['run_id']); aid=item['attempt_id']; sid=item['selection_id']
                if (run in runs or aid not in bindings or bindings[aid]['selection_id']!=sid
                        or item['call_status'] not in {'ACCEPTED','FAILED'}
                        or item['attribution_scope']!='OPERATOR_ASSIGNED_SCHEDULING_PROVENANCE'
                        or item['scientific_acceptance'] is not False):
                    raise ValueError('Invalid or duplicate candidate run mapping history')
                runs[run]=item
            else: raise ValueError('Unknown candidate selection event')
            previous=event['sha256']
    except (KeyError,TypeError,AttributeError) as exc:
        raise ValueError('Corrupt candidate selection history; preserve and audit') from exc
    return data


def _registry(project):
    value=configuration.load_json(registry_path(project))
    if value is None: return None
    if (not isinstance(value,dict) or set(value)!={'schema_version','project_id','committed_sha256','pending','sha256'}
            or type(value['schema_version']) is not int or value['schema_version']!=1 or value['project_id']!=configuration.project_id(project)
            or value['sha256']!=object_hash({k:v for k,v in value.items() if k!='sha256'})):
        raise ValueError('Candidate selection registry changed; explicit audit required')
    committed=value['committed_sha256']
    if committed is not None and (not isinstance(committed,str) or not re.fullmatch('[0-9a-f]{64}',committed)):
        raise ValueError('Invalid candidate selection high-water digest')
    return value


def _write_registry(project, value):
    value['sha256']=object_hash({k:v for k,v in value.items() if k!='sha256'})
    configuration.atomic_json(registry_path(project),value)


def _load(project, *, request_sha256=None):
    path=history_path(project); registry=_registry(project)
    if registry is None:
        if path.exists(): raise ValueError('Candidate selection registry is missing; do not silently re-enroll')
        return _empty(project)
    pending=registry['pending']
    if pending is not None:
        if (not isinstance(pending,dict) or set(pending)!={
                'request_sha256','beforeimage_sha256','afterimage_sha256','afterimage'}):
            raise ValueError('Invalid frozen candidate selection recovery receipt')
        if (pending['beforeimage_sha256']!=registry['committed_sha256']
                or any(not isinstance(pending[k],str) or not re.fullmatch('[0-9a-f]{64}',pending[k])
                       for k in ('request_sha256','afterimage_sha256'))):
            raise ValueError('Candidate selection recovery high-water binding changed')
        if request_sha256 is None or pending['request_sha256']!=request_sha256:
            raise ValueError('SELECTION_RECOVERY_REQUIRED: replay only the original frozen local operation')
        after=pending['afterimage']; _validate_history(project,after)
        if object_hash(after)!=pending['afterimage_sha256']:
            raise ValueError('Frozen candidate selection recovery image changed')
        prefix={**after,'events':after['events'][:-1]}
        if (not after['events'] or (pending['beforeimage_sha256'] is None and len(after['events'])!=1)
                or (pending['beforeimage_sha256'] is not None and object_hash(prefix)!=pending['beforeimage_sha256'])):
            raise ValueError('Candidate selection recovery does not append to the committed prefix')
        current=configuration.load_json(path)
        current_hash=object_hash(current) if current is not None else None
        if current_hash not in {pending['beforeimage_sha256'],pending['afterimage_sha256']}:
            raise ValueError('Candidate selection recovery inputs changed; explicit audit required')
        if current_hash!=pending['afterimage_sha256']: configuration.atomic_json(path,after)
        registry['committed_sha256']=pending['afterimage_sha256']; registry['pending']=None
        _write_registry(project,registry)
    if not path.is_file(): raise ValueError('Registered candidate selection history is missing')
    value=_validate_history(project,configuration.load_json(path))
    if object_hash(value)!=registry['committed_sha256']:
        raise ValueError('Candidate selection history differs from its independent high-water witness')
    return value


def _append(project,data,kind,payload,reason,request_sha256):
    before=object_hash(data) if history_path(project).is_file() else None
    event={'sequence':len(data['events'])+1,'previous_sha256':data['events'][-1]['sha256'] if data['events'] else None,
           'type':kind,'payload':copy.deepcopy(payload),'reason':reason,'at':route_budget.stamp()}
    event['sha256']=object_hash(event); data=copy.deepcopy(data); data['events'].append(event)
    _validate_history(project,data)
    registry={'schema_version':1,'project_id':configuration.project_id(project),
        'committed_sha256':before,'pending':{'request_sha256':request_sha256,
            'beforeimage_sha256':before,'afterimage_sha256':object_hash(data),'afterimage':data}}
    _write_registry(project,registry)
    configuration.atomic_json(history_path(project),data)
    registry['committed_sha256']=object_hash(data); registry['pending']=None
    _write_registry(project,registry)
    return data


@contextlib.contextmanager
def _locks(project, locks_held):
    _,key=catalog._project(project)
    with contextlib.ExitStack() as stack:
        if not locks_held:
            for name in ('route-'+key+'.lock',key+'.lock'):
                stack.enter_context(route_budget.file_lock(catalog._unlinked(configuration.ROOT/'locks'/name)))
        for name in ('candidates-'+key+'.lock','candidate-selection-'+key+'.lock'):
            stack.enter_context(route_budget.file_lock(catalog._unlinked(configuration.ROOT/'locks'/name)))
        yield


def _fact(project,relative,locator,scope,verification):
    file=validate.safe(project,relative)
    return {'source_file':relative,'sha256':hash_file(file),'locator':locator,
            'scope':scope,'verification_status':verification}


def _dimension(status='UNKNOWN',facts=None,task='Obtain and independently check the exact evidence before ranking this dimension.'):
    return {'status':status,'facts':facts or [],'next_task':task,'positive_basis':False}


def _rank(project,candidate):
    spec=candidate['spec']; decisive=0; obstacle=0
    dimensions={name:_dimension() for name in ('decisive_falsification','prior_coverage','security_obstacle','goal_link','cost')}
    claim_items={}; statuses={}
    if spec['dependency_claims']:
        validate.safe(project,'research/discovery/CLAIM_GRAPH.json')
        claim_items={c['id']:c for c in claim_graph.load(project)['claims']}
        statuses={c['id']:c for c in claim_graph.status(project)['claims']}
    for pin in spec['dependency_claims']:
        item=claim_items.get(pin['id']); state=statuses.get(pin['id'],{})
        if (not item or item['revision']!=pin['revision'] or item['spec_sha256']!=pin['spec_sha256']
                or not fresh(project,item['evidence']) or not claim_graph.dependency_bindings_valid(item)
                or not claim_graph.receipt_history_valid(item,claim_graph.load(project).get('events'))
                or any(reason!='MACHINE_STATEMENT_REFUTED' for reason in state.get('invalidation_reasons',[]))):
            continue
        fact=_fact(project,'research/discovery/CLAIM_GRAPH.json','claim:'+pin['id']+'@'+str(pin['revision']),
                   'DECLARED_NECESSARY_DEPENDENCY_ONLY',state.get('proof_status','UNKNOWN'))
        if state.get('proof_status')!='INDEPENDENTLY_REVIEWED':
            obstacle=1
            dimensions['security_obstacle']=_dimension('INDEPENDENT_DEPENDENCY_REVIEW_REQUIRED',[fact],
                'Independently check the exact necessary dependency '+pin['id']+'; an unresolved lemma is not a proved security obstruction.')
        statement=item['spec'].get('machine_statement')
        try:
            falsification.validate_statement(statement)
            decisive=1
            dimensions['decisive_falsification']=_dimension('COMPUTABLE_PREDICATE_PENDING',[fact],
                'Use the existing exact-integer verifier on pinned dependency '+pin['id']+
                '; independently verify its implication for this candidate before rejecting the branch.')
        except (ValueError,TypeError): pass
    if not candidate['readiness_reasons']:
        dimensions['goal_link']=_dimension('FROZEN_PROBLEM_PIN_CURRENT',[
            _fact(project,'research/discovery/PROBLEMS.json','problem:'+candidate['problem_binding']['id'],
                  'STRUCTURAL_FROZEN_TARGET_LINK_ONLY','USER_FROZEN_PROBLEM')],
            'Resolve the unchanged fixed proof obligations; structural linkage is not scientific progress.')
    measured=len(json.dumps(spec,sort_keys=True,ensure_ascii=False).encode('utf8'))
    measured+=sum(validate.safe(project,p).stat().st_size for p in candidate['evidence_bindings']
                  if fresh(project,{p:candidate['evidence_bindings'][p]}))
    # Reviewed supporting lemmas do not certify the candidate's own security.
    # Until an exact candidate-level receipt exists, size is display-only for all.
    safe_for_cost=False
    dimensions['cost']={'status':'UNKNOWN_CANDIDATE_SECURITY_COST_DISPLAY_ONLY',
        'measured_input_bytes':measured,'declared_estimated_context_bytes':spec['estimated_context_bytes'],
        'used_for_ranking':safe_for_cost,'facts':[{'source_file':str(catalog.path(project).relative_to(configuration.ROOT).as_posix()),
            'sha256':hash_file(catalog.path(project)),'locator':'candidate:'+candidate['id']+'@'+str(candidate['revision']),
            'scope':'CATALOG_INPUT_SIZE_ONLY','verification_status':'MEASURED_NOT_EXECUTION_ESTIMATE'}],
        'positive_basis':False}
    score=[decisive,0,obstacle,int(not candidate['readiness_reasons']),-measured if safe_for_cost else 0]
    return {'candidate_id':candidate['id'],'revision':candidate['revision'],'status':candidate['status'],
            'dimensions':dimensions,'priority_vector':score,'eligible_for_attempt':candidate['eligible_for_attempt'],
            'next_task':dimensions['decisive_falsification']['next_task'] if decisive else
                dimensions['security_obstacle']['next_task'] if obstacle else
                'Review the frozen candidate, original nearest-work text and falsification gate before any attempt.',
            'scientific_acceptance':False}


def plan(project, *, dry_run=True):
    history=_load(project)
    observed=costs.read(project); candidates=catalog.list_candidates(project)['candidates']
    rankings=[_rank(project,c) for c in candidates if c['status'] not in model.TERMINAL_STATUSES]
    rankings.sort(key=lambda row:(tuple(-n for n in row['priority_vector']),row['candidate_id'],row['revision']))
    # Existing admitted branches reserve the bounded frontier first. New
    # proposals may fill vacancies using the same evidence order, but cannot
    # evict three already admitted branches merely by declaring a cheap score.
    limit=catalog._policy()['max_active_candidates']
    admitted=[row for row in rankings if row['status'] in model.ACTIVE_STATUSES]
    if len(admitted)>limit:
        raise ValueError('Existing candidate frontier exceeds configured limit; explicitly retire a branch first')
    proposed=[row for row in rankings if row['status'] not in model.ACTIVE_STATUSES]
    frontier_ids={row['candidate_id'] for row in admitted+proposed[:limit-len(admitted)]}
    deferred=[{'candidate_id':row['candidate_id'],'revision':row['revision'],'status':row['status'],
               'reason':'OUTSIDE_BOUNDED_SCHEDULING_FRONTIER',
               'required_action':'EXPLICITLY_RETIRE_AN_ADMITTED_BRANCH_OR_WAIT_FOR_A_FRONTIER_VACANCY'}
              for row in rankings if row['candidate_id'] not in frontier_ids]
    rankings=[row for row in rankings if row['candidate_id'] in frontier_ids]
    blockers=[]; active=observed['active']
    if observed['unresolved']: blockers.append('UNKNOWN_OR_PENDING_DISCOVERY_CALLS:'+json.dumps(observed['unresolved'],sort_keys=True))
    if observed['acceptance_pending']: blockers.append('ORIGINAL_WRAPPER_ACCEPTANCE_RECOVERY_REQUIRED')
    if observed['route_state_drift']: blockers.append('UNACCOUNTED_ORIGINAL_RUN: STATE.last_run differs from route.last_processed_run')
    state=observed['state']; snapshot=observed['snapshot']
    import research
    if (snapshot['stop_requested'] or state.get('decision') in research.STOP_DECISIONS
            or state.get('initialization_required') or state.get('initialization_status')=='NEEDS_INPUT'):
        blockers.append('OPERATOR_OR_PROJECT_STOP')
    if observed['route_budget']['review_reason']:
        blockers.append('EXISTING_ROUTE_REVIEW:'+observed['route_budget']['review_reason'])
    if active: status='DEFERRED_UNTIL_ATTEMPT_CLOSE'; action='PRESERVE_EXISTING_ATTEMPT_CHECKPOINT_AND_WAIT_FOR_EXPLICIT_CLOSE'
    elif observed['unresolved'] or observed['acceptance_pending'] or observed['route_state_drift']: status='RECOVERY_REQUIRED'; action='RECOVER_OR_AUDIT_ORIGINAL_OWNER_WITHOUT_REDISPATCH'
    elif 'OPERATOR_OR_PROJECT_STOP' in blockers: status='STOPPED'; action='EXPLICIT_OPERATOR_RESUME_REQUIRED'
    elif observed['route_budget']['review_reason']: status='ROUTE_REVIEW_REQUIRED'; action='USE_EXISTING_ROUTE_REVIEW_FLOW_WITHOUT_AUTOMATIC_CALL'
    elif rankings: status='ADVISORY_ONLY'; action='REVIEW_PROBLEM_BEFORE_EXPLICIT_ATTEMPT_START_AND_BIND'
    else: status='NO_CANDIDATE'; action='REGISTER_AND_REVIEW_A_FROZEN_CANDIDATE'
    # A second read detects changes to authority or evidence during projection.
    if costs.read(project)['snapshot']!=snapshot or _load(project)!=history:
        raise ValueError('STALE_PLAN: frozen inputs changed during planning')
    snapshot['selection_history_sha256']=object_hash(history)
    return {'schema_version':1,'project_id':configuration.project_id(project),'status':status,
        'snapshot':snapshot,'snapshot_sha256':object_hash(snapshot),'rankings':rankings,
        'frontier_limit':limit,'deferred_candidates':deferred,
        'next_candidate':rankings[0]['candidate_id'] if rankings else None,'required_action':action,
        'route_budget':observed['route_budget'],'attempt_budget':observed['attempt_budget'],
        'supervision_budget':observed['supervision_budget'],'active_attempt_id':active['id'] if active else None,
        'excluded_candidates':[{'candidate_id':c['id'],'revision':c['revision'],'status':c['status'],
            'disposition':copy.deepcopy(c.get('disposition')),'scope':'OPERATOR_DECLARED_DISPOSITION_NOT_AUTOMATIC_SCIENTIFIC_VERDICT',
            'catalog_source':str(catalog.path(project).relative_to(configuration.ROOT).as_posix()),
            'catalog_sha256':snapshot['catalog_sha256']} for c in candidates if c['status'] in model.TERMINAL_STATUSES],
        'blocking_reasons':blockers,'execution_allowed':False,'budget_extension_requested':False,
        'automatic_retry_allowed':False,'dry_run':True,'ranking_scope':'SCHEDULING_FACTS_ONLY_NOT_SCIENTIFIC_JUDGMENT'}


def status(project):
    data=_load(project)
    return {'schema_version':1,'project_id':configuration.project_id(project),'plan':plan(project),
        'selections':[copy.deepcopy(e['payload']) for e in data['events'] if e['type']=='SELECTED'],
        'attempt_bindings':[copy.deepcopy(e['payload']) for e in data['events'] if e['type']=='ATTEMPT_BOUND'],
        'run_mappings':[copy.deepcopy(e['payload']) for e in data['events'] if e['type']=='RUN_MAPPED'],
        'history_event_count':len(data['events']),'execution_allowed':False}


def select(project,candidate_id,*,expected_revision,reason,expected_goal_anchor_id,
           expected_route_epoch,expected_last_processed_run,expected_snapshot_sha256=None,locks_held=False):
    identifier(candidate_id); text(reason,'selection reason')
    if not isinstance(expected_snapshot_sha256,str) or len(expected_snapshot_sha256)!=64:
        raise ValueError('STALE_SELECTION: a complete plan snapshot SHA-256 is required')
    request=object_hash({'action':'SELECTED','candidate_id':candidate_id,'revision':expected_revision,
        'goal_anchor_id':expected_goal_anchor_id,'route_epoch':expected_route_epoch,
        'last_processed_run':expected_last_processed_run,'snapshot_sha256':expected_snapshot_sha256,'reason':reason})
    with _locks(project,locks_held):
        data=_load(project,request_sha256=request); current=plan(project); snapshot=current['snapshot']
        candidate=catalog.show(project,candidate_id)
        # An exact previous request may return its original receipt even though
        # that receipt itself advanced the history head; it never becomes a new
        # current selection and never reserves research or supervision budget.
        repeated=next((e['payload'] for e in data['events'] if e['type']=='SELECTED'
            and e['payload']['candidate_id']==candidate_id and e['payload']['candidate_revision']==expected_revision
            and e['payload']['snapshot_sha256']==expected_snapshot_sha256),None)
        if repeated:
            compare=lambda s:{k:v for k,v in s.items() if k!='selection_history_sha256'}
            if (compare(repeated['snapshot'])==compare(snapshot) and candidate['revision']==expected_revision
                    and snapshot['goal_anchor_id']==expected_goal_anchor_id and snapshot['route_epoch']==expected_route_epoch
                    and snapshot['last_processed_run']==expected_last_processed_run):
                return {'status':'PENDING_OPERATOR_REVIEW','selection':copy.deepcopy(repeated),'idempotent':True,'execution_allowed':False}
        if (type(expected_revision) is not int or candidate['revision']!=expected_revision
                or snapshot['goal_anchor_id']!=expected_goal_anchor_id
                or type(expected_route_epoch) is not int or snapshot['route_epoch']!=expected_route_epoch
                or snapshot['last_processed_run']!=expected_last_processed_run
                or (expected_snapshot_sha256 is not None and current['snapshot_sha256']!=expected_snapshot_sha256)):
            raise ValueError('STALE_SELECTION: regenerate the exact candidate plan before selecting')
        if current['status']!='ADVISORY_ONLY': return {**current,'selected':False}
        if candidate['status'] in model.TERMINAL_STATUSES: raise ValueError('Rejected candidate cannot be selected')
        if not any(row['candidate_id']==candidate_id for row in current['rankings']):
            raise ValueError('OUTSIDE_SCHEDULING_FRONTIER: candidate selection is bounded; explicitly retire another branch first')
        identity={'candidate_id':candidate_id,'candidate_revision':expected_revision,'snapshot_sha256':current['snapshot_sha256']}
        sid='S-'+object_hash(identity)[:32]
        existing=next((e['payload'] for e in data['events'] if e['type']=='SELECTED' and e['payload']['selection_id']==sid),None)
        if existing: return {'status':'PENDING_OPERATOR_REVIEW','selection':copy.deepcopy(existing),'idempotent':True,'execution_allowed':False}
        record={**identity,'selection_id':sid,'snapshot':copy.deepcopy(snapshot),
            'candidate_spec_sha256':candidate['spec_sha256'],'problem_binding':copy.deepcopy(candidate['problem_binding']),
            'ranking':next(row for row in current['rankings'] if row['candidate_id']==candidate_id),
            'required_action':'REVIEW_PROBLEM_BEFORE_EXPLICIT_ATTEMPT_START_AND_BIND',
            'scientific_acceptance':False,'created_at':route_budget.stamp()}
        if plan(project)['snapshot_sha256']!=current['snapshot_sha256']: raise ValueError('STALE_SELECTION: inputs changed before append')
        _append(project,data,'SELECTED',record,reason,request)
        return {'status':'PENDING_OPERATOR_REVIEW','selection':record,'idempotent':False,'execution_allowed':False}


def _selected(data,sid):
    records=[e['payload'] for e in data['events'] if e['type']=='SELECTED']
    item=next((e for e in records if e['selection_id']==sid),None)
    if item is None: raise ValueError('Unknown candidate selection')
    return item, records[-1]


def bind_attempt(project,selection_id,attempt_id,*,reason,locks_held=False):
    text(reason,'binding reason'); identifier(attempt_id)
    request=object_hash({'action':'ATTEMPT_BOUND','selection_id':selection_id,'attempt_id':attempt_id,'reason':reason})
    with _locks(project,locks_held):
        data=_load(project,request_sha256=request); selected,latest=_selected(data,selection_id)
        for event in data['events']:
            if event['type']=='ATTEMPT_BOUND' and event['payload']['attempt_id']==attempt_id:
                if event['payload']['selection_id']!=selection_id: raise ValueError('Attempt already belongs to another selection')
                return {'status':'ATTEMPT_OWNER_BOUND','binding':copy.deepcopy(event['payload']),'idempotent':True,'execution_allowed':False}
        observed=costs.read(project); attempt=observed['active']
        if attempt is None or attempt['id']!=attempt_id: raise ValueError('Bind the exact existing active attempt owner')
        if attempt['calls']: raise ValueError('Pre-dispatch binding requires zero original calls; retroactive binding is forbidden')
        if observed['attempt_budget']['preflight']!='READY' or attempt['status']!='ACTIVE':
            raise ValueError('Original attempt preflight is not READY: '+observed['attempt_budget']['preflight'])
        if selected!=latest: raise ValueError('Selection is no longer current')
        candidate=catalog.show(project,selected['candidate_id']); snapshot=selected['snapshot']; now=observed['snapshot']
        if (candidate['revision']!=selected['candidate_revision'] or candidate['spec_sha256']!=selected['candidate_spec_sha256']
                or any(snapshot[k]!=now[k] for k in ('goal_anchor_id','route_epoch','last_processed_run','catalog_sha256'))):
            raise ValueError('STALE_SELECTION: candidate or frozen route changed before owner binding')
        binding=selected['problem_binding']
        if (binding['status']!='FIXED' or attempt['problem_id']!=binding['id']
                or attempt['problem_version']!=binding['version'] or attempt['problem_sha256']!=binding['spec_sha256']):
            raise ValueError('Candidate and original attempt must pin the same exact fixed problem')
        import research
        if (observed['unresolved'] or observed['acceptance_pending'] or observed['route_state_drift'] or observed['route_budget']['review_reason']
                or now['stop_requested'] or observed['state'].get('decision') in research.STOP_DECISIONS
                or observed['state'].get('initialization_required') or observed['state'].get('initialization_status')=='NEEDS_INPUT'):
            raise ValueError('Original recovery/stop/route review blocks pre-dispatch ownership binding')
        if not candidate['eligible_for_attempt']:
            raise ValueError('Candidate READY_FOR_ATTEMPT and fresh independent gates are required before binding')
        record={'selection_id':selection_id,'candidate_id':selected['candidate_id'],'candidate_revision':selected['candidate_revision'],
            'attempt_id':attempt_id,'problem_id':binding['id'],'problem_version':binding['version'],
            'problem_sha256':binding['spec_sha256'],'calls_at_binding':[],
            'attempt_before_calls_sha256':object_hash(attempt),'bound_at':route_budget.stamp(),
            'attribution_scope':'OPERATOR_ASSIGNED_SCHEDULING_PROVENANCE','candidate_injection_proven':False}
        if costs.read(project)['snapshot']!=observed['snapshot'] or not catalog.show(project,selected['candidate_id'])['eligible_for_attempt']:
            raise ValueError('STALE_SELECTION: original owner or candidate evidence changed before binding')
        _append(project,data,'ATTEMPT_BOUND',record,reason,request)
        return {'status':'ATTEMPT_OWNER_BOUND','binding':record,'idempotent':False,'execution_allowed':False}


def record_run_mapping(project,selection_id,run_id,*,reason,expected_attempt_id=None,locks_held=False):
    text(reason,'run mapping reason'); identifier(run_id)
    request=object_hash({'action':'RUN_MAPPED','selection_id':selection_id,'attempt_id':expected_attempt_id,'run_id':run_id,'reason':reason})
    with _locks(project,locks_held):
        data=_load(project,request_sha256=request); selected,_=_selected(data,selection_id)
        owners=[e['payload'] for e in data['events'] if e['type']=='ATTEMPT_BOUND'
                and e['payload']['selection_id']==selection_id and e['payload']['attempt_id']==expected_attempt_id]
        if len(owners)!=1: raise ValueError('A unique pre-dispatch candidate owner binding is required')
        owner=owners[0]
        # A committed mapping is historical scheduling provenance. Its original
        # owner/acceptance were checked before append; replay the protected
        # selection history without requiring bounded current display events.
        for event in data['events']:
            if event['type']=='RUN_MAPPED' and event['payload']['run_id']==run_id:
                mapped=event['payload']
                if (mapped['selection_id']!=selection_id or mapped['attempt_id']!=owner['attempt_id']
                        or mapped['candidate_id']!=owner['candidate_id']
                        or mapped['candidate_revision']!=owner['candidate_revision']):
                    raise ValueError('Original run already maps to another candidate or attempt')
                return {'status':'RUN_MAPPING_RECORDED','mapping':copy.deepcopy(mapped),'idempotent':True,'execution_allowed':False}
        trusted=costs.trusted_run(project,run_id,owner['attempt_id']); attempt=trusted['attempt']
        if (attempt['problem_id']!=owner['problem_id'] or attempt['problem_version']!=owner['problem_version']
                or attempt['problem_sha256']!=owner['problem_sha256']):
            raise ValueError('Original run owner fixed problem changed after binding')
        if trusted['route_event'] and trusted['route_event'].get('anchor_id')!=selected['snapshot']['goal_anchor_id']:
            raise ValueError('Original accepted route event belongs to a different frozen candidate anchor')
        if trusted['route_event'] and not any(
                e['epoch']==selected['snapshot']['route_epoch'] and run_id in e['counted_run_ids']
                and e['route']==trusted['route_event'].get('route')
                and e.get('focus',{}).get('anchor_id')==selected['snapshot']['goal_anchor_id']
                for e in trusted['acceptance_route_epochs']):
            raise ValueError('Original accepted run belongs to a different frozen route epoch')
        if run_id in selected['snapshot']['known_discovery_run_ids'] or run_id in selected['snapshot']['route_counted_run_ids']:
            raise ValueError('Retroactive attribution of an existing run is forbidden')
        record={'selection_id':selection_id,'candidate_id':owner['candidate_id'],'candidate_revision':owner['candidate_revision'],
            'attempt_id':owner['attempt_id'],'run_id':run_id,'call_status':trusted['call']['status'],
            'settlement_sha256':trusted['settlement_sha256'],'discovery_ledger_sha256':trusted['ledger_sha256'],
            'route_event_sha256':object_hash(trusted['route_event']) if trusted['route_event'] else None,
            'accounting_source':'ORIGINAL_ROUTE_AND_DISCOVERY_LEDGERS_ONLY','new_budget_charge':False,
            'attribution_scope':'OPERATOR_ASSIGNED_SCHEDULING_PROVENANCE','candidate_injection_proven':False,
            'scientific_acceptance':False,'mapped_at':route_budget.stamp()}
        _append(project,data,'RUN_MAPPED',record,reason,request)
        return {'status':'RUN_MAPPING_RECORDED','mapping':record,'idempotent':False,'execution_allowed':False}
