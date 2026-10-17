"""Independent high-water authority for the existing discovery call ledger.

This records original bytes and pending local afterimages; it is not another
budget. Reads never enroll, repair, settle checks, or dispatch research.
"""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import re
import uuid

import configuration
from route_budget import file_lock, stamp
from .common import identifier, object_hash


def _safe(path):
    path=Path(path)
    path.relative_to(configuration.ROOT)
    from runner_core import project_link
    for part in (path,*path.parents):
        if part.exists() and project_link(part): raise ValueError('DISCOVERY_AUTHORITY_LINKED: authority must not traverse links')
        if part==configuration.ROOT: break
    return path


def _key(project): return identifier(configuration.project_id(project))
def path(project): return _safe(configuration.ROOT/'state/discovery'/(_key(project)+'.json'))
def registry_path(project): return _safe(configuration.ROOT/'state/discovery_registry'/(_key(project)+'.json'))
def registration_path(project): return _safe(configuration.ROOT/'state/discovery_registration'/(_key(project)+'.json'))
def _lock(project): return file_lock(_safe(configuration.ROOT/'locks'/('discovery-authority-'+_key(project)+'.lock')))
def _sha(raw): return hashlib.sha256(raw).hexdigest()
def _file_sha(location): return _sha(location.read_bytes()) if location.is_file() else None
def _bytes(value): return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf8')
def _hex(value): return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) is not None
def _empty(): return {'schema_version':1,'active_attempt':None,'attempts':[]}


def _validate(value):
    try:
        if (not isinstance(value,dict) or type(value.get('schema_version')) is not int or value['schema_version']!=1
                or not isinstance(value.get('attempts'),list) or 'active_attempt' not in value):
            raise ValueError('DISCOVERY_AUTHORITY_INVALID: incomplete ledger')
        owners=set(); runs=set()
        for attempt in value['attempts']:
            aid=identifier(attempt['id'])
            if aid in owners or not isinstance(attempt['calls'],list): raise ValueError('DISCOVERY_AUTHORITY_INVALID: duplicate owner')
            owners.add(aid)
            for key in ('budget','extensions','stagnation'):
                if type(attempt[key]) is not int or attempt[key]<(1 if key=='budget' else 0):
                    raise ValueError('DISCOVERY_AUTHORITY_INVALID: original consumption or budget')
            if not isinstance(attempt.get('status'),str) or not attempt['status']: raise ValueError('Invalid original attempt status')
            for call in attempt['calls']:
                run=identifier(call['run_id'])
                if run in runs or call['status'] not in {'RESERVED','PENDING_WRAPPER','SETTLING','SETTLEMENT_READY','ACCEPTED','FAILED'}:
                    raise ValueError('DISCOVERY_AUTHORITY_INVALID: duplicate run or unknown call phase')
                runs.add(run)
        if value['active_attempt'] is not None and value['active_attempt'] not in owners:
            raise ValueError('DISCOVERY_AUTHORITY_INVALID: active original owner missing')
    except (KeyError,TypeError,AttributeError) as exc: raise ValueError('DISCOVERY_AUTHORITY_INVALID: incomplete original ledger') from exc
    return value


def _read(location): return configuration.load_json(_safe(location))


def _pair(project):
    registration=_read(registration_path(project)); registry=_read(registry_path(project))
    if registration is None and registry is None: return None
    try:
        if registration is None or registry is None: raise ValueError('DISCOVERY_AUTHORITY_WITNESS_MISSING: preserve and restore the original pair')
        if (set(registration)!={'schema_version','project_id','authority_id','registered_at','reason','initial_ledger_sha256','sha256'}
                or type(registration['schema_version']) is not int or registration['schema_version']!=1
                or registration['project_id']!=_key(project) or not _hex(registration['authority_id'])
                or registration['sha256']!=object_hash({k:v for k,v in registration.items() if k!='sha256'})
                or not (registration['initial_ledger_sha256'] is None or _hex(registration['initial_ledger_sha256']))):
            raise ValueError('DISCOVERY_AUTHORITY_INVALID: registration witness changed')
        if (set(registry)!={'schema_version','project_id','authority_id','registration_sha256','committed','pending','sha256'}
                or type(registry['schema_version']) is not int or registry['schema_version']!=1
                or registry['project_id']!=_key(project) or registry['authority_id']!=registration['authority_id']
                or registry['registration_sha256']!=registration['sha256']
                or registry['sha256']!=object_hash({k:v for k,v in registry.items() if k!='sha256'})):
            raise ValueError('DISCOVERY_AUTHORITY_INVALID: high-water witness changed')
        committed=registry['committed']; pending=registry['pending']
        if committed is not None and (set(committed)!={'sequence','ledger_sha256'} or type(committed['sequence']) is not int
                or committed['sequence']<1 or not _hex(committed['ledger_sha256'])):
            raise ValueError('DISCOVERY_AUTHORITY_INVALID: committed high-water')
        if pending is not None:
            if (set(pending)!={'operation_id','sequence','from_sha256','to_sha256','afterimage','prepared_at'}
                    or not isinstance(pending['operation_id'],str) or not re.fullmatch('[0-9a-f]{32}',pending['operation_id'])
                    or type(pending['sequence']) is not int or pending['sequence']!=(committed['sequence']+1 if committed else 1)
                    or not (pending['from_sha256'] is None or _hex(pending['from_sha256']))
                    or (committed is not None and pending['from_sha256']!=committed['ledger_sha256'])
                    or pending['to_sha256']!=_sha(_bytes(_validate(pending['afterimage'])))):
                raise ValueError('DISCOVERY_AUTHORITY_INVALID: pending afterimage changed')
        elif committed is None: raise ValueError('DISCOVERY_AUTHORITY_INVALID: no committed or prepared authority')
    except (KeyError,TypeError,AttributeError) as exc: raise ValueError('DISCOVERY_AUTHORITY_INVALID: malformed witness pair') from exc
    return registry


def _write_registry(project,value):
    value['sha256']=object_hash({k:v for k,v in value.items() if k!='sha256'})
    configuration.atomic_json(registry_path(project),value)


def _new_registration(project,reason,initial):
    registration={'schema_version':1,'project_id':_key(project),'authority_id':object_hash({'project_id':_key(project),'nonce':uuid.uuid4().hex}),
                  'registered_at':stamp(),'reason':reason,'initial_ledger_sha256':initial}
    registration['sha256']=object_hash(registration); configuration.atomic_json(registration_path(project),registration)
    return {'schema_version':1,'project_id':_key(project),'authority_id':registration['authority_id'],
            'registration_sha256':registration['sha256'],'committed':None,'pending':None}


def _scan_witnesses(project,value):
    """Original independent run witnesses cannot be forgotten by a legacy image."""
    owners={a['id']:a for a in value['attempts']}
    def require(aid,rid):
        owner=owners.get(aid)
        call=next((c for c in owner['calls'] if c['run_id']==rid),None) if owner else None
        if call is None: raise ValueError('DISCOVERY_AUTHORITY_FORGOTTEN_RUN: original witness retains '+str(aid)+'/'+str(rid))
        return call
    base=_safe(configuration.ROOT/'state/discovery/settlements'/_key(project))
    if base.exists():
        for location in base.rglob('*.json'):
            record=_read(location); aid=location.parent.name
            rid=location.name[:-13] if location.name.endswith('.started.json') else location.stem
            identifier(aid); identifier(rid)
            if (not isinstance(record,dict) or type(record.get('schema_version')) is not int or record['schema_version']!=1
                    or record.get('project_id')!=_key(project) or record.get('attempt_id')!=aid or record.get('run_id')!=rid):
                raise ValueError('DISCOVERY_AUTHORITY_WITNESS_INVALID: original settlement identity changed')
            call=require(aid,rid)
            if call['status'] not in {'SETTLING','SETTLEMENT_READY','ACCEPTED','FAILED'}:
                raise ValueError('DISCOVERY_AUTHORITY_FORGOTTEN_PHASE: started original check may have unknown outcome')
            if location.name.endswith('.started.json'):
                if record.get('phase')!='SETTLING' or not _hex(record.get('attempt_sha256')):
                    raise ValueError('DISCOVERY_AUTHORITY_WITNESS_INVALID: malformed original started record')
                if call['status'] in {'ACCEPTED','FAILED'} and not _safe(location.with_name(rid+'.json')).is_file():
                    raise ValueError('UNKNOWN_LOCAL_CHECK_OUTCOME: completed original settlement receipt missing for '+rid)
            else:
                # The original pure reader verifies both independently written
                # records and their exact before/after/project bindings.
                _safe(location.with_suffix('.started.json'))
                from .discovery_scheduler import _read_settlement
                record=_read_settlement(project,aid,rid)
                if call['status'] in {'ACCEPTED','FAILED'}:
                    expected=next((c for c in record['after_attempt']['calls'] if c['run_id']==rid),None)
                    if ({k:v for k,v in call.items() if k!='settlement_receipt_sha256'}!=expected
                            or call.get('settlement_receipt_sha256')!=record['receipt_sha256']):
                        raise ValueError('DISCOVERY_AUTHORITY_WITNESS_INVALID: terminal original call differs from its receipt')
    checkpoints=_safe(configuration.ROOT/'state/discovery/checkpoints'/_key(project))
    if checkpoints.exists():
        for location in checkpoints.rglob('*.json'):
            record=_read(location)
            if not isinstance(record,dict) or record.get('attempt_id')!=location.parent.name or record.get('run_id')!=location.stem:
                raise ValueError('DISCOVERY_AUTHORITY_WITNESS_INVALID: original checkpoint identity changed')
            require(record['attempt_id'],record['run_id'])
    acceptance=_safe(configuration.ROOT/'state/research_acceptance'/(_key(project)+'.json'))
    archive=_safe(configuration.ROOT/'state/research_acceptance'/_key(project))
    journals=([acceptance] if acceptance.is_file() else [])+ (list(archive.glob('*.json')) if archive.exists() else [])
    for location in journals:
        record=_read(location)
        if not isinstance(record,dict): raise ValueError('DISCOVERY_AUTHORITY_WITNESS_INVALID: malformed original acceptance')
        aid=record.get('discovery_owner_attempt_id')
        if aid is None: continue
        if (record.get('project_id')!=_key(project) or record.get('journal_sha256')!=object_hash({k:v for k,v in record.items() if k!='journal_sha256'})):
            raise ValueError('DISCOVERY_AUTHORITY_WITNESS_INVALID: original acceptance identity or digest changed')
        require(aid,record.get('run_id'))


def load(project):
    registry=_pair(project); location=path(project); value=_read(location)
    if registry is None:
        if value is not None:
            _validate(value); _scan_witnesses(project,value)
            raise ValueError('DISCOVERY_LEGACY_ENROLLMENT_REQUIRED: explicitly enroll the complete original ledger; no zero migration')
        value=_empty(); _scan_witnesses(project,value); return value
    if registry['pending'] is not None: raise ValueError('DISCOVERY_AUTHORITY_RECOVERY_REQUIRED: explicitly recover the frozen local afterimage')
    if value is None: raise ValueError('DISCOVERY_AUTHORITY_MISSING: restore the exact latest witnessed ledger; no new attempt')
    _validate(value)
    if _file_sha(location)!=registry['committed']['ledger_sha256']:
        raise ValueError('DISCOVERY_AUTHORITY_STALE: ledger differs from latest committed SHA; no consumption reset')
    _scan_witnesses(project,value); return value


def _no_regression(before,after):
    old=before['attempts']; new=after['attempts']
    if len(new)<len(old): raise ValueError('DISCOVERY_AUTHORITY_REGRESSION: historical attempts cannot be removed')
    for index,owner in enumerate(old):
        target=new[index]
        if any(target.get(k)!=owner.get(k) for k in ('id','problem_id','problem_version','problem_sha256','binding','created_at','policy_snapshot')):
            raise ValueError('DISCOVERY_AUTHORITY_REGRESSION: original owner identity cannot be rewritten')
        # Tightening a call limit does not erase consumption. Keep every call
        # and extension; the original check blocks at len(calls) >= budget.
        if target['extensions']<owner['extensions'] or len(target['calls'])<len(owner['calls']):
            raise ValueError('DISCOVERY_AUTHORITY_REGRESSION: original consumed calls or extensions cannot be discarded')
        for number,call in enumerate(owner['calls']):
            updated=target['calls'][number]
            if any(updated.get(k)!=call.get(k) for k in ('run_id','started_at','mode')):
                raise ValueError('DISCOVERY_AUTHORITY_REGRESSION: original run identity cannot be replaced')
            if call['status'] in {'ACCEPTED','FAILED'} and updated!=call:
                raise ValueError('DISCOVERY_AUTHORITY_REGRESSION: completed original call cannot be downgraded or rewritten')


def save(project,value):
    value=copy.deepcopy(_validate(value))
    with _lock(project):
        registry=_pair(project); location=path(project)
        if registry is None:
            if location.exists(): raise ValueError('DISCOVERY_LEGACY_ENROLLMENT_REQUIRED: enroll original authority before writing')
            _scan_witnesses(project,_empty())
            if len(value['attempts'])!=1 or value['attempts'][0]['id']!='attempt-0001' or value['attempts'][0]['calls']:
                raise ValueError('DISCOVERY_EXPLICIT_ENROLLMENT_REQUIRED: only the first original empty attempt may create new authority')
            registry=_new_registration(project,'First original attempt on a new unregistered project',None)
        else:
            current=load(project); _no_regression(current,value)
            if _file_sha(location)==_sha(_bytes(value)): return
        _scan_witnesses(project,value)
        registry['pending']={'operation_id':uuid.uuid4().hex,'sequence':registry['committed']['sequence']+1 if registry['committed'] else 1,
            'from_sha256':_file_sha(location),'to_sha256':_sha(_bytes(value)),'afterimage':value,'prepared_at':stamp()}
        _write_registry(project,registry); _complete_pending(project,registry)


def _complete_pending(project,registry):
    pending=registry['pending']; location=path(project); actual=_file_sha(location)
    if actual not in {pending['from_sha256'],pending['to_sha256']}:
        raise ValueError('DISCOVERY_AUTHORITY_CONFLICT: a third ledger version must not be overwritten')
    _scan_witnesses(project,pending['afterimage'])
    if actual!=pending['to_sha256']: configuration.atomic_json(location,pending['afterimage'])
    if _file_sha(location)!=pending['to_sha256']: raise ValueError('DISCOVERY_AUTHORITY_AFTERIMAGE_MISMATCH')
    registry['committed']={'sequence':pending['sequence'],'ledger_sha256':pending['to_sha256']}; registry['pending']=None
    _write_registry(project,registry)


def enroll(project,reason,*,expected_ledger_sha256):
    if not isinstance(reason,str) or len(reason.strip())<12: raise ValueError('Explicit authority enrollment reason must have at least 12 characters')
    with _lock(project):
        if _pair(project) is not None: raise ValueError('Discovery authority is already registered; enrollment cannot reset it')
        location=path(project); actual=_file_sha(location)
        if not _hex(expected_ledger_sha256) or actual!=expected_ledger_sha256: raise ValueError('DISCOVERY_ENROLLMENT_CAS: original ledger SHA changed')
        value=_validate(_read(location)); _scan_witnesses(project,value)
        if not value['attempts']: raise ValueError('DISCOVERY_EMPTY_LEGACY_AUTHORITY: cannot confirm historical zero consumption')
        registry=_new_registration(project,reason,actual)
        registry['committed']={'sequence':1,'ledger_sha256':actual}; _write_registry(project,registry)
        return status(project)


def recover(project,reason,*,expected_afterimage_sha256):
    if not isinstance(reason,str) or len(reason.strip())<12: raise ValueError('Explicit authority recovery reason must have at least 12 characters')
    with _lock(project):
        registry=_pair(project)
        if registry is None: raise ValueError('No frozen discovery afterimage exists; do not reconstruct consumed calls')
        if registry['pending'] is None:
            load(project)
            if registry['committed']['ledger_sha256']!=expected_afterimage_sha256: raise ValueError('DISCOVERY_RECOVERY_CAS: completed afterimage differs')
            return {'status':'ALREADY_COMMITTED','ledger_sha256':expected_afterimage_sha256,'model_execution_started':False}
        if registry['pending']['to_sha256']!=expected_afterimage_sha256: raise ValueError('DISCOVERY_RECOVERY_CAS: frozen afterimage differs')
        _complete_pending(project,registry)
        return {'status':'RECOVERED_LOCAL_AFTERIMAGE','ledger_sha256':expected_afterimage_sha256,'model_execution_started':False}


def status(project):
    location=path(project); actual=_file_sha(location)
    result={'project_id':_key(project),'actual_ledger_sha256':actual,'pending_afterimage_sha256':None,
            'model_execution_started':False,'automatic_retry_allowed':False}
    try:
        registry=_pair(project); value=_read(location)
        if registry is None:
            if value is None: _scan_witnesses(project,_empty()); result['status']='NEW_UNENROLLED'
            else: _validate(value); _scan_witnesses(project,value); result['status']='LEGACY_ENROLLMENT_REQUIRED'
        else:
            result['committed']=copy.deepcopy(registry['committed'])
            if registry['pending'] is not None:
                result.update(status='RECOVERY_REQUIRED',pending_afterimage_sha256=registry['pending']['to_sha256'])
            else: load(project); result['status']='COMMITTED'
        if value is not None:
            _validate(value); result.update(attempts=len(value['attempts']),calls=sum(len(a['calls']) for a in value['attempts']))
    except (ValueError,OSError,TypeError,KeyError) as exc: result.update(status='FAILED',reason=str(exc))
    return result
