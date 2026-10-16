"""Explicit bilateral public capsules. Never traverse foreign scientific evidence."""
import copy
import hashlib
import json
from pathlib import Path
import re
import configuration
from research_quality import hash_file
from supervision_contracts import canonical_hash
from supervision_snapshot import _path
from . import reuse_review,schema

DEFAULTS={'schema_version':1,'enabled':False,'projects':{}}
HEX=re.compile(r'[0-9a-f]{64}')
IDENT=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}')
PROJECT=re.compile(r'[a-z0-9][a-z0-9_-]{0,63}')
LICENSES={'CC0-1.0','CC-BY-4.0','MIT','Apache-2.0','OPERATOR-APPROVED-SHARING'}


def _read(path,watch,limit=65536):
    if not path.is_file() or path.stat().st_size>limit: raise ValueError('SHARING_SOURCE_MISSING_OR_OVERSIZED')
    raw=path.read_bytes()
    if len(raw)>limit: raise ValueError('SHARING_SOURCE_OVERSIZED')
    pin=(hashlib.sha256(raw).hexdigest(),len(raw))
    if path in watch and watch[path]!=pin: raise ValueError('SHARING_INPUT_CHANGED')
    watch[path]=pin
    return raw


def _stable(watch):
    for path,(digest,size) in watch.items():
        if not path.is_file() or path.stat().st_size!=size or hash_file(path)!=digest:
            raise ValueError('SHARING_INPUT_CHANGED')


def _json(path,watch,limit=65536):
    try: return json.loads(_read(path,watch,limit).decode('utf-8-sig'))
    except (UnicodeError,json.JSONDecodeError) as exc: raise ValueError('INVALID_SHARING_JSON') from exc


def _id(value,pattern=IDENT):
    if not isinstance(value,str) or not pattern.fullmatch(value): raise ValueError('Invalid sharing identity')
    return value


def _sha(value):
    if not isinstance(value,str) or not HEX.fullmatch(value): raise ValueError('Invalid sharing SHA256')
    return value


def _text(value,limit=4096):
    if not isinstance(value,str) or not value.strip() or len(value)>limit: raise ValueError('Invalid sharing text')
    return value


def _public_relative(relative,kind):
    prefix={'reference':'knowledge/shared/references/','source':'knowledge/shared/sources/','draft':'knowledge/shared/drafts/'}[kind]
    allowed={'.json'} if kind=='reference' else {'.txt','.md','.json'} if kind=='source' else {'.txt','.md'}
    if (not isinstance(relative,str) or not relative.startswith(prefix) or not re.fullmatch(r'[A-Za-z0-9_./-]{1,240}',relative)
            or Path(relative).suffix not in allowed or any(not part or part.startswith('.') or part.endswith('.') for part in relative.split('/'))):
        raise ValueError('SHARING_PATH_NOT_PUBLIC_WHITELIST')
    return relative


def _public_path(project,relative,kind):
    _public_relative(relative,kind)
    path=_path(project,relative)
    return path


def _project(controller,key,watch):
    _id(key,PROJECT); project=_path(controller,'projects/'+key)
    obj=_json(_path(project,'PROJECT.json'),watch)
    if not isinstance(obj,dict) or obj.get('id')!=key: raise ValueError('SHARING_PROJECT_ID_MISMATCH')
    return project


def _local(controller,project,watch):
    if Path(controller).resolve()!=Path(configuration.ROOT).resolve(): raise ValueError('Sharing controller must match configuration root')
    key=configuration.project_id(project)
    if Path(project).resolve()!=Path(controller).resolve()/'projects'/key: raise ValueError('Invalid local sharing project')
    _project(controller,key,watch)
    return key


def _policy(controller,watch):
    path=_path(controller,'config/sharing_policy.json')
    obj=_json(path,watch,1048576) if path.is_file() else copy.deepcopy(DEFAULTS)
    if not isinstance(obj,dict) or set(obj)!=set(DEFAULTS) or type(obj['schema_version']) is not int or obj['schema_version']!=1:
        raise ValueError('Invalid sharing policy schema')
    if type(obj['enabled']) is not bool or not isinstance(obj['projects'],dict) or len(obj['projects'])>128:
        raise ValueError('Invalid sharing policy')
    for key,settings in obj['projects'].items():
        _id(key,PROJECT)
        if (not isinstance(settings,dict) or set(settings)-{'enabled','imports','exports','model_sha256'}
                or not {'enabled','imports','exports'}<=set(settings) or type(settings['enabled']) is not bool
                or any(not isinstance(settings[k],list) or len(settings[k])>64 for k in ('imports','exports'))):
            raise ValueError('Invalid project sharing policy')
        if 'model_sha256' in settings: _sha(settings['model_sha256'])
        if settings['enabled'] and settings['imports'] and 'model_sha256' not in settings:
            raise ValueError('Destination sharing requires an operator-pinned model_sha256')
        imports=set(); exports=set()
        for entry in settings['imports']:
            if not isinstance(entry,dict) or set(entry)!={'origin_project','id','sha256'}: raise ValueError('Invalid sharing import')
            identity=(_id(entry['origin_project'],PROJECT),_id(entry['id'])); _sha(entry['sha256'])
            if identity in imports or identity[0]==key: raise ValueError('Duplicate or self sharing import')
            imports.add(identity)
        for entry in settings['exports']:
            if not isinstance(entry,dict) or set(entry)!={'id','path','sha256','destinations'}: raise ValueError('Invalid sharing export')
            eid=_id(entry['id']); _sha(entry['sha256'])
            _public_relative(entry['path'],'reference')
            if eid in exports or not isinstance(entry['destinations'],list) or len(entry['destinations'])>64:
                raise ValueError('Invalid sharing destinations')
            for destination in entry['destinations']: _id(destination,PROJECT)
            if len(entry['destinations'])!=len(set(entry['destinations'])): raise ValueError('Duplicate sharing destination')
            exports.add(eid)
    return obj


def _model(controller,project,relative,watch,*,expected_sha256=None,additional_assumptions=()):
    if relative!='knowledge/shared/MODEL.json': raise ValueError('Sharing model must use the explicit fixed local path')
    obj=_json(_path(project,relative),watch)
    if expected_sha256 is not None and watch[_path(project,relative)][0]!=expected_sha256: raise ValueError('TARGET_MODEL_PIN_CHANGED')
    fields={'schema_version','goal_sha256','problem_id','problem_version','problem_sha256','model'}
    if not isinstance(obj,dict) or set(obj)!=fields or type(obj['schema_version']) is not int or obj['schema_version']!=1: raise ValueError('Invalid target model descriptor')
    _sha(obj['goal_sha256']); _sha(obj['problem_sha256']); _id(obj['problem_id'])
    if type(obj['problem_version']) is not int or obj['problem_version']<1: raise ValueError('Invalid sharing problem version')
    from engine import problem_compiler
    _read(_path(project,'research/discovery/PROBLEMS.json'),watch,4000000)
    problem=problem_compiler.get_problem(project,obj['problem_id'],obj['problem_version'])
    goal=hashlib.sha256(_read(_path(project,'GOAL.md'),watch,4000000)).hexdigest()
    if problem['goal_sha256']!=goal: raise ValueError('TARGET_MODEL_PROBLEM_STALE')
    for relative,expected in problem['source_bindings'].items():
        path=_path(project,relative)
        if not path.is_file() or hash_file(path)!=expected: raise ValueError('TARGET_MODEL_PROBLEM_STALE')
        pin=(expected,path.stat().st_size)
        if path in watch and watch[path]!=pin: raise ValueError('SHARING_INPUT_CHANGED')
        watch[path]=pin
    reuse_review.validate_model(obj['model'])
    assumptions=list(dict.fromkeys([*problem['spec']['assumptions'],*additional_assumptions]))
    if (goal!=obj['goal_sha256'] or problem['spec_sha256']!=obj['problem_sha256']
            or any(obj['model'][k]!=problem['spec'][k] for k in ('domain','quantifiers')) or obj['model']['assumptions']!=assumptions):
        raise ValueError('TARGET_MODEL_BINDING_MISMATCH')
    return obj


def _capsule(obj,origin,reference_id):
    fields={'schema_version','id','revision','origin_project','kind','summary','permission','origin','model','source_bindings','verification_status_at_export'}
    if not isinstance(obj,dict) or set(obj)!=fields or type(obj['schema_version']) is not int or obj['schema_version']!=1:
        raise ValueError('Invalid shared capsule schema')
    if obj['origin_project']!=origin or obj['id']!=reference_id: raise ValueError('Shared capsule identity mismatch')
    if type(obj['revision']) is not int or obj['revision']<1 or not isinstance(obj['kind'],str) or obj['kind'] not in {'THEOREM_SUMMARY','PAPER_IDENTITY','FAILED_ROUTE_TAG'}:
        raise ValueError('Invalid shared capsule version/kind')
    _text(obj['summary']); reuse_review.validate_model(obj['model']); _text(obj['verification_status_at_export'],160)
    permission=obj['permission']
    if (not isinstance(permission,dict) or set(permission)!={'license','approved_by','reason'}
            or not isinstance(permission['license'],str) or permission['license'] not in LICENSES):
        raise ValueError('Invalid public sharing permission')
    _text(permission['approved_by'],160); _text(permission['reason'],1024)
    source=obj['origin']; keys={'node_id','goal_sha256','problem_id','problem_version','problem_sha256','claim_id','claim_revision','claim_spec_sha256','obligation_ids','authority_sha256_at_export'}
    if not isinstance(source,dict) or set(source)!=keys: raise ValueError('Invalid shared origin provenance')
    has_claim=source['claim_id'] is not None
    if not has_claim and obj['kind']=='THEOREM_SUMMARY': raise ValueError('Theorem summary requires exact claim provenance')
    for key in ('goal_sha256','problem_sha256','claim_spec_sha256','authority_sha256_at_export'):
        if source[key] is not None or has_claim: _sha(source[key])
    for key in ('problem_id','claim_id'):
        if source[key] is not None or has_claim: _id(source[key])
    for key in ('problem_version','claim_revision'):
        if (source[key] is not None or has_claim) and (type(source[key]) is not int or source[key]<1): raise ValueError('Invalid shared origin revision')
    expected_node=(schema.identity(origin,'CLAIM_REVISION',source['claim_id'],source['claim_revision']) if has_claim
        else schema.identity(origin,'SOURCE_VERSION' if obj['kind']=='PAPER_IDENTITY' else 'FAILED_BRANCH',obj['id'],obj['revision']))
    if (not isinstance(source['obligation_ids'],list) or len(source['obligation_ids'])>64
            or source['node_id']!=expected_node):
        raise ValueError('Invalid shared origin node')
    for value in source['obligation_ids']: _id(value)
    if not isinstance(obj['source_bindings'],list) or not 1<=len(obj['source_bindings'])<=16: raise ValueError('Missing public source bindings')
    paths=set()
    for binding in obj['source_bindings']:
        if not isinstance(binding,dict) or set(binding)!={'path','sha256'}: raise ValueError('Invalid public source binding')
        _sha(binding['sha256'])
        if not isinstance(binding['path'],str) or binding['path'] in paths: raise ValueError('Duplicate public source')
        paths.add(binding['path'])
    return obj


def preview(controller,project,*,claim_id,reference_id,revision,model_path,summary_path,public_sources,license_id,approved_by,reason):
    """Source-owner preview only; stdout draft is not an authorization or a write."""
    watch={}; key=_local(controller,project,watch); _id(reference_id)
    if type(revision) is not int or revision<1: raise ValueError('Invalid shared revision')
    from . import retrieval
    found=retrieval.search(controller,project,claim_id=claim_id)
    claim=next((n for n in found['graph']['nodes'] if n['kind']=='CLAIM_REVISION' and n['claim_id']==claim_id and n['current']),None)
    if claim is None or claim['proof_status']!='INDEPENDENTLY_REVIEWED' or found['missing_required']:
        raise ValueError('SHARE_PREVIEW_REQUIRES_CURRENT_REVIEWED_CLAIM')
    records=_json(_path(project,'research/discovery/CLAIM_GRAPH.json'),watch,4000000)
    record=next(c for c in records['claims'] if c['id']==claim_id)
    if watch[_path(project,'research/discovery/CLAIM_GRAPH.json')][0]!=claim['source_sha256']: raise ValueError('SHARING_INPUT_CHANGED')
    descriptor=_model(controller,project,model_path,watch,additional_assumptions=record['spec']['assumptions'])
    if (descriptor['problem_id'],descriptor['problem_version'])!=(claim['problem_id'],claim['problem_version']):
        raise ValueError('SHARE_MODEL_PROBLEM_MISMATCH')
    sources=[]
    for relative in public_sources:
        raw=_read(_public_path(project,relative,'source'),watch,1048576)
        sources.append({'path':relative,'sha256':hashlib.sha256(raw).hexdigest()})
    obj={'schema_version':1,'id':reference_id,'revision':revision,'origin_project':key,'kind':'THEOREM_SUMMARY',
        'summary':_read(_public_path(project,summary_path,'draft'),watch,16384).decode('utf-8-sig'),
        'permission':{'license':license_id,'approved_by':approved_by,'reason':reason},'model':descriptor['model'],
        'origin':{'node_id':claim['id'],'goal_sha256':claim['goal_sha256'],'problem_id':claim['problem_id'],
            'problem_version':claim['problem_version'],'problem_sha256':descriptor['problem_sha256'],
            'claim_id':claim_id,'claim_revision':claim['claim_revision'],'claim_spec_sha256':claim['spec_sha256'],
            'obligation_ids':claim['obligation_ids'],'authority_sha256_at_export':claim['source_sha256']},
        'source_bindings':sources,'verification_status_at_export':claim['proof_status']}
    _capsule(obj,key,reference_id); _stable(watch)
    from .build import _manifest
    if _manifest(controller,project)!=found['graph']['source_manifest']: raise ValueError('SHARING_INPUT_CHANGED')
    return obj


def search(controller,project,*,query='',model_path='knowledge/shared/MODEL.json'):
    watch={}; target=_local(controller,project,watch); policy=_policy(controller,watch)
    result={'schema_version':1,'status':'DISABLED','destination_project':target,'references':[],'diagnostics':[],
        'conflicts':[],'cache_used':False,'network_requests':0,'provider_requests':0}
    destination=policy['projects'].get(target,{})
    if not policy['enabled'] or not destination.get('enabled'): return result
    if not isinstance(query,str) or len(query)>16000: raise ValueError('Invalid shared query')
    result['status']='OK'
    if not destination['imports']: return result
    descriptor=_model(controller,project,model_path,watch,expected_sha256=destination['model_sha256'])
    for entry in destination['imports']:
        origin=entry['origin_project']; diagnostic={'origin_project':origin,'id':entry['id']}
        source=policy['projects'].get(origin,{})
        export=next((e for e in source.get('exports',[]) if e['id']==entry['id']),None)
        if not source.get('enabled') or export is None or target not in export['destinations']:
            result['diagnostics'].append({**diagnostic,'reason':'SOURCE_PERMISSION_DENIED'}); continue
        if export['sha256']!=entry['sha256']:
            result['diagnostics'].append({**diagnostic,'reason':'IMPORT_EXPORT_PIN_MISMATCH'}); continue
        try:
            home=_project(controller,origin,watch); path=_public_path(home,export['path'],'reference'); raw=_read(path,watch)
            if hashlib.sha256(raw).hexdigest()!=export['sha256']:
                result['diagnostics'].append({**diagnostic,'reason':'EXPORT_SHA_CHANGED','source_file':export['path']}); continue
            obj=_capsule(json.loads(raw.decode('utf-8-sig')),origin,entry['id']); invalid=[]
            for binding in obj['source_bindings']:
                raw_source=_read(_public_path(home,binding['path'],'source'),watch,1048576)
                current=hashlib.sha256(raw_source).hexdigest()
                if current!=binding['sha256']:
                    invalid.append({'reason':'PUBLIC_SOURCE_CHANGED','source_file':binding['path'],
                        'expected_sha256':binding['sha256'],'current_sha256':current})
            if invalid:
                result['diagnostics'].append({**diagnostic,'reason':'STALE_REFERENCE','causes':invalid}); continue
            if query and query.casefold() not in (obj['summary']+' '+obj['id']).casefold(): continue
            result['references'].append({'reference_id':origin+':SHARED:'+obj['id']+':'+str(obj['revision'])+':'+export['sha256'],
                'origin_project':origin,'destination_project':target,'id':obj['id'],'revision':obj['revision'],'kind':obj['kind'],
                'source_file':export['path'],'sha256':export['sha256'],'summary':obj['summary'],'permission':obj['permission'],
                'origin':obj['origin'],'source_hashes':obj['source_bindings'],'verification_status_at_export':obj['verification_status_at_export'],
                'destination_binding':{k:v for k,v in descriptor.items() if k!='model'},
                'destination_model_sha256':destination['model_sha256'],
                'reuse_review':reuse_review.compare(obj['model'],descriptor['model']),'status':'REFERENCE_ONLY','positive_basis':False,
                'requires_revalidation':True,'notice':'参考用，尚未在目标项目重新审查',
                'freshness_scope':'EXPLICIT_PUBLIC_SOURCES_ONLY','private_upstream_status':'NOT_READ_OR_REVALIDATED'})
        except (OSError,ValueError,KeyError,UnicodeError) as exc:
            result['diagnostics'].append({**diagnostic,'reason':'INVALID_OR_UNAVAILABLE_PUBLIC_EXPORT',
                'detail':str(exc) if isinstance(exc,ValueError) else type(exc).__name__})
    result['references'].sort(key=lambda r:r['reference_id'])
    for ref in result['references']:
        others=[r['reference_id'] for r in result['references'] if r['reference_id']!=ref['reference_id']
            and (r['id']==ref['id'] or ref['origin']['claim_id'] is not None and r['origin']['claim_id']==ref['origin']['claim_id'])]
        if others: result['conflicts'].append({'reference_id':ref['reference_id'],'reason':'NAMESPACE_OR_THEOREM_CONTEXT_CONFLICT','other_references':others})
    _stable(watch)
    result['input_digest']=canonical_hash(sorted((str(p.relative_to(controller)),digest) for p,(digest,_) in watch.items()))
    return result
