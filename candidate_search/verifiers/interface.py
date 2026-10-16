"""Frozen verifier requests and audit receipts; no canonical claim writes."""
from __future__ import annotations
import contextlib
import copy
import math
from pathlib import Path
import re
import sys
import configuration
from engine import claim_graph, falsification, formal_verifier
from engine.common import fresh, identifier, object_hash, policy
from research_quality import hash_file
from route_budget import file_lock, stamp
from candidate_search import catalog, validate

STATUSES=frozenset({'EXECUTED','COUNTEREXAMPLE_FOUND','NO_COUNTEREXAMPLE_WITHIN_BOUND',
                    'TOOL_PASSED_AUDIT_PENDING','UNSUPPORTED','FAILED'})
LIMITATIONS=[
    'Verification metadata never changes canonical claims, proof/novelty reviews, goals, state or budgets.',
    'Exact integer results concern only the frozen machine predicate; candidate/natural-statement correspondence requires independent review.',
    'A bounded search without a counterexample is not a proof; no adapter certifies cryptographic simulation security.',
    'Trusted data-only child lifetime/resource bounds do not certify OS deny-read or network isolation.',
    'Lean execution remains blocked; source, declaration type, quantifiers and axioms need independent correspondence review.',
    'Local paired audit files detect partial loss or conflicting writes, not deletion/rollback of all authorities by their owner.']


def home(project):
    return catalog._unlinked(catalog.path(project).parent/'verification')


def _id(value):
    if not isinstance(value,str) or not re.fullmatch(r'V-[0-9a-f]{64}',value):
        raise ValueError('Verifier request ID must be its exact frozen V- SHA-256 identifier')
    return value


def _paths(project,rid):
    _id(rid)
    return {kind:catalog._unlinked(home(project)/(rid+'.'+kind+'.json'))
            for kind in ('request','started','receipt')}


def _tool_bindings():
    root=Path(__file__).resolve().parents[2]
    relatives=['candidate_search/verifiers/'+name for name in (
        'interface.py','integer_adapter.py','lean_adapter.py','trusted_integer_worker.py')]
    relatives+=['engine/falsification.py','engine/formal_verifier.py','supervision_process.py']
    return {rel:hash_file(catalog._unlinked(root/rel)) for rel in relatives}


def prepare_request(project,candidate_id,claim_id,*,adapter_id='integer-v1',low=-3,high=3,
                    max_cases=10000,max_seconds=3,wall_timeout_seconds=5,proof_file=None,declaration=None):
    identifier(candidate_id); identifier(claim_id); identifier(adapter_id)
    project,key=catalog._project(project); current=catalog.anchor(project); candidate=catalog.show(project,candidate_id)
    if (candidate['goal_binding']!=current['goal_binding'] or candidate['goal_anchor_id']!=current['goal_anchor_id']
            or candidate['route_epoch']!=current['route_epoch'] or not fresh(project,candidate['evidence_bindings'])):
        raise ValueError('STALE_VERIFICATION_INPUT: candidate frozen goal or evidence changed')
    binding=candidate['problem_binding']
    if binding['status']!='FIXED' or validate.problem(project,candidate['spec'])!=binding:
        raise ValueError('Verifier requests require the exact unchanged fixed problem')
    validate.safe(project,'research/discovery/CLAIM_GRAPH.json')
    item=claim_graph.get(project,claim_id); graph=claim_graph.load(project)
    if (item['spec_sha256']!=object_hash(item['spec']) or item['binding']!=current['goal_binding']
            or not fresh(project,item['evidence']) or not claim_graph.dependency_bindings_valid(item)
            or not claim_graph.receipt_history_valid(item,graph.get('events'))):
        raise ValueError('STALE_VERIFICATION_INPUT: claim revision, sources or canonical audit history changed')
    if (item['spec']['problem_id']!=binding['id'] or item['spec']['problem_version']!=binding['version']
            or item['problem_sha256']!=binding['spec_sha256']):
        raise ValueError('Claim and candidate must bind the same exact fixed problem')
    if type(low) is not int or type(high) is not int or not -1000<=low<=high<=1000:
        raise ValueError('Integer bounds must satisfy -1000 <= low <= high <= 1000')
    if type(max_cases) is not int or not 1<=max_cases<=10000: raise ValueError('Verifier case limit is 1..10000')
    for name,value,upper in [('max_seconds',max_seconds,3),('wall_timeout_seconds',wall_timeout_seconds,15)]:
        if type(value) not in {int,float} or not math.isfinite(value) or not 0<value<=upper:
            raise ValueError(name+' exceeds the positive verifier resource bound')
    original_policy=policy(project)
    resource_policy={k:original_policy[k] for k in (
        'counterexample_max_cases','counterexample_max_seconds','verifier_timeout_seconds')}
    max_cases=min(max_cases,resource_policy['counterexample_max_cases'])
    max_seconds=float(min(max_seconds,resource_policy['counterexample_max_seconds']))
    wall_timeout_seconds=float(min(wall_timeout_seconds,resource_policy['verifier_timeout_seconds']))
    sources={**current['goal_binding']['files'],**binding['source_bindings'],
             **candidate['evidence_bindings'],**item['evidence']}
    options={'low':low,'high':high,'max_cases':max_cases,'max_seconds':max_seconds,
             'wall_timeout_seconds':wall_timeout_seconds,'proof_file':proof_file,'declaration':declaration}
    if adapter_id=='lean-v1':
        validate.safe(project,proof_file,roots={'proofs'})
        if not isinstance(declaration,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*',declaration):
            raise ValueError('Lean target requires a plain exact declaration name')
        workspace=project/'proofs/lean'
        sources.update(formal_verifier.source_bindings(project,workspace))
        sources[proof_file]=hash_file(validate.safe(project,proof_file,roots={'proofs'}))
    for relative,digest in sources.items():
        if hash_file(validate.safe(project,relative))!=digest: raise ValueError('Frozen verifier source SHA mismatch')
    request={'schema_version':1,'project_id':key,'adapter_id':adapter_id,
        'claim_binding':{'claim_id':claim_id,'claim_revision':item['revision'],'claim_sha256':item['spec_sha256'],
            'candidate_id':candidate_id,'candidate_revision':candidate['revision'],'candidate_sha256':candidate['spec_sha256'],
            'goal_anchor_id':current['goal_anchor_id'],'goal_sha256':current['goal_sha256'],
            'route_epoch':current['route_epoch'],
            'problem_id':binding['id'],'problem_version':binding['version'],'problem_sha256':binding['spec_sha256'],
            'dependency_pins':copy.deepcopy(item['dependency_pins'])},
        'goal_binding':copy.deepcopy(current['goal_binding']),'source_hashes':sources,
        'tool_bindings':_tool_bindings(),'python_version':sys.version.split()[0],'resource_policy':resource_policy,
        'natural_statement':item['spec']['statement'],
        'natural_problem_scope':{k:copy.deepcopy(binding['spec'][k]) for k in (
            'domain','quantifiers','assumptions','immutable_constraints','input_contract','output_contract')},
        'statement':copy.deepcopy(item['spec'].get('machine_statement')),'options':options}
    digest=object_hash(request); request['request_sha256']=digest; request['request_id']='V-'+digest
    return request


def _request_valid(request):
    if (not isinstance(request,dict) or type(request.get('schema_version')) is not int or request['schema_version']!=1):
        raise ValueError('Invalid verifier request schema')
    rid=_id(request.get('request_id')); payload={k:v for k,v in request.items() if k not in {'request_id','request_sha256'}}
    if request.get('request_sha256')!=object_hash(payload) or rid!='V-'+object_hash(payload):
        raise ValueError('Verifier request hash mismatch')


def _fresh(project,request):
    try:
        _request_valid(request)
        binding=request['claim_binding']; options=request['options']
        now=prepare_request(project,binding['candidate_id'],binding['claim_id'],adapter_id=request['adapter_id'],**options)
        if now!=request: return False,'Exact claim/candidate/problem/goal/source/tool bindings changed'
        return True,None
    except (ValueError,OSError,KeyError,TypeError) as exc: return False,str(exc)


def _base(request):
    return {'schema_version':1,'request_id':request.get('request_id'),'request_sha256':object_hash(request),
        'claim_binding':copy.deepcopy(request.get('claim_binding',{})),
        'source_hashes':copy.deepcopy(request.get('source_hashes',{})),
        'tool_bindings':copy.deepcopy(request.get('tool_bindings',{})),
        'adapter_id':request.get('adapter_id'),'tool_version':'NOT_EXECUTED','result_status':'FAILED',
        'execution_started':False,'scientific_acceptance':False,'positive_basis':False,
        'statement_match':'REQUIRES_INDEPENDENT_REVIEW','evidence_files':[],
        'reproduction_command':['research.cmd','candidate','verify','<project>','--request','<frozen-request-file>'],
        'limitations':list(LIMITATIONS)}


def _failure(request,reason):
    return {**_base(request),'reason':reason,'automatic_retry_allowed':False}


def _read(project,rid):
    paths=_paths(project,rid)
    if not paths['request'].is_file(): raise ValueError('Frozen verifier request is missing; never reconstruct it from live sources')
    request=configuration.load_json(paths['request']); _request_valid(request)
    if request['request_id']!=rid: raise ValueError('Verifier request identity/path mismatch')
    if not paths['started'].is_file(): raise ValueError('Verifier dispatch fence is missing; explicit audit required')
    started=configuration.load_json(paths['started'])
    if (not isinstance(started,dict) or set(started)!={'schema_version','request_id','request_sha256','phase','at','sha256'}
            or type(started['schema_version']) is not int or started['schema_version']!=1 or started['phase']!='STARTED'
            or started['request_id']!=rid or started['request_sha256']!=object_hash(request)
            or started['sha256']!=object_hash({k:v for k,v in started.items() if k!='sha256'})):
        raise ValueError('Verifier dispatch fence changed; explicit audit required')
    if not paths['receipt'].is_file(): return request,None
    receipt=configuration.load_json(paths['receipt'])
    if (not isinstance(receipt,dict) or receipt.get('request_id')!=rid
            or receipt.get('request_sha256')!=object_hash(request)
            or receipt.get('started_sha256')!=started['sha256'] or receipt.get('result_status') not in STATUSES
            or receipt.get('scientific_acceptance') is not False or receipt.get('positive_basis') is not False
            or receipt.get('claim_binding')!=request['claim_binding'] or receipt.get('source_hashes')!=request['source_hashes']
            or receipt.get('adapter_id')!=request['adapter_id'] or receipt.get('tool_bindings')!=request['tool_bindings']
            or receipt.get('statement_match')!='REQUIRES_INDEPENDENT_REVIEW'
            or (request['adapter_id']=='lean-v1' and (receipt.get('result_status') not in {'UNSUPPORTED','FAILED'}
                                                     or receipt.get('execution_started') is not False))
            or (request['adapter_id']=='integer-v1' and receipt.get('result_status') not in {
                'COUNTEREXAMPLE_FOUND','NO_COUNTEREXAMPLE_WITHIN_BOUND','FAILED','UNSUPPORTED'})
            or receipt.get('receipt_sha256')!=object_hash({k:v for k,v in receipt.items() if k!='receipt_sha256'})):
        raise ValueError('Verifier receipt integrity changed; preserve it and audit')
    return request,receipt


@contextlib.contextmanager
def _locks(project,locks_held):
    _,key=catalog._project(project)
    with contextlib.ExitStack() as stack:
        if not locks_held:
            for name in ('route-'+key+'.lock',key+'.lock'):
                stack.enter_context(file_lock(catalog._unlinked(configuration.ROOT/'locks'/name)))
        for name in ('candidates-'+key+'.lock','candidate-verifier-'+key+'.lock'):
            stack.enter_context(file_lock(catalog._unlinked(configuration.ROOT/'locks'/name)))
        yield


def verify(project,request,*,locks_held=False):
    if not isinstance(request,dict): raise ValueError('Verifier request must be an object')
    good,reason=_fresh(project,request)
    if not good: return _failure(request,'STALE_OR_INVALID_VERIFICATION_REQUEST: '+str(reason))
    with _locks(project,locks_held):
        good,reason=_fresh(project,request)
        if not good: return _failure(request,'STALE_OR_INVALID_VERIFICATION_REQUEST: '+str(reason))
        paths=_paths(project,request['request_id'])
        if any(path.exists() for path in paths.values()):
            try: old,receipt=_read(project,request['request_id'])
            except ValueError as exc: return _failure(request,'UNKNOWN_LOCAL_VERIFICATION_OUTCOME: '+str(exc))
            if old!=request: return _failure(request,'VERIFICATION_REQUEST_ID_CONFLICT')
            return receipt if receipt is not None else _failure(request,'UNKNOWN_LOCAL_VERIFICATION_OUTCOME: dispatch fence has no complete receipt; no automatic retry')
        configuration.atomic_json(paths['request'],request)
        started={'schema_version':1,'request_id':request['request_id'],'request_sha256':object_hash(request),'phase':'STARTED','at':stamp()}
        started['sha256']=object_hash(started); configuration.atomic_json(paths['started'],started)
        receipt=_base(request)
        try:
            if request['adapter_id']=='integer-v1':
                from . import integer_adapter
                if request['statement'] is None:
                    result={'result_status':'UNSUPPORTED','reason':'Claim has no registered exact-integer machine predicate'}
                else:
                    falsification.validate_statement(request['statement'])
                    result=integer_adapter.execute(request)
                    if result.get('result_status') not in {'COUNTEREXAMPLE_FOUND','NO_COUNTEREXAMPLE_WITHIN_BOUND','FAILED'}:
                        raise ValueError('Integer adapter cannot issue a proof or an unsupported positive tool status')
                    if result.get('result_status')=='COUNTEREXAMPLE_FOUND':
                        witness=result['result']['witness']['assignment']
                        if any(not request['options']['low']<=value<=request['options']['high'] for value in witness.values()):
                            raise ValueError('Returned worker witness is outside its frozen search bounds')
                        if not falsification.check_witness(request['statement'],witness)['is_counterexample']:
                            raise ValueError('Returned worker witness is not an exact counterexample')
                        result['certificate']={'statement_sha256':object_hash(request['statement']),
                            'assignment':copy.deepcopy(witness),'evaluation':falsification.check_witness(request['statement'],witness),
                            'scope':'FROZEN_MACHINE_PREDICATE_ONLY','candidate_statement_correspondence':'REQUIRES_INDEPENDENT_REVIEW'}
                receipt.update(result)
            elif request['adapter_id']=='lean-v1':
                from . import lean_adapter
                receipt.update(lean_adapter.execute(project,request))
            else: receipt.update(result_status='UNSUPPORTED',reason='Unknown verifier adapter; no process was launched')
        except Exception as exc:
            receipt.update(result_status='FAILED',reason=type(exc).__name__+': '+str(exc))
        good,reason=_fresh(project,request)
        if not good: receipt.update(result_status='FAILED',reason='STALE_AFTER_VERIFICATION: '+str(reason))
        receipt['scientific_acceptance']=False; receipt['positive_basis']=False
        receipt['evidence_files']=[{'scope':'CONTROLLER','path':path.relative_to(configuration.ROOT).as_posix(),'sha256':hash_file(path)}
                                   for kind,path in paths.items() if kind!='receipt']
        receipt['reproduction_command']=['research.cmd','candidate','verify',configuration.project_id(project),
            '--request',str(paths['request'].resolve())]
        receipt.update(started_sha256=started['sha256'],completed_at=stamp(),automatic_retry_allowed=False)
        receipt['receipt_sha256']=object_hash(receipt)
        configuration.atomic_json(paths['receipt'],receipt)
        return receipt


def show(project,request_id):
    request,receipt=_read(project,request_id)
    if receipt is None: return _failure(request,'UNKNOWN_LOCAL_VERIFICATION_OUTCOME: no complete receipt')
    good,reason=_fresh(project,request)
    return {**receipt,'fresh':good,'freshness_reason':reason}


def recheck(project,request_id):
    request,receipt=_read(project,request_id)
    if receipt is None: return {**_failure(request,'UNKNOWN_LOCAL_VERIFICATION_OUTCOME: never rerun an interrupted check'),
                                'fresh':False,'certificate_valid':False}
    good,reason=_fresh(project,request); valid=False
    if good and receipt['result_status']=='COUNTEREXAMPLE_FOUND':
        try:
            witness=receipt['result']['witness']['assignment']
            certificate=receipt.get('certificate',{})
            valid=(falsification.check_witness(request['statement'],witness)['is_counterexample']
                and certificate.get('statement_sha256')==object_hash(request['statement'])
                and certificate.get('assignment')==witness
                and all(request['options']['low']<=v<=request['options']['high'] for v in witness.values()))
        except (KeyError,ValueError,TypeError): valid=False
    result={**receipt,'fresh':good,'freshness_reason':reason,'certificate_valid':valid,
            'certificate_scope':'EXACT_FROZEN_MACHINE_PREDICATE_ONLY' if valid else 'NO_POSITIVE_PROOF_CERTIFICATE',
            'recheck_execution_started':False}
    if not good: result.update(result_status='FAILED',reason='STALE_VERIFICATION_RECEIPT: '+str(reason))
    elif receipt['result_status']=='COUNTEREXAMPLE_FOUND' and not valid:
        result.update(result_status='FAILED',reason='Exact counterexample certificate did not revalidate')
    return result
