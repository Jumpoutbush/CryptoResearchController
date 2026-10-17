"""Append-only branch audit history, separate from scientific and cost authority."""
from __future__ import annotations
import copy
import configuration
from engine.common import object_hash
from route_budget import stamp
from . import catalog


def path(project): return catalog._unlinked(catalog.path(project).parent/'history.json')
def registry_path(project): return catalog._unlinked(catalog.path(project).parent/'history.registry.json')


def projection_paths(project):
    return [location for location in (path(project),registry_path(project)) if location.exists()]


def _empty(project): return {'schema_version':1,'project_id':configuration.project_id(project),'events':[]}


def _validate(project,data):
    try:
        if (not isinstance(data,dict) or set(data)!={'schema_version','project_id','events'}
                or type(data['schema_version']) is not int or data['schema_version']!=1
                or data['project_id']!=configuration.project_id(project) or not isinstance(data['events'],list)
                or len(data['events'])>20000): raise ValueError('Invalid candidate branch history')
        previous=None; operations=set()
        for number,event in enumerate(data['events'],1):
            if (type(event['sequence']) is not int or event['sequence']!=number or event['previous_sha256']!=previous
                    or event['type'] not in {'RESOLUTION_RECORDED','SWITCH_APPLIED','SWITCH_CANCELLED'}
                    or event['sha256']!=object_hash({k:v for k,v in event.items() if k!='sha256'})
                    or event['operation_id'] in operations): raise ValueError('Branch history hash-chain or operation identity changed')
            operations.add(event['operation_id']); previous=event['sha256']
            record=event['payload']
            if record.get('scientific_acceptance') is not False: raise ValueError('Branch history cannot grant scientific acceptance')
            if event['type']=='RESOLUTION_RECORDED':
                if (record['status'] not in {'REFUTED','COVERED','RETIRED','CONDITIONAL'}
                        or record['scope_type']!='EXACT_CANDIDATE_REVISION' or record['parent_or_family_refuted'] is not False
                        or record['resolution_id']!=event['operation_id']): raise ValueError('Invalid scoped resolution record')
    except (KeyError,TypeError,AttributeError) as exc: raise ValueError('Corrupt candidate branch history') from exc
    return data


def load(project,*,operation_id=None):
    location=path(project); witness=configuration.load_json(registry_path(project))
    if witness is None:
        if location.exists(): raise ValueError('Branch history high-water witness missing; no silent enrollment')
        return _empty(project)
    try:
        if (set(witness)!={'schema_version','project_id','committed_sha256','pending','sha256'}
                or type(witness['schema_version']) is not int or witness['schema_version']!=1
                or witness['project_id']!=configuration.project_id(project)
                or witness['sha256']!=object_hash({k:v for k,v in witness.items() if k!='sha256'})):
            raise ValueError('Branch history high-water witness changed')
        pending=witness['pending']
        if pending is not None:
            if operation_id is None or operation_id!=pending['operation_id']:
                raise ValueError('BRANCH_HISTORY_RECOVERY_REQUIRED: only the frozen local operation may finish')
            after=_validate(project,pending['afterimage'])
            if object_hash(after)!=pending['afterimage_sha256'] or pending['beforeimage_sha256']!=witness['committed_sha256']:
                raise ValueError('Branch history frozen recovery image changed')
            prefix={**after,'events':after['events'][:-1]}
            if ((pending['beforeimage_sha256'] is None and len(after['events'])!=1)
                    or (pending['beforeimage_sha256'] is not None and object_hash(prefix)!=pending['beforeimage_sha256'])):
                raise ValueError('Branch history recovery does not append to committed prefix')
            actual=configuration.load_json(location)
            actual_sha=object_hash(actual) if actual is not None else None
            if actual_sha not in {pending['beforeimage_sha256'],pending['afterimage_sha256']}:
                raise ValueError('Branch history recovery inputs changed; preserve operator evidence')
            if actual_sha!=pending['afterimage_sha256']: configuration.atomic_json(location,after)
            witness['committed_sha256']=pending['afterimage_sha256']; witness['pending']=None; _write_witness(project,witness)
        if not location.is_file(): raise ValueError('Registered branch history is missing')
        data=_validate(project,configuration.load_json(location))
        if object_hash(data)!=witness['committed_sha256']: raise ValueError('Branch history differs from its high-water witness')
        return data
    except (KeyError,TypeError,AttributeError) as exc: raise ValueError('Corrupt branch history witness') from exc


def _write_witness(project,value):
    value['sha256']=object_hash({k:v for k,v in value.items() if k!='sha256'})
    configuration.atomic_json(registry_path(project),value)


def append(project,kind,payload,operation_id,reason):
    """Trusted caller holds route/core/resolution locks; no science or costs here."""
    data=load(project,operation_id=operation_id)
    old=next((e for e in data['events'] if e['operation_id']==operation_id),None)
    if old:
        if old['type']!=kind or old['payload']!=payload: raise ValueError('Branch history operation conflict')
        return copy.deepcopy(old['payload'])
    before=object_hash(data) if path(project).is_file() else None
    event={'sequence':len(data['events'])+1,'previous_sha256':data['events'][-1]['sha256'] if data['events'] else None,
           'type':kind,'operation_id':operation_id,'reason':reason,'at':stamp(),'payload':copy.deepcopy(payload)}
    event['sha256']=object_hash(event); after=copy.deepcopy(data); after['events'].append(event); _validate(project,after)
    witness={'schema_version':1,'project_id':configuration.project_id(project),'committed_sha256':before,
        'pending':{'operation_id':operation_id,'beforeimage_sha256':before,'afterimage_sha256':object_hash(after),'afterimage':after}}
    _write_witness(project,witness); configuration.atomic_json(path(project),after)
    witness['committed_sha256']=object_hash(after); witness['pending']=None; _write_witness(project,witness)
    return copy.deepcopy(payload)


def projection_records(project):
    return [copy.deepcopy(event['payload']) for event in load(project)['events'] if event['type']=='RESOLUTION_RECORDED']


def view(project,candidate_id=None):
    data=load(project)
    events=[copy.deepcopy(event) for event in data['events']
            if candidate_id is None or event['payload'].get('candidate_id')==candidate_id]
    return {'schema_version':1,'project_id':data['project_id'],'events':events,
            'records':[e['payload'] for e in events if e['type']=='RESOLUTION_RECORDED'],
            'scientific_acceptance':False,'history_sha256':object_hash(data)}
