"""Append-only logical event chain and immutable snapshots, committed atomically.

History is independent of the disposable index. No event changes scientific truth.
"""
import datetime as dt
import json
import re
import configuration
from supervision_contracts import canonical_hash
from supervision_snapshot import _path
from . import lineage,schema

LIMIT=64*1024*1024
MAX_EVENTS=10000


def path(controller,project):
    from supervision_ledger import home
    home(controller,project)
    return _path(controller,'state/knowledge/'+configuration.project_id(project)+'/history.json')


def _digest(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value): raise ValueError('Invalid digest')
    return value


def load(controller,project):
    file=path(controller,project); pid=configuration.project_id(project)
    if not file.exists(): return {'schema_version':1,'project_id':pid,'events':[],'snapshots':{},'head_sha256':None}
    try:
        if file.stat().st_size>LIMIT: raise ValueError('History exceeds 64 MiB')
        data=configuration.load_json(file)
        if (not isinstance(data,dict) or type(data.get('schema_version')) is not int or data['schema_version']!=1
                or data.get('project_id')!=pid or not isinstance(data.get('events'),list)
                or not isinstance(data.get('snapshots'),dict) or len(data['events'])>MAX_EVENTS):
            raise ValueError('Invalid history schema')
        previous=None; last_index=None; seen=set(); indexes=set()
        for i,event in enumerate(data['events'],1):
            if not isinstance(event,dict): raise ValueError('Invalid event')
            unsigned={k:v for k,v in event.items() if k!='event_sha256'}
            digest=canonical_hash(unsigned)
            if (type(event.get('sequence')) is not int or event.get('sequence')!=i or event.get('previous_sha256')!=previous or digest!=event.get('event_sha256')
                    or digest in seen or event.get('from_index')!=last_index or event.get('operation')!='knowledge.build'
                    or event.get('type') not in {'INDEX_BUILT','GRAPH_INVALIDATED'}):
                raise ValueError('Event hash/sequence/continuity mismatch')
            _digest(event['to_index']); _digest(event['input_sha256'])
            dt.datetime.fromisoformat(event['recorded_at'])
            if not isinstance(event.get('affected_claims'),list) or not isinstance(event.get('source_changes'),list):
                raise ValueError('Invalid event provenance')
            previous=digest; last_index=event['to_index']; seen.add(digest); indexes.add(last_index)
        if data.get('head_sha256')!=previous: raise ValueError('History head mismatch')
        # Snapshot loss is HISTORY_UNAVAILABLE, not permission to invent old truth.
        for digest,graph in data['snapshots'].items():
            _digest(digest); schema.validate(graph)
            if graph['graph_sha256']!=digest or graph['project_id']!=pid or digest not in indexes:
                raise ValueError('Snapshot digest/project/event mismatch')
        return data
    except (ValueError,TypeError,KeyError,AttributeError,OSError,OverflowError,RecursionError) as exc:
        raise ValueError('HISTORY_INTEGRITY: '+str(exc)) from exc


def summary(controller,project):
    try:
        data=load(controller,project)
        return {'status':'VALID' if data['events'] else 'ABSENT','event_count':len(data['events']),
            'head_sha256':data['head_sha256'],'latest_index':data['events'][-1]['to_index'] if data['events'] else None}
    except ValueError as exc: return {'status':'CORRUPT','error':str(exc)}


def record(controller,project,graph):
    schema.validate(graph)
    if graph['project_id']!=configuration.project_id(project): raise ValueError('Snapshot project mismatch')
    data=load(controller,project); old_index=data['events'][-1]['to_index'] if data['events'] else None
    # Replaying a completed history transaction only repairs the disposable cache.
    if old_index==graph['graph_sha256']:
        if old_index not in data['snapshots']:
            data['snapshots'][old_index]=graph; _store(controller,project,data)
        return summary(controller,project)
    if len(data['events'])>=MAX_EVENTS: raise ValueError('HISTORY_LIMIT: preserve and explicitly archive history before further builds')
    before=data['snapshots'].get(old_index)
    changes=lineage.compare(before,graph) if before else {'affected_claims':[],'affected_nodes':[],'source_changes':[]}
    for c in changes['affected_claims']: c['lost_scopes']=lineage.lost_scopes(c['before'],c['after'])
    invalid=any(c['lost_scopes'] for c in changes['affected_claims']) or any(
        n['before'].get('validity')=='SOURCE_BOUND' and n['after'].get('validity')=='PENDING_REVALIDATION'
        or n['before'].get('location_status')=='FULLTEXT_LOCATED' and n['after'].get('location_status')!='FULLTEXT_LOCATED'
        for n in changes['affected_nodes'])
    event={'sequence':len(data['events'])+1,'previous_sha256':data['head_sha256'],
        'type':'GRAPH_INVALIDATED' if invalid else 'INDEX_BUILT','operation':'knowledge.build',
        'recorded_at':dt.datetime.now(dt.timezone.utc).isoformat(),'from_index':old_index,
        'to_index':graph['graph_sha256'],'input_sha256':graph['input_sha256'],
        'index_schema_version':graph['schema_version'],'builder_version':graph['builder_version'],
        'affected_claims':changes['affected_claims'],'affected_nodes':changes['affected_nodes'],'source_changes':changes['source_changes'],
        'comparison_status':'AVAILABLE' if before else 'HISTORY_UNAVAILABLE' if old_index else 'INITIAL_OBSERVATION',
        'scientific_discovery':False}
    event['event_sha256']=canonical_hash(event)
    data['events'].append(event); data['head_sha256']=event['event_sha256']; data['snapshots'][graph['graph_sha256']]=graph
    _store(controller,project,data)
    return summary(controller,project)


def _store(controller,project,data):
    raw=(json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf8')
    if len(raw)>LIMIT: raise ValueError('History exceeds 64 MiB; preserve history and explicitly archive before further builds')
    import supervision
    supervision._write(path(controller,project),raw)


def diff(controller,project,from_index,to_index):
    _digest(from_index); _digest(to_index)
    data=load(controller,project)
    missing=[d for d in (from_index,to_index) if d not in data['snapshots']]
    if missing: return {'status':'HISTORY_UNAVAILABLE','missing_indexes':missing,'scientific_discovery':False}
    return lineage.compare(data['snapshots'][from_index],data['snapshots'][to_index])
