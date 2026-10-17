"""Read public tasks and export an allowlisted agent bundle, never an oracle."""
from __future__ import annotations
import copy
import hashlib
from pathlib import Path
from . import schema


def _manifest(root=None):
    base=schema.root_path(root); value=schema.read(schema.safe(base,'manifest.json'))
    if (not isinstance(value,dict) or set(value)!={'schema_version','dataset','scope','evaluator','cases'}
            or type(value['schema_version']) is not int or value['schema_version']!=1
            or not isinstance(value['cases'],list) or not value['cases']): raise ValueError('Invalid public benchmark manifest')
    schema.no_private_fields(value)
    if value['evaluator']!=schema.evaluator_binding(): raise ValueError('Benchmark evaluator changed; a reviewed evaluator revision is required')
    seen=set()
    for item in value['cases']:
        if not isinstance(item,dict) or set(item)!={'case_id','version','category','task_file','task_sha256','input_sha256'}:
            raise ValueError('Public manifest cannot contain private grading records')
        schema.identity(item['case_id'],item['version']); key=(item['case_id'],item['version'])
        if key in seen or item['category'] not in schema.CATEGORIES: raise ValueError('Duplicate or invalid public benchmark revision')
        seen.add(key)
    return base,value


def list_cases(root=None):
    _,manifest=_manifest(root)
    return {'schema_version':1,'cases':copy.deepcopy(manifest['cases']),'formal_counted':False,
            'benchmark_agent_isolation':'NOT_ISOLATED','quality_gain':'NOT_MEASURED'}


def public_view(case_id,version=None,root=None):
    base,manifest=_manifest(root); matches=[row for row in manifest['cases'] if row['case_id']==case_id and (version is None or row['version']==version)]
    if not matches: raise ValueError('Unknown public benchmark case revision')
    row=max(matches,key=lambda item:item['version']); path=schema.safe(base,row['task_file'])
    raw=path.read_bytes(); task=schema.validate_task(schema.decode(raw)); schema.no_private_fields(task)
    if (hashlib.sha256(raw).hexdigest()!=row['task_sha256'] or task['input_sha256']!=row['input_sha256']
            or any(task[k]!=row[k] for k in ('case_id','version','category'))):
        raise ValueError('Public benchmark task changed; register a new reviewed case version')
    documents=[]
    for pin in task['sources']:
        path=schema.safe(base,pin['file'])
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=pin['sha256']: raise ValueError('Benchmark source changed; historical results are stale')
        if len(raw)>200000: raise ValueError('Public source exceeds calibration bound')
        documents.append({'file':pin['file'],'sha256':pin['sha256'],'text':raw.decode('utf8')})
    result={'task':copy.deepcopy(task),'source_documents':documents,
            'public_binding':{**copy.deepcopy(row),'evaluator_version':manifest['evaluator']['version'],
                              'evaluator_sha256':manifest['evaluator']['sha256']}}
    schema.no_private_fields(result); return result


def build_agent_bundle(case_id,destination,*,version=None,root=None):
    view=public_view(case_id,version,root); target=Path(destination)
    if target.exists(): raise ValueError('Agent bundle destination must be a new directory')
    # Copy exact allowlisted public bytes. No directory walk or private index.
    target.mkdir(parents=True)
    raw=schema.safe(schema.root_path(root),view['public_binding']['task_file']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=view['public_binding']['task_sha256']:
        raise ValueError('Benchmark task changed while freezing its public bundle')
    (target/'task.json').write_bytes(raw)
    for source in view['source_documents']:
        relative=source['file']; path=schema.safe(target,relative); path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(source['text'],encoding='utf8',newline='')
    binding={k:v for k,v in view['public_binding'].items() if k!='task_file'}
    (target/'PUBLIC_BINDING.json').write_bytes(schema.canonical_bytes(binding))
    return {'status':'PUBLIC_BUNDLE_CREATED','case_id':view['task']['case_id'],'version':view['task']['version'],
            'files':sorted(p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()),
            'benchmark_agent_isolation':'NOT_ISOLATED','agent_execution_allowed':False,'formal_counted':False}
