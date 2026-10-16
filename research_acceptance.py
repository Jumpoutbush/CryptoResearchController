"""Durable wrapper acceptance decisions; all recovery precedes a new model call.

The journal is controller authority, not a rebuildable knowledge cache. Unknown
precommit executions and interrupted local checks stop for audit, never redispatch.
"""
from __future__ import annotations
import copy
import hashlib
import json
import re
from pathlib import Path

from configuration import atomic_json
from route_budget import project_key, read_json, stamp


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def path_for(controller, project):
    return Path(controller)/'state/research_acceptance'/(project_key(project)+'.json')


def manifest(project):
    from runner_core import project_files, digest_file
    return {p.relative_to(project).as_posix():digest_file(p) for p in project_files(project)}


def load(controller, project):
    path=path_for(controller,project)
    if not path.exists(): return None
    obj=read_json(path)
    payload={k:v for k,v in obj.items() if k!='journal_sha256'}
    if (obj.get('schema_version')!=1 or obj.get('project_id')!=project_key(project)
            or obj.get('journal_sha256')!=digest(payload)
            or obj.get('phase') not in {'STARTED','ABORTED','COMMIT_DECIDED','COMPLETE'}
            or not re.fullmatch('[0-9a-f]{32}',str(obj.get('transaction_id','')))
            or obj.get('route_path')!='state/routes/'+project_key(project)+'.json'):
        raise ValueError('ACCEPTANCE_JOURNAL_CORRUPT: preserve it and audit; no new research')
    return obj


def write(controller, project, obj):
    obj['journal_sha256']=digest({k:v for k,v in obj.items() if k!='journal_sha256'})
    atomic_json(path_for(controller,project),obj)


def begin(controller, project, transaction, ledger_path, ledger):
    old=load(controller,project)
    if old and old['phase']=='COMPLETE': archive_complete(controller,project,old)
    if old and old['phase'] not in {'COMPLETE','ABORTED'}:
        raise ValueError('ACCEPTANCE_PENDING: recover the original run before dispatch')
    obj={'schema_version':1,'project_id':project_key(project),'transaction_id':transaction.label,
         'phase':'STARTED','created_at':stamp(),'before_manifest':manifest(project),
         'snapshot_before':copy.deepcopy(transaction.manifest),'route_before':copy.deepcopy(ledger),
         'route_path':Path(ledger_path).relative_to(controller).as_posix(),
         'steps':{},'step_active':None}
    write(controller,project,obj)
    fault_hook('STARTED')
    return obj


def commit(controller, project, obj, ledger, run_id, outcome, *, initialization, reviewed):
    from engine.common import ledger as discovery_ledger
    owners=[(a['id'],c) for a in discovery_ledger(project)['attempts']
            for c in a['calls'] if c['run_id']==run_id]
    if len(owners)>1: raise ValueError('DISCOVERY_ACCEPTANCE_OWNER_AMBIGUOUS')
    obj.update(phase='COMMIT_DECIDED',run_id=run_id,outcome=outcome,
               route_after=copy.deepcopy(ledger),expected_manifest=manifest(project),
               initialization=initialization,reviewed=reviewed,committed_at=stamp(),
               discovery_owner_attempt_id=owners[0][0] if owners else None,
               discovery_call_before=copy.deepcopy(owners[0][1]) if owners else None)
    # The durable decision is the sole commit point. Callers must reread it if
    # an exception follows os.replace but precedes this function's return.
    write(controller,project,obj)
    fault_hook('COMMIT_DECIDED')


def committed(controller, project, transaction_id):
    obj=load(controller,project)
    return bool(obj and obj['transaction_id']==transaction_id and obj['phase'] in {'COMMIT_DECIDED','COMPLETE'})


def abort(controller, project, obj, reason):
    obj.update(phase='ABORTED',failure=str(reason),finished_at=stamp())
    write(controller,project,obj)


def fault_hook(stage):
    """An inert injection seam for isolated subprocess crash tests."""


def verify_project(project, obj):
    if manifest(project)!=obj['expected_manifest']:
        raise ValueError('ACCEPTANCE_PROJECT_CHANGED: retain accepted evidence and audit the interrupted step; no model retry')


def step(controller, project, obj, name, function):
    if name in obj['steps']: return obj['steps'][name]
    verify_project(project,obj)
    obj['step_active']=name
    write(controller,project,obj)
    result=function()
    obj['steps'][name]=result
    obj.update(step_active=None,expected_manifest=manifest(project))
    write(controller,project,obj)
    fault_hook(name.upper()+'_COMPLETE')
    return result


def finish(controller, project, obj):
    # Persist the completion timestamp while retaining the pending decision.
    # Archive first, then mark latest complete. Either crash window is replayable.
    if 'finished_at' not in obj:
        obj['finished_at']=stamp()
        write(controller,project,obj)
    complete=copy.deepcopy(obj); complete['phase']='COMPLETE'
    complete['journal_sha256']=digest({k:v for k,v in complete.items() if k!='journal_sha256'})
    archive_complete(controller,project,complete)
    write(controller,project,complete)
    obj.clear(); obj.update(complete)


def archive_complete(controller, project, obj):
    archive=path_for(controller,project).parent/project_key(project)/(obj['transaction_id']+'.json')
    if archive.exists() and read_json(archive)!=obj:
        raise ValueError('ACCEPTANCE_HISTORY_CONFLICT')
    if not archive.exists(): atomic_json(archive,obj)
