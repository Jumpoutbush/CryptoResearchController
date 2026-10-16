"""Deterministic protocol review findings; independent human review stays required."""
from __future__ import annotations
import copy
import re
import configuration
from engine.common import object_hash
from research_quality import hash_file
from route_budget import stamp
from . import catalog, security_model
from .verifiers.interface import _locks

LIMITATIONS=[
    'Every output is REVIEW_FINDING, not an independent human attestation or a cryptographic proof.',
    'Finite supplied traces test declared data consistency only; no protocol program, simulator, Lean or model is executed.',
    'A trace exceeding the frozen corruption threshold is outside the original theorem scope, not a break of that theorem.',
    'Matching an original PDF theorem location does not prove premise completeness or applicability of its reduction.',
    'Cost decompositions and framework differences remain declarations until independent review.',
    'No canonical claim, G8 gate, candidate status, frozen target, research state or budget is changed.',
    'Paired local hashes detect partial loss/conflicts, not an owner deleting or rolling back every audit file.']


def home(project):
    return catalog._unlinked(catalog.path(project).parent/'security_review')


def _paths(project,rid):
    if not isinstance(rid,str) or not re.fullmatch(r'SR-[0-9a-f]{64}',rid): raise ValueError('Invalid frozen security review request ID')
    return {kind:catalog._unlinked(home(project)/(rid+'.'+kind+'.json')) for kind in ('request','started','report')}


def _valid(request):
    if not isinstance(request,dict) or type(request.get('schema_version')) is not int or request['schema_version']!=1:
        raise ValueError('Unsupported security review request schema')
    body={k:v for k,v in request.items() if k not in {'request_id','request_sha256'}}
    if request.get('request_sha256')!=object_hash(body) or request.get('request_id')!='SR-'+object_hash(body):
        raise ValueError('Security review request digest mismatch')


def _fresh(project,request):
    try:
        _valid(request); binding=request['claim_binding']
        current=security_model.prepare_request(project,binding['candidate_id'],binding['claim_id'],request['card'])
        return (current==request,None if current==request else 'Exact candidate/claim/problem/goal/card/source/tool bindings changed')
    except (ValueError,OSError,KeyError,TypeError) as exc: return False,str(exc)


def _base(request):
    return {'schema_version':1,'request_id':request.get('request_id'),'request_sha256':object_hash(request),
        'claim_binding':copy.deepcopy(request.get('claim_binding',{})),
        'source_hashes':copy.deepcopy(request.get('source_hashes',{})),
        'finding_level':'REVIEW_FINDING','decision':'NEEDS_REVIEW','threat_model_complete':False,
        'findings':[],'attack_plans':[],'source_checks':copy.deepcopy(request.get('source_checks',[])),
        'claim_status_changed':False,'candidate_status_changed':False,'scientific_acceptance':False,
        'independent_review_required':True,'construction_progression_allowed':False,'safety_gate_passed':False,
        'execution_started':False,'automatic_retry_allowed':False,'limitations':list(LIMITATIONS),
        'next_review':['Use existing claim review proof_and_statement with an independent human reviewer and exact evidence.',
                       'Use existing claim review novelty with theorem-level original-source comparisons; never infer novelty from this report.']}


def _failed(request,reason):
    return {**_base(request),'decision':'FAILED','reason':reason}


def _analyze(request):
    report=_base(request); card=request['card']; frozen=request['frozen_security_model']; candidate=request['candidate_security_model']
    findings=report['findings']; needs_input=False
    obligations=[item['id'] for item in request['frozen_obligations']]
    def finding(code,detail,*,proof_step='SECURITY_MODEL',scope='DECLARED_OBLIGATION_ONLY',evidence=None):
        nonlocal needs_input
        if code in {'MODEL_SCOPE_MISMATCH','SIMULATOR_AUTHORIZATION_UNASSESSED'}: needs_input=True
        findings.append({'code':code,'detail':detail,'game':card['security_game']['id'],'proof_step':proof_step,
            'affected_obligations':list(obligations),'scope':scope,'evidence_refs':evidence or [],
            'level':'REVIEW_FINDING','independent_review_required':True})
    game=card['security_game']; corruption=card['corruption_model']; leakage=card['leakage_function']
    for key,expected_type in (('corruption_timing',str),('corruption_threshold',int),('leakage_function',str),('party_count',int)):
        if type(frozen.get(key)) is not expected_type or candidate.get(key)!=frozen.get(key):
            needs_input=True; finding('FROZEN_MODEL_MAPPING_REQUIRED','No matching operator-frozen structured '+key+' is available; do not infer it from prose.')
    if (not game['definition'] or not game['rounds'] or not card['parties'] or not card['proof_paths']
            or any(corruption[k] is None for k in ('timing','claimed_timing','threshold','claimed_threshold','dropout_model'))
            or leakage['name'] is None or any(value is None for value in card['abort_behavior'].values())):
        needs_input=True; finding('SECURITY_MODEL_INCOMPLETE','Define the exact adversary, game, leakage, abort and proof paths before independent review.')
    authority=frozen.get('ideal_interface_sha256')
    if not isinstance(authority,str) or not re.fullmatch('[0-9a-f]{64}',authority):
        finding('SIMULATOR_AUTHORIZATION_UNASSESSED','The original fixed model has no user-frozen ideal_interface_sha256; the card cannot authorize its own simulator inputs, programming, game or leakage.')
    elif candidate.get('ideal_interface_sha256')!=authority or object_hash(security_model.ideal_interface_binding(card))!=authority:
        finding('MODEL_SCOPE_MISMATCH','Game/ideal-interface authorization differs from the user-frozen model; a card cannot add secrets or programmability to authorize itself.')
    if frozen.get('corruption_timing') is not None and any(
            corruption[k]!=frozen['corruption_timing'] for k in ('timing','claimed_timing') if corruption[k] is not None):
        finding('MODEL_SCOPE_MISMATCH','Static and adaptive corruption are different claims; the frozen theorem cannot be silently strengthened.')
    threshold=frozen.get('corruption_threshold')
    adaptive_budget=frozen.get('corruption_budget_scope')
    if frozen.get('corruption_timing')=='ADAPTIVE' and adaptive_budget not in {'CUMULATIVE','PER_ROUND'}:
        needs_input=True; finding('ADAPTIVE_CORRUPTION_BUDGET_UNDEFINED','The frozen adaptive model must explicitly define CUMULATIVE or PER_ROUND corruption accounting; per-step counts do not define the whole game.')
    if type(threshold) is int and any(corruption[k]!=threshold for k in ('threshold','claimed_threshold') if corruption[k] is not None):
        finding('MODEL_SCOPE_MISMATCH','The declared corruption threshold differs from the frozen problem; excess corruption is OUTSIDE_FROZEN_MODEL.')
    if type(frozen.get('party_count')) is int and len(card['parties'])!=frozen['party_count']:
        finding('MODEL_SCOPE_MISMATCH','The declared party set size differs from the frozen model.')
    if frozen.get('leakage_function') is not None and leakage['name']!=frozen['leakage_function']:
        finding('MODEL_SCOPE_MISMATCH','The named leakage function differs from the frozen model; natural privacy claims remain unapproved.')
    omitted=set(request['frozen_assumptions'])-set(card['setup_assumptions'])
    if omitted: finding('FROZEN_PREMISES_OMITTED','Missing unchanged problem assumptions: '+', '.join(sorted(omitted)))
    abort=card['abort_behavior']
    if abort['public_reject_bit'] and (not abort['ideal_reject_bit'] or 'reject_bit' not in leakage['ideal_leakage']):
        finding('REJECTION_BIT_OMITTED_FROM_IDEAL_LEAKAGE','Public reject_bit is visible but the declared ideal leakage omits it.',proof_step='ABORT_SIMULATION')
    for flag,name in (('forking_visible','fork'),('dropout_visible','dropout')):
        if abort[flag] and name not in leakage['ideal_leakage']:
            finding('PUBLIC_BEHAVIOR_OMITTED_FROM_IDEAL_LEAKAGE',name+' is publicly visible but absent from declared ideal leakage.',proof_step='ABORT_SIMULATION')
    missing_observables=set(leakage['real_observable'])-set(leakage['ideal_leakage'])
    if missing_observables:
        finding('REAL_IDEAL_LEAKAGE_GAP','Explicitly simulate or justify each unmatched observable: '+', '.join(sorted(missing_observables)),proof_step='SIMULATOR_OUTPUT')
    simulator=card['simulator_interface']; available=set(simulator['ideal_inputs'])
    required=set(simulator['required_inputs'])
    for inputs in simulator['output_dependencies'].values(): required.update(inputs)
    if required-available:
        finding('SIMULATOR_INPUT_UNAVAILABLE','The simulator requires inputs not supplied by its declared ideal interface: '+', '.join(sorted(required-available)),proof_step='SIMULATOR_INPUT')
    if set(simulator['required_programming'])-set(simulator['authorized_programming']):
        finding('UNAUTHORIZED_SIMULATOR_PROGRAMMING','The reduction assumes unavailable programmability: '+', '.join(sorted(set(simulator['required_programming'])-set(simulator['authorized_programming']))),proof_step='SIMULATOR_PROGRAMMING')
    if not set(game['public_outputs'])<=set(simulator['output_dependencies']):
        needs_input=True; finding('SIMULATOR_INTERFACE_INCOMPLETE','Give dependencies for every public output, without assuming secret ideal inputs.')
    composition=card['composition_scope']; rounds=composition['rounds']; sessions=composition['sessions']
    if rounds is None or sessions is None:
        needs_input=True; finding('COMPOSITION_SCOPE_INCOMPLETE','Define exact round and session scope before claiming composition security.')
    if (rounds or 0)>1 or (sessions or 0)>1:
        if not composition['cross_round_collusion'] or leakage['cross_round_linkage'] in {None,'UNDEFINED'}:
            needs_input=True; finding('CROSS_ROUND_COLLUSION_UNDEFINED','Multi-round/session collusion and observable linkage have no defined game.')
    if composition['component_theorems'] and not composition['end_to_end_reduction']:
        finding('END_TO_END_REDUCTION_MISSING','Component theorems do not establish the composed protocol theorem.',proof_step='COMPOSITION_HYBRID')
    loss=card['reduction_loss']
    report['reduction_table']={'parameters':copy.deepcopy(loss['parameters']),'bit_widths':copy.deepcopy(loss['bit_widths']),
        'rounds':loss['rounds'],'failure_events':copy.deepcopy(loss['failure_events']),'loss_bound':loss['loss_bound'],
        'status':'DECLARED_NOT_VERIFIED' if loss['parameters'] and loss['bit_widths'] and loss['rounds'] and loss['failure_events'] and loss['loss_bound'] else 'UNASSESSED'}
    missing_loss=[name for name in ('parameters','bit_widths','rounds','failure_events','loss_bound') if not loss[name]]
    if missing_loss:
        finding('REDUCTION_BOUND_INCOMPLETE','Missing reduction fields: '+', '.join(missing_loss),proof_step='REDUCTION_LOSS')
    report['cost_assessment']={'status':'DECLARED_NOT_VERIFIED' if loss['cost_breakdown'] else 'UNASSESSED',
        'breakdown':copy.deepcopy(loss['cost_breakdown']),'can_support_complexity_or_novelty_claim':False}
    report['framework_comparison']=[]
    known_spans={item['span_id'] for item in request['source_checks'] if item['status']=='SOURCE_LOCATION_ONLY'}
    for row in card['baseline_comparison']:
        assessed=copy.deepcopy(row); assessed['verification_status']='UNVERIFIED_DECLARATION'
        assessed['source_status']='ORIGINAL_LOCATION_ONLY' if row['source_span_ids'] and set(row['source_span_ids'])<=known_spans else 'NEEDS_SOURCE'
        report['framework_comparison'].append(assessed)
        if row['relation']=='DIRECT_COMPOSITION':
            finding('POTENTIALLY_COVERED','Declared direct composition with '+row['framework']+' requires original-theorem comparison; candidate status is unchanged.',proof_step='NOVELTY_COMPARISON')
    for dependency,check in zip(card['dependencies'],request['source_checks']):
        required=set(dependency['required_assumptions'])|set(check.get('source_assumptions',[]))
        if required-set(dependency['used_assumptions']):
            finding('THEOREM_PREMISES_OMITTED','The reused theorem has unaccounted declared/original-review premises: '+', '.join(sorted(required-set(dependency['used_assumptions']))),proof_step=dependency['proof_step'])
        if check.get('coverage_verdict')=='COVERS':
            finding('POTENTIALLY_COVERED','An original technical review declares coverage; independent exact-model comparison remains required.',proof_step=dependency['proof_step'])
    for trace in card['attack_traces']:
        if trace['game']!=game['id'] or not set(trace['affected_obligations'])<=set(obligations):
            raise ValueError('Attack trace must bind the exact game and fixed proof obligations')
        status='FIXED_TRACE_PLAN_REQUIRES_INDEPENDENT_REVIEW'
        excess=type(threshold) is int and any(len(step['corrupted_parties'])>threshold for step in trace['execution'])
        if frozen.get('corruption_timing')=='STATIC':
            sets=[set(step['corrupted_parties']) for step in trace['execution']]
            excess=excess or any(parties!=sets[0] or not parties<=set(corruption['corrupted_parties']) for parties in sets)
        elif frozen.get('corruption_timing')=='ADAPTIVE':
            if adaptive_budget=='CUMULATIVE' and type(threshold) is int:
                excess=excess or len(set().union(*(set(step['corrupted_parties']) for step in trace['execution'])))>threshold
            elif adaptive_budget not in {'CUMULATIVE','PER_ROUND'}: status='UNVERIFIED_CORRUPTION_SCOPE'
        if game['rounds'] is not None:
            excess=excess or any(not 1<=step['round']<=game['rounds'] for step in trace['execution'])
        if excess: status='OUT_OF_SCOPE'
        elif trace['kind']=='SELECTIVE_REJECTION' and status!='UNVERIFIED_CORRUPTION_SCOPE':
            for left in trace['execution']:
                for right in trace['execution']:
                    if (left['public_inputs']==right['public_inputs'] and left['ideal_leakage']==right['ideal_leakage']
                            and left['round']==right['round'] and set(left['corrupted_parties'])==set(right['corrupted_parties'])
                            and type(left['public_output'].get('reject_bit')) in {int,bool}
                            and type(right['public_output'].get('reject_bit')) in {int,bool}
                            and left['public_output']['reject_bit'] in {0,1} and right['public_output']['reject_bit'] in {0,1}
                            and left['secret_assignment']!=right['secret_assignment']
                            and left['public_output'].get('reject_bit')!=right['public_output'].get('reject_bit')):
                        status='FINITE_TRACE_DIFFERENCE_REQUIRES_REVIEW'
        report['attack_plans'].append({**copy.deepcopy(trace),'status':status,
            'counterexample_to_frozen_goal':False,'evidence_level':'SUPPLIED_FINITE_DATA_NOT_PROTOCOL_EXECUTION',
            'independent_review_required':True})
    report['threat_model_complete']=not needs_input
    report['threat_model_complete_scope']='DECLARED_FIELDS_AND_EXPLICIT_FROZEN_INTERFACE_MAPPING_ONLY_NOT_SECURITY_PROOF'
    report['decision']='NEEDS_INPUT' if needs_input else 'NEEDS_SOURCE' if any(c['status']=='UNVERIFIED' for c in request['source_checks']) else 'NEEDS_REVIEW'
    report['earliest_missing_obligation']=findings[0] if findings else {
        'code':'INDEPENDENT_PROTOCOL_REVIEW_REQUIRED','game':game['id'],'proof_step':'FULL_SECURITY_REDUCTION'}
    return report


def _read(project,rid):
    paths=_paths(project,rid)
    if not paths['request'].is_file() or not paths['started'].is_file():
        raise ValueError('Frozen security request or STARTED fence missing; never reconstruct it from current inputs')
    request=configuration.load_json(paths['request']); _valid(request)
    if request['request_id']!=rid: raise ValueError('Security review request identity/path mismatch')
    started=configuration.load_json(paths['started'])
    if (not isinstance(started,dict) or set(started)!={'schema_version','request_id','request_sha256','phase','at','sha256'}
            or type(started['schema_version']) is not int or started['schema_version']!=1
            or started['request_id']!=rid or started['phase']!='STARTED'
            or started['request_sha256']!=object_hash(request)
            or started['sha256']!=object_hash({k:v for k,v in started.items() if k!='sha256'})):
        raise ValueError('Security review dispatch fence changed')
    if not paths['report'].is_file(): return request,None
    report=configuration.load_json(paths['report'])
    if (not isinstance(report,dict) or report.get('request_id')!=rid or report.get('request_sha256')!=object_hash(request)
            or report.get('started_sha256')!=started['sha256'] or report.get('claim_binding')!=request['claim_binding']
            or report.get('source_hashes')!=request['source_hashes'] or report.get('finding_level')!='REVIEW_FINDING'
            or report.get('decision') not in {'NEEDS_REVIEW','NEEDS_INPUT','NEEDS_SOURCE','FAILED'}
            or any(report.get(key) is not False for key in ('claim_status_changed','candidate_status_changed','scientific_acceptance',
                                                          'construction_progression_allowed','safety_gate_passed','execution_started'))
            or report.get('independent_review_required') is not True
            or report.get('report_sha256')!=object_hash({k:v for k,v in report.items() if k!='report_sha256'})):
        raise ValueError('Security review report integrity or permission boundary changed')
    return request,report


def review(project,request,*,locks_held=False):
    if not isinstance(request,dict): raise ValueError('Security review request must be an object')
    good,reason=_fresh(project,request)
    if not good: return _failed(request,'STALE_OR_INVALID_SECURITY_REVIEW_REQUEST: '+str(reason))
    with _locks(project,locks_held):
        good,reason=_fresh(project,request)
        if not good: return _failed(request,'STALE_OR_INVALID_SECURITY_REVIEW_REQUEST: '+str(reason))
        paths=_paths(project,request['request_id'])
        if any(path.exists() for path in paths.values()):
            try: old,report=_read(project,request['request_id'])
            except ValueError as exc: return _failed(request,'UNKNOWN_LOCAL_SECURITY_REVIEW_OUTCOME: '+str(exc))
            if old!=request: return _failed(request,'SECURITY_REVIEW_REQUEST_ID_CONFLICT')
            return report if report is not None else _failed(request,'UNKNOWN_LOCAL_SECURITY_REVIEW_OUTCOME: no complete report; no automatic retry')
        configuration.atomic_json(paths['request'],request)
        started={'schema_version':1,'request_id':request['request_id'],'request_sha256':object_hash(request),'phase':'STARTED','at':stamp()}
        started['sha256']=object_hash(started); configuration.atomic_json(paths['started'],started)
        try: report=_analyze(request)
        except Exception as exc: report=_failed(request,type(exc).__name__+': '+str(exc))
        good,reason=_fresh(project,request)
        if not good: report=_failed(request,'STALE_AFTER_SECURITY_REVIEW: '+str(reason))
        report.update(started_sha256=started['sha256'],completed_at=stamp(),
            evidence_files=[{'scope':'CONTROLLER','path':path.relative_to(configuration.ROOT).as_posix(),'sha256':hash_file(path)}
                            for kind,path in paths.items() if kind!='report'])
        report['report_sha256']=object_hash(report); configuration.atomic_json(paths['report'],report)
        return report


def show(project,request_id):
    request,report=_read(project,request_id)
    if report is None: return _failed(request,'UNKNOWN_LOCAL_SECURITY_REVIEW_OUTCOME: no complete report')
    good,reason=_fresh(project,request)
    return {**report,'fresh':good,'freshness_reason':reason}


def recheck(project,request_id):
    request,report=_read(project,request_id)
    if report is None: return _failed(request,'UNKNOWN_LOCAL_SECURITY_REVIEW_OUTCOME: never retry an interrupted review')
    good,reason=_fresh(project,request)
    if not good: return {**report,'decision':'FAILED','fresh':False,'reason':'STALE_SECURITY_REVIEW_REPORT: '+str(reason)}
    return {**report,'fresh':True,'recheck_scope':'FROZEN_INPUT_AND_FINDING_INTEGRITY_ONLY','new_execution_started':False}
