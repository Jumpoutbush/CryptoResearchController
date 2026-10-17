"""Scoped branch resolution and explicit, recoverable old-engine close/start phases."""
from __future__ import annotations
import contextlib
import copy
from pathlib import Path
import re
import configuration
from engine import claim_graph, discovery_scheduler as discovery
from engine.common import fresh, identifier, object_hash, text
from research_quality import hash_file, validate_technical_review
from route_budget import file_lock, stamp
from . import catalog, cost_accounting as costs, history, model, security_model
from .verifiers import interface as verification

STATUSES={'REFUTED','COVERED','RETIRED','CONDITIONAL'}


def _card(value):
    fields={'schema_version','requested_status','scope','restart_conditions','reason','verification_request_id',
            'semantic_review_file','source_dependencies','reusable_lemmas'}
    if (not isinstance(value,dict) or set(value)!=fields or type(value['schema_version']) is not int
            or value['schema_version']!=1 or value['requested_status'] not in STATUSES): raise ValueError('Invalid scoped branch resolution card')
    for key in ('scope','restart_conditions','reason'): text(value[key],key)
    for key in ('verification_request_id','semantic_review_file'):
        if value[key] is not None: text(value[key],key)
    if not isinstance(value['source_dependencies'],list) or len(value['source_dependencies'])>100: raise ValueError('Invalid source dependencies')
    source_card=security_model.template(); source_card['dependencies']=copy.deepcopy(value['source_dependencies'])
    security_model.validate_card(source_card)
    if not isinstance(value['reusable_lemmas'],list) or len(value['reusable_lemmas'])>100: raise ValueError('Invalid reusable lemma list')
    for lemma in value['reusable_lemmas']:
        if (not isinstance(lemma,dict) or set(lemma)!={'id','revision','spec_sha256','scope','consumer_claim','dependency_argument'}
                or lemma['scope'] not in {'DIRECT_DEPENDENCY','SUPPORT'}): raise ValueError('Reusable lemmas require exact pins and DIRECT_DEPENDENCY/SUPPORT scope')
        identifier(lemma['id']); validate_revision(lemma['revision']); text(lemma['dependency_argument'],'lemma reuse argument')
        if lemma['scope']=='DIRECT_DEPENDENCY': text(lemma['consumer_claim'],'consumer_claim')
    return copy.deepcopy(value)


def validate_revision(value):
    if type(value) is not int or value<1: raise ValueError('Expected candidate/claim revision must be positive')


def semantic_review_template(project,candidate_id,claim_id,requested_status,*,scope,verification_request_id=None):
    base=verification.prepare_request(project,candidate_id,claim_id,adapter_id='branch-resolution-v1')
    return {'schema_version':1,'kind':'INDEPENDENT_BRANCH_SCOPE_REVIEW','reviewer':None,'decision':'CONFIRMED',
        'requested_status':requested_status,'claim_binding':base['claim_binding'],'scope_type':'EXACT_CANDIDATE_REVISION',
        'scope':scope,'verification_request_id':verification_request_id,'affected_obligations':
            copy.deepcopy(claim_graph.get(project,claim_id)['spec']['obligation_ids']),
        'assumptions':copy.deepcopy(catalog.show(project,candidate_id)['spec']['assumptions']),
        'necessity_argument':None,'premises_preserved':True}


def _independent_review(project,base,card):
    if base is None or not card['semantic_review_file']: return None,'Original independent statement review of the exact scope mapping is required'
    relative=card['semantic_review_file']; path=security_model.validate.safe(project,relative,roots={'research','proofs'})
    record=configuration.load_json(path); item=claim_graph.get(project,base['claim_binding']['claim_id'])
    receipt=item['reviews'].get('statement',{})
    latches=claim_graph._revocation_latches(item,claim_graph.load(project).get('events',[]))
    expected={'schema_version','kind','reviewer','decision','requested_status','claim_binding','scope_type','scope',
              'verification_request_id','affected_obligations','assumptions','necessity_argument','premises_preserved'}
    if (not isinstance(record,dict) or set(record)!=expected or type(record['schema_version']) is not int or record['schema_version']!=1
            or record['kind']!='INDEPENDENT_BRANCH_SCOPE_REVIEW' or record['decision']!='CONFIRMED'
            or record['requested_status']!=card['requested_status'] or record['claim_binding']!=base['claim_binding']
            or record['scope_type']!='EXACT_CANDIDATE_REVISION' or record['scope']!=card['scope']
            or record['verification_request_id']!=card['verification_request_id']
            or record['assumptions']!=catalog.show(project,base['claim_binding']['candidate_id'])['spec']['assumptions']
            or record['premises_preserved'] is not True or not isinstance(record['necessity_argument'],str)
            or len(record['necessity_argument'].strip())<32
            or not isinstance(record['affected_obligations'],list) or not record['affected_obligations']
            or not set(record['affected_obligations'])<=set(item['spec']['obligation_ids'])
            or latches is None or 'review:statement' in latches
            or not receipt or receipt.get('claim_sha256')!=item['spec_sha256']
            or record['reviewer']!=receipt.get('reviewer') or not isinstance(record['reviewer'],str)
            or record['reviewer'].strip().casefold()==item['spec']['proposer'].strip().casefold()
            or receipt.get('evidence',{}).get(relative)!=hash_file(path) or not fresh(project,receipt['evidence'])
            or not claim_graph.receipt_history_valid(item,claim_graph.load(project).get('events'))):
        return None,'Scope JSON must match exact candidate/claim/problem and an existing fresh independently attested statement-review receipt'
    return {'file':relative,'sha256':hash_file(path),'reviewer':record['reviewer'],
        'original_statement_receipt_sha256':object_hash(receipt),'evidence':copy.deepcopy(receipt['evidence']),
        'scope':'OPERATOR_ATTESTED_EXACT_CANDIDATE_SCOPE_NOT_EXTERNAL_IDENTITY_CERTIFICATION'},None


def prepare_request(project,candidate_id,claim_id,card,*,_recovery_operation_id=None):
    execution_preflight(project,allowed_operation_id=_recovery_operation_id)
    card=_card(card); candidate=catalog.show(project,candidate_id); observed=costs.read(project)
    if claim_id is None and card['requested_status']!='RETIRED': raise ValueError('A scientific branch resolution requires an exact existing claim')
    base=verification.prepare_request(project,candidate_id,claim_id,adapter_id='branch-resolution-v1') if claim_id is not None else None
    pins=copy.deepcopy(base['source_hashes'] if base else observed['snapshot']['goal_binding']['files'])
    pins.update(candidate['evidence_bindings']); controller={}; gaps=[]; outcome=card['requested_status']
    independent,error=_independent_review(project,base,card)
    if card['semantic_review_file']:
        path=security_model.validate.safe(project,card['semantic_review_file'],roots={'research','proofs'})
        pins[card['semantic_review_file']]=hash_file(path)
    if independent: pins.update(independent['evidence'])
    source_checks=[]
    if card['requested_status'] in {'REFUTED','COVERED'} and error: gaps.append(error)
    if card['requested_status']=='REFUTED':
        rid=card['verification_request_id']
        if rid:
            try:
                certificate=verification.recheck(project,rid)
                if (certificate.get('result_status')!='COUNTEREXAMPLE_FOUND' or not certificate.get('fresh')
                        or not certificate.get('certificate_valid') or base is None
                        or certificate['claim_binding']!=base['claim_binding']):
                    gaps.append('Fresh exact machine certificate must match this candidate, claim and fixed problem')
                for path in verification._paths(project,rid).values():
                    if path.is_file(): controller[path.relative_to(configuration.ROOT).as_posix()]=hash_file(path)
            except (ValueError,OSError,KeyError) as exc: gaps.append('Exact counterexample certificate unavailable: '+str(exc))
        else: gaps.append('Exact recheckable R13 counterexample certificate is required')
    if card['requested_status']=='COVERED':
        if not card['source_dependencies']: gaps.append('Original theorem-level source and coverage mapping are required')
        else:
            source_checks,source_pins=security_model._source_checks(project,{'dependencies':card['source_dependencies']})
            pins.update(source_pins)
            for dependency,check in zip(card['source_dependencies'],source_checks):
                if check['status']!='SOURCE_LOCATION_ONLY' or check.get('coverage_verdict')!='COVERS':
                    gaps.append('Coverage requires original FULLTEXT_LOCATED theorem and a decisive technically checked mapping')
                    continue
                try: validate_technical_review(project,check['technical_review_path'],claim_id,decisive=True)
                except (ValueError,OSError) as exc: gaps.append('Coverage mapping is incomplete: '+str(exc))
                required=set(dependency['required_assumptions'])|set(check.get('source_assumptions',[]))
                if not required<=set(dependency['used_assumptions']): gaps.append('Original theorem premises are not all preserved')
    if card['requested_status'] in {'REFUTED','COVERED'} and gaps: outcome='CONDITIONAL'
    lemmas=[]
    statuses={item['id']:item for item in claim_graph.status(project)['claims']} if card['reusable_lemmas'] else {}
    for pin in card['reusable_lemmas']:
        item=claim_graph.get(project,pin['id'])
        if {'revision':item['revision'],'spec_sha256':item['spec_sha256']}!={k:pin[k] for k in ('revision','spec_sha256')}:
            raise ValueError('Reusable lemma pins must match exact existing revisions')
        if pin['scope']=='DIRECT_DEPENDENCY':
            consumer=claim_graph.get(project,pin['consumer_claim'])
            expected={'revision':item['revision'],'spec_sha256':item['spec_sha256']}
            if (pin['id'] not in consumer['spec']['dependencies']
                    or consumer.get('dependency_pins',{}).get(pin['id'])!=expected):
                raise ValueError('DIRECT_DEPENDENCY requires an existing consumer with the exact original declared dependency pin')
        lemmas.append({**pin,'proof_status':statuses[pin['id']]['proof_status'],'positive_basis':False})
        pins.update(item['evidence'])
    authority={'research/discovery/CLAIM_GRAPH.json':hash_file(project/'research/discovery/CLAIM_GRAPH.json')} if base is not None or lemmas else {}
    value={'schema_version':1,'project_id':configuration.project_id(project),'candidate_id':candidate_id,
        'candidate_revision':candidate['revision'],'candidate_spec_sha256':candidate['spec_sha256'],
        'candidate_semantic_sha256':candidate['semantic_sha256'],'goal_sha256':candidate['goal_sha256'],
        'goal_anchor_id':candidate['goal_anchor_id'],'problem_binding':copy.deepcopy(candidate['problem_binding']),
        'base_request':base,'card':card,'decision':outcome,'gaps':gaps,'independent_review':independent,
        'source_checks':source_checks,'evidence_bindings':pins,'controller_bindings':controller,'authority_bindings':authority,'reusable_lemmas':lemmas,
        'route_effective_rounds':observed['route_budget']['effective_rounds'],'route_epoch':observed['snapshot']['route_epoch'],
        'route_sha256':observed['snapshot']['route_sha256'],'route_registry_sha256':observed['snapshot']['route_registry_sha256'],
        'catalog_before_sha256':hash_file(catalog.path(project)),'assumptions':copy.deepcopy(candidate['spec']['assumptions']),
        'open_obligations':copy.deepcopy(candidate['problem_binding']['spec']['obligations'])}
    digest=object_hash(value); value['request_sha256']=digest; value['request_id']='BR-'+digest
    return value


def _paths(project,rid,kind='resolutions'):
    if not isinstance(rid,str) or not re.fullmatch(r'(BR|SW)-[0-9a-f]{64}',rid): raise ValueError('Invalid frozen branch operation ID')
    base=catalog._unlinked(catalog.path(project).parent/kind)
    return {'intent':catalog._unlinked(base/(rid+'.json')),
            'witness':catalog._unlinked(catalog.path(project).parent/'operation_witnesses'/(rid+'.json'))}


def _valid_request(request,prefix):
    if (not isinstance(request,dict) or type(request.get('schema_version')) is not int or request.get('schema_version')!=1
            or request.get('request_sha256')!=object_hash({k:v for k,v in request.items() if k not in {'request_id','request_sha256'}})
            or request.get('request_id')!=prefix+'-'+request['request_sha256']): raise ValueError('Branch request digest mismatch')


@contextlib.contextmanager
def _locks(project,locks_held):
    _,key=catalog._project(project)
    with contextlib.ExitStack() as stack:
        if not locks_held:
            for name in ('route-'+key+'.lock',key+'.lock'):
                stack.enter_context(file_lock(catalog._unlinked(configuration.ROOT/'locks'/name)))
        stack.enter_context(file_lock(catalog._unlinked(configuration.ROOT/'locks'/('candidate-resolution-'+key+'.lock'))))
        yield


def _write_intent(path,value):
    value['sha256']=object_hash({k:v for k,v in value.items() if k!='sha256'})
    configuration.atomic_json(path,value)


def _read_intent(path):
    value=configuration.load_json(path)
    if value is not None and (not isinstance(value,dict) or value.get('sha256')!=object_hash({k:v for k,v in value.items() if k!='sha256'})):
        raise ValueError('Branch operation journal changed; preserve and audit')
    return value


def _witness_value(request,kind):
    return {'schema_version':1,'operation_id':request['request_id'],'kind':kind,
            'request_sha256':request['request_sha256'],'intent_file':kind+'/'+request['request_id']+'.json'}


def _write_witness(project,request,kind):
    """A second immutable local witness precedes all original-engine effects."""
    location=_paths(project,request['request_id'],kind)['witness']; expected=_witness_value(request,kind)
    existing=configuration.load_json(location)
    if existing is not None and existing!=expected: raise ValueError('Branch operation witness conflicts with its frozen request')
    if existing is None: configuration.atomic_json(location,expected)


def _require_witness(project,request,kind):
    actual=configuration.load_json(_paths(project,request['request_id'],kind)['witness'])
    if actual!=_witness_value(request,kind) or type(actual.get('schema_version')) is not int:
        raise ValueError('CANDIDATE_SWITCH_RECOVERY_REQUIRED: frozen operation witness missing or changed; do not reconstruct inputs')


def _resolution_fresh(project,request,*,recovery=False):
    _valid_request(request,'BR'); current=catalog.show(project,request['candidate_id'])
    if (current['revision']!=request['candidate_revision'] or current['spec_sha256']!=request['candidate_spec_sha256']
            or current['goal_anchor_id']!=request['goal_anchor_id'] or not fresh(project,request['evidence_bindings'])):
        raise ValueError('Resolution candidate or exact scientific evidence changed')
    for relative,digest in request['controller_bindings'].items():
        file=catalog._unlinked(configuration.ROOT/relative)
        if not file.is_file() or hash_file(file)!=digest: raise ValueError('Resolution verification certificate changed')
    if request['base_request'] is not None:
        base=verification.prepare_request(project,request['candidate_id'],request['base_request']['claim_binding']['claim_id'],adapter_id='branch-resolution-v1')
        if base!=request['base_request']: raise ValueError('Resolution exact claim/problem/goal binding changed')
        actual,error=_independent_review(project,base,request['card'])
        if actual!=request['independent_review']: raise ValueError('Resolution independent scope review changed: '+str(error))
    # A self-computed digest is integrity, not authority. Re-derive every
    # scientific decision and gap from the original adapters/independent gate.
    claim_id=request['base_request']['claim_binding']['claim_id'] if request['base_request'] else None
    recalculated=prepare_request(project,request['candidate_id'],claim_id,request['card'],
                                _recovery_operation_id=request['request_id'] if recovery else None)
    ignored={'request_id','request_sha256'}
    if recovery: ignored|={'catalog_before_sha256'}
    if {k:v for k,v in recalculated.items() if k not in ignored}!={k:v for k,v in request.items() if k not in ignored}:
        raise ValueError('Resolution scientific decision or frozen derived evidence was forged or changed')
    return current


def _catalog_resolution(project,request,intent):
    current=catalog._load(project); before=intent['catalog_before']; record=next(c for c in current['candidates'] if c['id']==request['candidate_id'])['revisions'][-1]
    old=next(c for c in before['candidates'] if c['id']==request['candidate_id'])['revisions'][-1]
    target=request['decision']; reason='R15 '+request['request_id']+': '+request['card']['reason']
    evidence_refs=sorted(set(old['spec']['evidence_refs']+([request['card']['semantic_review_file']] if request['card']['semantic_review_file'] else [])))
    disposition={'scope':request['card']['scope'],'restart_conditions':request['card']['restart_conditions'],
                 'evidence_refs':evidence_refs} if target in {'REFUTED','COVERED'} else None
    if old['status'] in model.TERMINAL_STATUSES or old['status']==target:
        if current!=before: raise ValueError('Resolution legacy terminal catalog version changed')
        return 'PRESERVED_EXISTING_OPERATOR_LABEL'
    if current==before:
        catalog.transition(project,request['candidate_id'],target,reason,expected_revision=request['candidate_revision'],disposition=disposition)
        current=catalog._load(project); record=next(c for c in current['candidates'] if c['id']==request['candidate_id'])['revisions'][-1]
    if len(current['events'])!=len(before['events'])+1 or current['events'][:-1]!=before['events']:
        raise ValueError('Resolution catalog has a third-party version; do not overwrite it')
    event=current['events'][-1]
    if (event['type']!='STATUS_CHANGED' or event['reason']!=reason or event['record']['id']!=request['candidate_id']
            or event['record']['revision']!=request['candidate_revision'] or event['record']['status']!=target):
        raise ValueError('Resolution catalog change is not the original owned local operation')
    expected=copy.deepcopy(old); expected['status']=target
    if disposition is not None:
        expected['disposition']={**disposition,'evidence_bindings':security_model.validate.refs(project,evidence_refs)}
    if record!=expected: raise ValueError('Resolution catalog scope/disposition or immutable fields differ from the owned afterimage')
    return 'UPDATED_BY_EXISTING_CATALOG_TRANSITION'


def resolve(project,request,*,locks_held=False):
    with _locks(project,locks_held):
        try:
            _valid_request(request,'BR'); path=_paths(project,request['request_id'])['intent']; intent=_read_intent(path)
            if intent is not None and intent['request']!=request: raise ValueError('Resolution intent conflicts with the original frozen request')
            if intent is not None: _require_witness(project,request,'resolutions')
            if intent is not None and intent['phase']=='APPLIED':
                # A frozen completed audit receipt may be read after later
                # budget/catalog work; it does not apply the decision again.
                return copy.deepcopy(intent['record'])
            history.load(project,operation_id=request['request_id'])
            _resolution_fresh(project,request,recovery=intent is not None)
        except (ValueError,OSError,KeyError,TypeError) as exc:
            return {'status':'FAILED','reason':str(exc),'scientific_acceptance':False}
        if intent is not None:
            if intent['request']!=request: raise ValueError('Resolution intent conflicts with the original frozen request')
            if intent['phase']=='APPLIED': return copy.deepcopy(intent['record'])
        else:
            observed=costs.read(project)
            if (observed['snapshot']['route_sha256']!=request['route_sha256']
                    or observed['snapshot']['route_registry_sha256']!=request['route_registry_sha256']
                    or hash_file(catalog.path(project))!=request['catalog_before_sha256']):
                return {'status':'FAILED','reason':'Stale resolution route/catalog CAS','scientific_acceptance':False}
            intent={'schema_version':1,'phase':'PREPARED','request':request,'catalog_before':catalog._load(project),'created_at':stamp()}
            _write_intent(path,intent)
            _write_witness(project,request,'resolutions')
        _resolution_fresh(project,request,recovery=True)
        catalog_action=_catalog_resolution(project,request,intent)
        binding=request['problem_binding']; base=request['base_request']
        record={'id':request['request_id'],'resolution_id':request['request_id'],'project_id':request['project_id'],
            'candidate_id':request['candidate_id'],'candidate_revision':request['candidate_revision'],
            'candidate_spec_sha256':request['candidate_spec_sha256'],'candidate_semantic_sha256':request['candidate_semantic_sha256'],
            'goal_sha256':request['goal_sha256'],'goal_anchor_id':request['goal_anchor_id'],
            'problem_id':binding['id'],'problem_version':binding['version'],'problem_sha256':binding['spec_sha256'],
            'claim_binding':copy.deepcopy(base['claim_binding']) if base else None,
            'status':request['decision'],'requested_status':request['card']['requested_status'],
            'scope':request['card']['scope'],'scope_type':'EXACT_CANDIDATE_REVISION','assumptions':request['assumptions'],
            'parent_or_family_refuted':False,'scientific_acceptance':False,'reason':request['card']['reason'],
            'gaps':request['gaps'],'evidence_bindings':request['evidence_bindings'],'controller_bindings':request['controller_bindings'],
            'authority_bindings':request['authority_bindings'],
            'route_effective_rounds':request['route_effective_rounds'],'route_epoch':request['route_epoch'],
            'open_obligations':request['open_obligations'],'reusable_lemmas':request['reusable_lemmas'],
            'restart_conditions':request['card']['restart_conditions'],'independent_review':request['independent_review'],
            'source_checks':request['source_checks'],'catalog_action':catalog_action,'recorded_at':intent['created_at']}
        history.append(project,'RESOLUTION_RECORDED',record,record['resolution_id'],request['card']['reason'])
        intent.update(phase='APPLIED',record=record); _write_intent(path,intent)
        return copy.deepcopy(record)


def retire(project,candidate_id,*,expected_revision,reason,scope,restart_conditions,locks_held=False):
    if catalog.show(project,candidate_id)['revision']!=expected_revision: raise ValueError('Expected candidate revision conflict')
    card={'schema_version':1,'requested_status':'RETIRED','scope':scope,'restart_conditions':restart_conditions,
          'reason':reason,'verification_request_id':None,'semantic_review_file':None,'source_dependencies':[],'reusable_lemmas':[]}
    return resolve(project,prepare_request(project,candidate_id,None,card),locks_held=locks_held)


def compare(project,candidate_ids):
    return {'candidates':[catalog.show(project,cid) for cid in candidate_ids],
            'resolutions':[r for r in history.projection_records(project) if r['candidate_id'] in candidate_ids],
            'scientific_acceptance':False}


def _switch_guard(project):
    observed=costs.read(project); import research
    if observed['unresolved'] or observed['acceptance_pending'] or observed['route_state_drift']:
        raise ValueError('RECOVERY_REQUIRED: original pending/UNKNOWN call or wrapper acceptance must be resolved before switching')
    if (observed['snapshot']['stop_requested'] or observed['state'].get('decision') in research.STOP_DECISIONS
            or observed['state'].get('initialization_required') or observed['state'].get('initialization_status')=='NEEDS_INPUT'
            or observed['route_budget']['review_reason']): raise ValueError('Original STOP/initialization/route review prevents switching')
    return observed


def execution_preflight(project,*,allowed_operation_id=None):
    """Read-only fence shared with every old model-dispatch preflight.

    The private allowed ID is used solely to finish an already frozen local
    metadata operation; no existing research API exposes such an escape.
    """
    base=catalog.path(project).parent
    witness_dir=catalog._unlinked(base/'operation_witnesses')
    if witness_dir.exists():
        for location in witness_dir.glob('*.json'):
            value=configuration.load_json(catalog._unlinked(location))
            if (not isinstance(value,dict) or value.get('kind') not in {'switches','resolutions'}
                    or not isinstance(value.get('operation_id'),str) or location.name!=value['operation_id']+'.json'):
                raise ValueError('CANDIDATE_SWITCH_RECOVERY_REQUIRED: malformed frozen operation witness')
            pair=_paths(project,value['operation_id'],value['kind'])['intent']
            if not pair.is_file(): raise ValueError('CANDIDATE_SWITCH_RECOVERY_REQUIRED: frozen operation input missing; no retry')
    for kind in ('switches','resolutions'):
        directory=catalog._unlinked(base/kind)
        if not directory.exists(): continue
        for location in directory.glob('*.json'):
            catalog._unlinked(location); intent=_read_intent(location)
            try:
                request=intent['request']; prefix='SW' if kind=='switches' else 'BR'
                _valid_request(request,prefix)
                _require_witness(project,request,kind)
                if (intent.get('schema_version')!=1 or type(intent.get('schema_version')) is not int
                        or intent.get('phase') not in {'PREPARED','APPLIED'}
                        or location.name!=request['request_id']+'.json'):
                    raise ValueError('Malformed or mismatched branch operation fence')
                if intent['phase']=='PREPARED' and request['request_id']!=allowed_operation_id:
                    raise ValueError('CANDIDATE_SWITCH_RECOVERY_REQUIRED: '+request['request_id'])
                if intent['phase']=='APPLIED':
                    record=intent['record']
                    actual=record.get('request_id') if kind=='switches' else record.get('resolution_id')
                    if actual!=request['request_id'] or record.get('scientific_acceptance') is not False:
                        raise ValueError('Completed branch fence has no exact local receipt')
            except (KeyError,TypeError,AttributeError) as exc:
                raise ValueError('CANDIDATE_SWITCH_RECOVERY_REQUIRED: corrupt original branch operation') from exc


def _readiness_snapshot(project,candidate):
    pins=candidate['spec']['dependency_claims']; rows=[]; evidence={}
    if pins:
        graph=claim_graph.load(project); states={row['id']:row for row in claim_graph.status(project)['claims']}
        for pin in pins:
            item=claim_graph.get(project,pin['id']); rows.append(copy.deepcopy(states[pin['id']]))
            paths=set(item['evidence'])
            for receipt in item.get('reviews',{}).values(): paths.update(receipt.get('evidence',{}))
            for relative in paths:
                path=security_model.validate.safe(project,relative)
                evidence[relative]=hash_file(path)
        graph_sha=hash_file(security_model.validate.safe(project,'research/discovery/CLAIM_GRAPH.json'))
    else: graph_sha=None
    return {'eligible_for_attempt':candidate['eligible_for_attempt'],'readiness_reasons':copy.deepcopy(candidate['readiness_reasons']),
            'canonical_graph_sha256':graph_sha,'dependencies':rows,'evidence_bindings':evidence}


def _close_attribution(project,candidate,attempt_id,*,explicit):
    from . import scheduler
    events=scheduler._load(project)['events']
    owners=[e['payload'] for e in events if e['type']=='ATTEMPT_BOUND' and e['payload']['attempt_id']==attempt_id]
    if owners:
        if len(owners)!=1: raise ValueError('Ambiguous original candidate owner binding')
        owner=owners[0]
        selected=next(e['payload'] for e in events if e['type']=='SELECTED' and e['payload']['selection_id']==owner['selection_id'])
        if (owner['candidate_id']!=candidate['id'] or owner['candidate_revision']!=candidate['revision']
                or selected['candidate_spec_sha256']!=candidate['spec_sha256']):
            raise ValueError('CLOSE candidate must match the original R12 bound owner; use original attempt close to audit an old revised owner')
        return {'kind':'R12_PRE_DISPATCH_BINDING','binding':copy.deepcopy(owner),
                'candidate_spec_sha256':selected['candidate_spec_sha256'],'candidate_injection_proven':False}
    starts=[e['payload'] for e in history.load(project)['events'] if e['type']=='SWITCH_APPLIED'
            and e['payload']['phase']=='START' and e['payload']['attempt_id']==attempt_id]
    if starts:
        previous=starts[-1]
        if (previous['candidate_id']!=candidate['id'] or previous['candidate_revision']!=candidate['revision']
                or previous.get('candidate_spec_sha256')!=candidate['spec_sha256']):
            raise ValueError('CLOSE candidate must match the original explicit START owner')
        return {'kind':'R15_EXPLICIT_START_BINDING','request_id':previous['request_id'],'candidate_injection_proven':False}
    if not explicit: raise ValueError('Legacy unbound attempt requires explicit from_attempt_id for operator assignment')
    return {'kind':'EXPLICIT_OPERATOR_ASSIGNMENT_OF_LEGACY_UNBOUND_ATTEMPT','attempt_id':attempt_id,'candidate_injection_proven':False}


def _close_owner_preflight(project,owner):
    """Keep old stale/pause checks while allowing budget-exhausted closure.

    During recovery the original check first sees our own pending fence, so
    inspect the exact frozen original owner, never an invented new attempt.
    """
    if owner['status'] not in {'ACTIVE','BUDGET_EXHAUSTED'}:
        raise ValueError('ATTEMPT_PAUSED: do not bypass the original checkpoint review')
    if owner['binding']!=discovery.goal_binding(project): raise ValueError('ATTEMPT_STALE: original owner binding changed')
    fixed=discovery.get_problem(project,owner['problem_id'],owner['problem_version'])
    if fixed['spec_sha256']!=owner['problem_sha256'] or not fresh(project,fixed['source_bindings']):
        raise ValueError('ATTEMPT_STALE: pinned original problem changed')
    if owner['checkpoint'] and not fresh(project,owner['checkpoint'].get('evidence',{})):
        raise ValueError('ATTEMPT_STALE: accepted checkpoint evidence changed; review before closing')


def prepare_switch(project,candidate_id,*,phase,reason,expected_revision,from_attempt_id=None):
    execution_preflight(project)
    text(reason,'switch reason'); current=catalog.show(project,candidate_id); observed=_switch_guard(project)
    if current['revision']!=expected_revision: raise ValueError('Expected candidate revision conflict')
    restart=None; attribution=None
    if phase=='CLOSE':
        owner=observed['active']
        if owner is None or (from_attempt_id is not None and owner['id']!=from_attempt_id): raise ValueError('Explicit original active owner is required')
        _close_owner_preflight(project,owner)
        problem=current['problem_binding']
        if (owner['problem_id']!=problem['id'] or owner['problem_version']!=problem['version'] or owner['problem_sha256']!=problem['spec_sha256']):
            raise ValueError('Close must name the exact existing fixed problem owner')
        attribution=_close_attribution(project,current,owner['id'],explicit=from_attempt_id is not None)
        engine_plan=discovery.prepare_close(project,reason,capture_state=True)
    elif phase=='START':
        if observed['active'] is not None: raise ValueError('Close the original attempt explicitly before preparing START')
        if not current['eligible_for_attempt']: raise ValueError('New candidate must pass the existing READY and fresh independent dependency gates')
        old=[r for r in history.projection_records(project) if r['candidate_id']==candidate_id and r['status'] in {'REFUTED','COVERED'}]
        if old:
            latest=old[-1]
            if (current['revision']<=latest['candidate_revision'] or current['semantic_sha256']==latest['candidate_semantic_sha256']):
                raise ValueError('Restart requires a genuinely changed hypothesis and new independent scope review')
            restart=_restart_review(project,current)
            if not restart: raise ValueError('Restart requires a new independently attested exact scope review in the original statement receipts')
        problem=current['problem_binding']; engine_plan=discovery.prepare_start(project,problem['id'],version=problem['version'])
    else: raise ValueError('Switch phase must be explicit CLOSE or START')
    value={'schema_version':1,'candidate_id':candidate_id,'candidate_revision':expected_revision,
        'candidate_spec_sha256':current['spec_sha256'],'phase':phase,'reason':reason,
        'goal_anchor_id':current['goal_anchor_id'],'route_epoch':observed['snapshot']['route_epoch'],
        'route_sha256':observed['snapshot']['route_sha256'],'route_registry_sha256':observed['snapshot']['route_registry_sha256'],
        'route_effective_rounds':observed['route_budget']['effective_rounds'],'engine_plan':engine_plan,
        'readiness_snapshot':_readiness_snapshot(project,current) if phase=='START' else None,
        'restart_review':restart,
        'close_attribution':attribution,
        'evidence_bindings':{**current['goal_binding']['files'],**current['evidence_bindings']}}
    digest=object_hash(value); value['request_sha256']=digest; value['request_id']='SW-'+digest
    return value


def restart_review_template(project,candidate_id,claim_id):
    """Prepare an operator scope card; this never supplies independent approval."""
    candidate=catalog.show(project,candidate_id)
    verification.prepare_request(project,candidate_id,claim_id,adapter_id='branch-restart-v1')
    old=[r for r in history.projection_records(project) if r['candidate_id']==candidate_id and r['status'] in {'REFUTED','COVERED'}]
    if not old: raise ValueError('A prior exact verified branch resolution is required')
    previous=old[-1]; earlier=catalog.show(project,candidate_id,revision=previous['candidate_revision'])
    item=claim_graph.get(project,claim_id)
    return {'schema_version':1,'kind':'INDEPENDENT_BRANCH_RESTART_REVIEW','decision':'CONFIRMED',
        'candidate_id':candidate_id,'candidate_revision':candidate['revision'],'candidate_spec_sha256':candidate['spec_sha256'],
        'previous_resolution_id':previous['resolution_id'],'previous_candidate_revision':previous['candidate_revision'],
        'previous_candidate_spec_sha256':previous['candidate_spec_sha256'],
        'changed_hypothesis':{'before':earlier['spec']['hypothesis'],'after':candidate['spec']['hypothesis']},
        'changed_assumptions':{'before':earlier['spec']['assumptions'],'after':candidate['spec']['assumptions']},
        'why_old_evidence_not_applicable':None,'claim_id':claim_id,'claim_revision':item['revision'],
        'claim_spec_sha256':item['spec_sha256'],'reviewer':None}


def _restart_review(project,candidate):
    prior=[r for r in history.projection_records(project) if r['candidate_id']==candidate['id'] and r['status'] in {'REFUTED','COVERED'}]
    if not prior: return False
    previous=prior[-1]; earlier=catalog.show(project,candidate['id'],revision=previous['candidate_revision'])
    if (earlier['spec']['hypothesis']==candidate['spec']['hypothesis']
            and earlier['spec']['assumptions']==candidate['spec']['assumptions']): return False
    # Scope reviews are attested after a candidate revision is immutable.
    # Finding them through canonical receipts avoids a circular candidate-file
    # hash/version dependency, without changing the original candidate schema.
    graph=claim_graph.load(project)
    paths=sorted({relative for item in graph['claims'] for relative in item.get('reviews',{}).get('statement',{}).get('evidence',{})})
    for relative in paths:
        try:
            value=configuration.load_json(security_model.validate.safe(project,relative))
            if (not isinstance(value,dict) or value.get('kind')!='INDEPENDENT_BRANCH_RESTART_REVIEW'
                    or value.get('candidate_id')!=candidate['id'] or value.get('candidate_revision')!=candidate['revision']
                    or value.get('candidate_spec_sha256')!=candidate['spec_sha256'] or value.get('decision')!='CONFIRMED'): continue
            expected=restart_review_template(project,candidate['id'],value['claim_id'])
            if (set(value)!=set(expected) or type(value.get('schema_version')) is not int
                    or {k:v for k,v in value.items() if k not in {'reviewer','why_old_evidence_not_applicable'}}
                       !={k:v for k,v in expected.items() if k not in {'reviewer','why_old_evidence_not_applicable'}}
                    or not isinstance(value.get('why_old_evidence_not_applicable'),str)
                    or len(value['why_old_evidence_not_applicable'].strip())<32): continue
            item=claim_graph.get(project,value['claim_id']); receipt=item['reviews'].get('statement',{})
            graph=claim_graph.load(project); latches=claim_graph._revocation_latches(item,graph.get('events',[]))
            if (receipt.get('evidence',{}).get(relative)==hash_file(project/relative) and fresh(project,receipt['evidence'])
                    and receipt.get('claim_sha256')==item['spec_sha256'] and claim_graph.receipt_history_valid(item,graph.get('events'))
                    and latches is not None and 'review:statement' not in latches
                    and value.get('reviewer')==receipt.get('reviewer')
                    and value['reviewer'].strip().casefold()!=item['spec']['proposer'].strip().casefold()):
                return {'file':relative,'sha256':hash_file(project/relative),'claim_id':item['id'],
                    'claim_revision':item['revision'],'claim_spec_sha256':item['spec_sha256'],
                    'statement_receipt_sha256':object_hash(receipt),'reviewer':value['reviewer'],
                    'authority_bindings':{'research/discovery/CLAIM_GRAPH.json':hash_file(project/'research/discovery/CLAIM_GRAPH.json')}}
        except (ValueError,OSError,KeyError,TypeError): pass
    return False


def _switch_fresh(project,request,*,recovery=False):
    execution_preflight(project,allowed_operation_id=request['request_id'] if recovery else None)
    _valid_request(request,'SW'); observed=_switch_guard(project); current=catalog.show(project,request['candidate_id'])
    if (current['revision']!=request['candidate_revision'] or current['spec_sha256']!=request['candidate_spec_sha256']
            or current['goal_anchor_id']!=request['goal_anchor_id'] or observed['snapshot']['route_epoch']!=request['route_epoch']
            or observed['snapshot']['route_sha256']!=request['route_sha256']
            or observed['snapshot']['route_registry_sha256']!=request['route_registry_sha256']
            or observed['route_budget']['effective_rounds']!=request['route_effective_rounds']
            or request['evidence_bindings']!={**current['goal_binding']['files'],**current['evidence_bindings']}
            or not fresh(project,request['evidence_bindings'])):
        raise ValueError('Switch frozen route/goal/candidate/evidence changed; no original authority will be overwritten')
    discovery._validate_prepared(project,request['engine_plan'])
    plan=request['engine_plan']; problem=current['problem_binding']
    if request['phase']!=plan['operation']: raise ValueError('Switch phase cannot substitute a different original engine operation')
    if (plan['result']['problem_id']!=problem['id'] or plan['result']['problem_version']!=problem['version']
            or plan['result']['problem_sha256']!=problem['spec_sha256']):
        raise ValueError('Switch original engine plan belongs to a different candidate fixed problem')
    if request['phase']=='CLOSE' and request['reason']!=plan['arguments']['reason']:
        raise ValueError('Switch close reason differs from its frozen original operation')
    if request['phase']=='CLOSE':
        if request.get('readiness_snapshot') is not None or request.get('restart_review') is not None:
            raise ValueError('CLOSE cannot substitute START readiness or independent restart metadata')
        if plan['arguments'].get('capture_state') is not True or plan['before_state'] is None:
            raise ValueError('R15 CLOSE requires the exact original STATE beforeimage, including raw-byte CAS')
        owner=next(a for a in plan['before_ledger']['attempts'] if a['id']==plan['before_ledger']['active_attempt'])
        _close_owner_preflight(project,owner)
        actual=_close_attribution(project,current,plan['result']['id'],explicit=True)
        if actual!=request.get('close_attribution'): raise ValueError('Switch exact candidate close attribution changed')
    if request['phase']=='START':
        if not current['eligible_for_attempt'] or _readiness_snapshot(project,current)!=request['readiness_snapshot']:
            raise ValueError('Switch START dependency review/readiness changed; retain the original partial owner for audit')
        previous=[r for r in history.projection_records(project) if r['candidate_id']==current['id'] and r['status'] in {'REFUTED','COVERED'}]
        if previous and (current['revision']<=previous[-1]['candidate_revision']
                or current['semantic_sha256']==previous[-1]['candidate_semantic_sha256'] or not _restart_review(project,current)):
            raise ValueError('Restart requires changed assumptions/hypothesis and a fresh independent restart scope review')
        if (previous and _restart_review(project,current)!=request.get('restart_review')) or (not previous and request.get('restart_review') is not None):
            raise ValueError('Restart independent review authority or exact scope changed after switch preparation')


def apply_switch(project,request,*,locks_held=False):
    with _locks(project,locks_held):
        location=_paths(project,request['request_id'],'switches')['intent']; intent=_read_intent(location)
        if intent:
            if intent['request']!=request: raise ValueError('Switch request differs from its frozen local intent')
            _require_witness(project,request,'switches')
            if intent['phase']=='APPLIED': return copy.deepcopy(intent['record'])
            history.load(project,operation_id=request['request_id'])
        _switch_fresh(project,request,recovery=intent is not None)
        if intent is None:
            # Exact original beforeimages are required before the write-ahead
            # fence. A caller cannot smuggle an already changed ledger as ours.
            plan=request['engine_plan']
            if (discovery._file_sha(discovery.ledger_path(project))!=plan['before_ledger_sha256']
                    or (plan['before_state'] is not None and discovery._file_sha(project/'research/STATE.json')!=plan['before_state_sha256'])):
                raise ValueError('Switch beforeimages changed before prepare commit')
            intent={'schema_version':1,'phase':'PREPARED','request':request,'created_at':stamp()}; _write_intent(location,intent)
            _write_witness(project,request,'switches')
        result=discovery.commit_prepared(project,request['engine_plan'],allow_partial=True)
        record={'request_id':request['request_id'],'candidate_id':request['candidate_id'],'candidate_revision':request['candidate_revision'],
            'candidate_spec_sha256':request['candidate_spec_sha256'],'close_attribution':request['close_attribution'],
            'phase':request['phase'],'status':'APPLIED','attempt_id':result['id'],'route_effective_rounds':request['route_effective_rounds'],
            'route_epoch':request['route_epoch'],'scientific_acceptance':False,'research_execution_started':False,
            'next_required_action':'EXPLICIT_PREPARE_START_OTHER_CANDIDATE' if request['phase']=='CLOSE' else 'EXPLICIT_ORIGINAL_RUN_COMMAND',
            'applied_at':intent['created_at']}
        history.append(project,'SWITCH_APPLIED',record,request['request_id'],request['reason'])
        intent.update(phase='APPLIED',record=record); _write_intent(location,intent)
        return copy.deepcopy(record)


def recover_switch(project,request_id,*,locks_held=False):
    location=_paths(project,request_id,'switches')['intent']; intent=_read_intent(location)
    if intent is None: raise ValueError('No frozen original switch operation to recover')
    return apply_switch(project,intent['request'],locks_held=locks_held)


def switch_status(project,request_id):
    intent=_read_intent(_paths(project,request_id,'switches')['intent'])
    if intent is None: raise ValueError('Unknown switch operation')
    return {'request_id':request_id,'phase':intent['phase'],'record':copy.deepcopy(intent.get('record')),
            'research_execution_started':False,'automatic_retry_allowed':False}
