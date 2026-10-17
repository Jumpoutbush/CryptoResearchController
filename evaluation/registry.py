"""Append-only evaluator-private curation, outside public/controller workspaces."""
from __future__ import annotations
import copy
import hashlib
from pathlib import Path
import configuration
from route_budget import file_lock, stamp
from . import cases, schema


def _private(private_root,root=None):
    target=Path(private_root)
    public=schema.root_path(root).resolve(); absolute=target.resolve()
    if absolute.is_relative_to(schema.CONTROLLER.resolve()) or absolute.is_relative_to(public) or public.is_relative_to(absolute):
        raise ValueError('Evaluator-private curation must be outside the controller and public workspace')
    schema.safe(target,'registry.json'); return target


def _record_name(case_id,version): schema.identity(case_id,version); return 'records/'+case_id+'-v'+str(version)+'.json'
def _oracle_name(case_id,version): return 'oracles/'+case_id+'/v'+str(version)+'/oracle.json'


def _load(base):
    location=schema.safe(base,'registry.json'); value=schema.read(location) if location.exists() else None
    records=schema.safe(base,'records'); files=list(records.glob('*.json')) if records.exists() else []
    oracle_dir=schema.safe(base,'oracles')
    oracle_files=list(oracle_dir.rglob('oracle.json')) if oracle_dir.exists() else []
    actual_oracles=set()
    for oracle in oracle_files:
        relative=oracle.relative_to(base).as_posix(); schema.safe(base,relative); actual_oracles.add(relative)
    if value is None:
        if files or oracle_files: raise ValueError('Evaluator registry lost while immutable revision records or orphaned private files remain')
        return {'schema_version':1,'entries':[]}
    if not isinstance(value,dict) or set(value)!={'schema_version','entries'} or type(value['schema_version']) is not int or value['schema_version']!=1:
        raise ValueError('Invalid evaluator-private registry')
    previous=None; seen=set(); expected_files=set(); expected_oracles=set()
    for number,entry in enumerate(value['entries'],1):
        required={'sequence','previous_sha256','case_id','version','category','task_sha256','input_sha256','oracle_sha256',
            'oracle_file','evaluator_version','evaluator_sha256','source_bindings','reviewer','reason','registered_at','sha256'}
        if (not isinstance(entry,dict) or set(entry)!=required or type(entry['sequence']) is not int or entry['sequence']!=number
                or entry['previous_sha256']!=previous or entry['sha256']!=schema.digest({k:v for k,v in entry.items() if k!='sha256'})):
            raise ValueError('Evaluator revision history changed')
        schema.identity(entry['case_id'],entry['version']); identity=(entry['case_id'],entry['version'])
        if identity in seen or entry['oracle_file']!=_oracle_name(*identity): raise ValueError('Duplicate or misbound private oracle revision')
        seen.add(identity); previous=entry['sha256']; record_file=_record_name(*identity); expected_files.add(Path(record_file).name)
        expected_oracles.add(entry['oracle_file'])
        if schema.read(schema.safe(base,record_file))!=entry: raise ValueError('Immutable evaluator revision record changed or disappeared')
        if schema.sha_file(schema.safe(base,entry['oracle_file']))!=entry['oracle_sha256']: raise ValueError('Frozen private oracle changed')
    if {f.name for f in files}!=expected_files: raise ValueError('Evaluator revision history was truncated or orphaned')
    if actual_oracles!=expected_oracles: raise ValueError('Evaluator private-file history was truncated or orphaned; preserve it for audit')
    return value


def register(private_root,case_id,oracle,*,reviewer,reason,version=None,root=None):
    base=_private(private_root,root); schema.text(reviewer,'reviewer'); schema.text(reason,'curation reason')
    if len(reason.strip())<32: raise ValueError('Independent curation needs a substantive recorded reason')
    view=cases.public_view(case_id,version,root); task=view['task']; binding=view['public_binding']
    if reviewer.strip().casefold()==task['author'].strip().casefold(): raise ValueError('Curation reviewer must be independent of the task author')
    from .scoring import validate_oracle
    validate_oracle(task,oracle)
    document={'schema_version':1,'case_id':case_id,'version':task['version'],'input_sha256':task['input_sha256'],
        'task_sha256':binding['task_sha256'],'evaluator_version':binding['evaluator_version'],'evaluator_sha256':binding['evaluator_sha256'],
        'source_bindings':schema.source_bindings(task),'oracle':copy.deepcopy(oracle)}
    raw=schema.canonical_bytes(document)
    import hashlib
    oracle_sha=hashlib.sha256(raw).hexdigest()
    base.mkdir(parents=True,exist_ok=True)
    with file_lock(schema.safe(base,'registry.lock')):
        value=_load(base); matching=[r for r in value['entries'] if r['case_id']==case_id and r['version']==task['version']]
        if matching:
            existing=matching[0]
            if (existing['oracle_sha256']!=oracle_sha or existing['reviewer']!=reviewer or existing['reason']!=reason):
                raise ValueError('A frozen oracle cannot be replaced; publish a new task version and curation record')
            return {'status':'ALREADY_REGISTERED','entry':copy.deepcopy(existing),'formal_counted':False}
        versions=[r['version'] for r in value['entries'] if r['case_id']==case_id]
        if versions and task['version']<=max(versions): raise ValueError('Case curation revisions must advance monotonically')
        entry={'sequence':len(value['entries'])+1,'previous_sha256':value['entries'][-1]['sha256'] if value['entries'] else None,
            'case_id':case_id,'version':task['version'],'category':task['category'],'task_sha256':binding['task_sha256'],
            'input_sha256':task['input_sha256'],'oracle_sha256':oracle_sha,'oracle_file':_oracle_name(case_id,task['version']),
            'evaluator_version':binding['evaluator_version'],'evaluator_sha256':binding['evaluator_sha256'],
            'source_bindings':schema.source_bindings(task),'reviewer':reviewer,'reason':reason,'registered_at':stamp()}
        entry['sha256']=schema.digest(entry)
        for relative,payload in ((entry['oracle_file'],raw),(_record_name(case_id,task['version']),schema.canonical_bytes(entry))):
            location=schema.safe(base,relative); location.parent.mkdir(parents=True,exist_ok=True)
            with location.open('xb') as out: out.write(payload)
        value['entries'].append(entry); configuration.atomic_json(schema.safe(base,'registry.json'),value)
        return {'status':'REGISTERED_PRIVATE_CALIBRATION','entry':copy.deepcopy(entry),'formal_counted':False}


def get(private_root,case_id,*,version=None,root=None):
    base=_private(private_root,root); view=cases.public_view(case_id,version,root); binding=view['public_binding']; task=view['task']
    entries=[r for r in _load(base)['entries'] if r['case_id']==case_id and r['version']==task['version']]
    if not entries: raise ValueError('Case has no evaluator-private independent curation')
    entry=entries[0]
    if (any(entry[k]!=binding[k] for k in ('task_sha256','input_sha256','evaluator_version','evaluator_sha256'))
            or entry['source_bindings']!=schema.source_bindings(task)): raise ValueError('Historical evaluator or public source binding is stale')
    raw=schema.safe(base,entry['oracle_file']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=entry['oracle_sha256']: raise ValueError('Private oracle changed during exact read')
    document=schema.decode(raw)
    expected={k:entry[k] for k in ('case_id','version','task_sha256','input_sha256','evaluator_version','evaluator_sha256','source_bindings')}
    if (not isinstance(document,dict) or set(document)!={'schema_version',*expected,'oracle'}
            or type(document['schema_version']) is not int or document['schema_version']!=1
            or any(document[k]!=v for k,v in expected.items())): raise ValueError('Private oracle envelope is misbound')
    return copy.deepcopy(entry),document


def history(private_root,case_id=None,*,root=None):
    entries=_load(_private(private_root,root))['entries']
    return {'entries':[copy.deepcopy(e) for e in entries if case_id is None or e['case_id']==case_id],'formal_counted':False}


def diff(private_root,case_id,from_version,to_version,*,root=None):
    entries=history(private_root,case_id,root=root)['entries']
    first=next((e for e in entries if e['version']==from_version),None); last=next((e for e in entries if e['version']==to_version),None)
    if first is None or last is None: raise ValueError('Both historical curation revisions are required')
    return {'case_id':case_id,'from_version':from_version,'to_version':to_version,
        'changed_fields':sorted(key for key in first if first[key]!=last[key]),
        'responsibility':{'before':{'reviewer':first['reviewer'],'reason':first['reason']},'after':{'reviewer':last['reviewer'],'reason':last['reason']}},
        'formal_counted':False}
