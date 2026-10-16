"""Deterministic exact graph lookup; ranking never grants scientific status."""
from collections import deque
import hashlib
import json
import re
import configuration
import research_focus
from engine import problem_compiler
from engine.common import goal_binding,fresh
from supervision_snapshot import _path
from . import build as projection


def validate_dependency_bindings(project,graph=None):
    """Fail closed for retrieval without repairing or rewriting scientific authority."""
    from engine.claim_graph import load
    data=load(project) if graph is None else _pinned_json(project,projection.CLAIMS,'PROJECT',graph['source_manifest'],{'claims':[]})
    for current in data['claims']:
        for item in [*current.get('history',[]),current]:
            pins=item.get('dependency_pins'); declared=item['spec']['dependencies']
            valid=isinstance(pins,dict) and set(pins)==set(declared)
            if valid:
                valid=all(isinstance(pin,dict) and set(pin)=={'revision','spec_sha256'}
                    and type(pin['revision']) is int and pin['revision']>0
                    and isinstance(pin['spec_sha256'],str) and re.fullmatch('[0-9a-f]{64}',pin['spec_sha256'])
                    for pin in pins.values())
            if not valid: raise ValueError('CLAIM_DEPENDENCY_BINDING_INVALID:'+item['id']+':'+str(item['revision']))


def _pinned_json(root,path,scope,manifest,default):
    file=_path(root,path)
    raw=file.read_bytes() if file.is_file() else None
    digest=hashlib.sha256(raw).hexdigest() if raw is not None else None
    expected=next((e['sha256'] for e in manifest if (e['scope'],e['path'])==(scope,path)),None)
    if digest!=expected: raise ValueError('SOURCE_CHANGED_DURING_CONTEXT: '+path)
    return json.loads(raw.decode('utf-8-sig')) if raw is not None else default


def search(controller,project,*,task='',claim_id=None,problem_id=None,problem_version=None,obligation_id=None,goal_anchor_id=None):
    for name,value in (('claim_id',claim_id),('problem_id',problem_id),('obligation_id',obligation_id)):
        if value is not None and (not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}',value)):
            raise ValueError('Invalid exact '+name)
    if not isinstance(task,str) or len(task)>16000: raise ValueError('Task must be text of at most 16000 characters')
    if problem_version is not None and (type(problem_version) is not int or problem_version<1): raise ValueError('Invalid problem version')
    if problem_version is not None and not problem_id: raise ValueError('Problem version requires an explicit problem ID')
    validate_dependency_bindings(project)
    graph=projection.derive(controller,project); nodes={n['id']:n for n in graph['nodes']}
    validate_dependency_bindings(project,graph)
    manifest=graph['source_manifest']; key=configuration.project_id(project)
    state=_pinned_json(project,'research/STATE.json','PROJECT',manifest,{})
    route=_pinned_json(controller,'state/routes/'+key+'.json','CONTROLLER',manifest,{})
    epochs=route.get('epochs',[]); focus=epochs[-1].get('focus') if epochs else None
    missing=[]
    if route and (route.get('schema_version')!=1 or route.get('project_id',configuration.project_id(project))!=configuration.project_id(project)):
        missing.append('CORRUPT_GOAL_ANCHOR_LEDGER')
    if focus:
        origin='FROZEN_ROUTE_FOCUS'
        if focus.get('binding')!=research_focus.binding(project,state): missing.append('STALE_GOAL_ANCHOR')
        if focus!=research_focus.make_focus(project,state,focus.get('core_problem')) or epochs[-1].get('route')!=state.get('research_route'):
            missing.append('CORRUPT_GOAL_ANCHOR')
    else: focus=research_focus.make_focus(project,state); origin='READONLY_DERIVED_FOCUS'
    if goal_anchor_id is not None and goal_anchor_id!=focus['anchor_id']: missing.append('GOAL_ANCHOR_MISMATCH')
    # Same read-only selection as discovery_scheduler.active, from the exact pinned bytes.
    ledger=_pinned_json(controller,'state/discovery/'+key+'.json','CONTROLLER',manifest,
        {'schema_version':1,'active_attempt':None,'attempts':[]})
    active=next((a for a in ledger['attempts'] if a['id']==ledger.get('active_attempt')),None)
    if not any((claim_id,problem_id,obligation_id)) and active:
        problem_id=active['problem_id']; problem_version=active['problem_version']
    active_context=None
    if active:
        active_context={k:active.get(k) for k in ('id','status','problem_id','problem_version','problem_sha256','binding','budget','extensions','stagnation')}
        active_context['calls']=[{k:c.get(k) for k in ('run_id','status')} for c in active.get('calls',[])]
        if active.get('binding')!=goal_binding(project): missing.append('ACTIVE_ATTEMPT_BINDING_STALE')
        try:
            pinned=problem_compiler.get_problem(project,active['problem_id'],active['problem_version'])
            if pinned['spec_sha256']!=active.get('problem_sha256') or not fresh(project,pinned['source_bindings']):
                missing.append('ACTIVE_PROBLEM_PIN_STALE')
        except (ValueError,KeyError): missing.append('ACTIVE_PROBLEM_UNAVAILABLE')
    claims=[n for n in graph['nodes'] if n['kind']=='CLAIM_REVISION' and n.get('current')]
    if claim_id:
        claims=[n for n in claims if n['claim_id']==claim_id]
        if not claims: missing.append('UNKNOWN_CLAIM:'+claim_id)
        elif problem_id is None: problem_id=claims[0]['problem_id']; problem_version=claims[0]['problem_version']
    if problem_id:
        problems=[n for n in graph['nodes'] if n['kind']=='PROBLEM_VERSION' and n['problem_id']==problem_id
            and (problem_version is None or n['problem_version']==problem_version)]
        if len(problems)!=1: missing.append(('AMBIGUOUS_PROBLEM:' if problems else 'UNKNOWN_PROBLEM:')+problem_id)
        else: problem_version=problems[0]['problem_version']
        claims=[n for n in claims if n['problem_id']==problem_id and n['problem_version']==problem_version]
    if obligation_id:
        obligations=[n for n in graph['nodes'] if n['kind']=='OBLIGATION' and n.get('obligation_id')==obligation_id
            and (problem_id is None or n.get('problem_id')==problem_id and n.get('problem_version')==problem_version)]
        if len(obligations)!=1: missing.append(('AMBIGUOUS_OBLIGATION:' if obligations else 'UNKNOWN_OBLIGATION:')+obligation_id)
        elif problem_id is None: problem_id=obligations[0]['problem_id']; problem_version=obligations[0]['problem_version']
        claims=[n for n in claims if n['problem_id']==problem_id and n['problem_version']==problem_version and obligation_id in n['obligation_ids']]
    exact=bool(claim_id or problem_id or obligation_id)
    tokens=set(re.findall(r'\w+',task.casefold()))
    def relevance(n):
        text=' '.join(str(n.get(k,'')) for k in ('statement','title','failure_reason'))
        if isinstance(n.get('location'),dict): text+=' '+str(n['location'].get('excerpt',''))
        return sum(1 for t in tokens if t in text.casefold())
    seeds={n['id'] for n in claims} if exact else {n['id'] for n in graph['nodes'] if relevance(n)}
    seeds.update(n['id'] for n in graph['nodes'] if n['kind'] in {'PROBLEM_VERSION','OBLIGATION'} and problem_id
        and n.get('problem_id')==problem_id and n.get('problem_version')==problem_version
        and (n['kind']=='PROBLEM_VERSION' or not obligation_id or n.get('obligation_id')==obligation_id))
    if not seeds: missing.append('NO_RELEVANT_EVIDENCE')
    if exact and not any(n['proof_status']=='INDEPENDENTLY_REVIEWED' for n in claims): missing.append('NO_CURRENT_REVIEWED_CLAIM_FOR_TARGET')
    if active and (problem_id,problem_version)!=(active['problem_id'],active['problem_version']):
        missing.append('ACTIVE_TARGET_CONFLICT')
    edges=graph['edges']; outgoing={}; incoming={}
    for e in edges:
        outgoing.setdefault(e['from'],[]).append(e); incoming.setdefault(e['to'],[]).append(e)
    required=set(seeds); queue=deque(sorted(seeds)); refutations=set()
    while queue:
        uid=queue.popleft(); adjacent=[e['to'] for e in outgoing.get(uid,[]) if e['relation'] in {'REQUIRES','USES_SOURCE','REVIEWED_BY'}]
        for e in incoming.get(uid,[]):
            if e['relation'] in {'SUPPORTS','REFUTES'}:
                adjacent.append(e['from'])
                if e['relation']=='REFUTES': refutations.add(e['from'])
        for target in adjacent:
            if target not in required: required.add(target); queue.append(target)
    candidates=[]
    from .adapters import claims as claim_adapter
    specs={(r['id'],r['revision']):r['spec'] for r,_,_ in claim_adapter.read(project)}
    invalid_target=bool(any(s.startswith(('UNKNOWN_','AMBIGUOUS_','STALE_GOAL','CORRUPT_GOAL','GOAL_ANCHOR_','ACTIVE_')) for s in missing))
    for n in graph['nodes']:
        if n['kind'] in {'PROJECT','EVIDENCE_FILE','GOAL'}: continue
        score=relevance(n)
        if n['id'] not in required: continue
        positive=bool(n['kind']=='CLAIM_REVISION' and n.get('current') and n.get('proof_status')=='INDEPENDENTLY_REVIEWED'
            and not n.get('invalidation_reasons') and not invalid_target)
        role=('COUNTEREXAMPLE' if n['id'] in refutations else 'INVALIDATED_CONTEXT_ONLY'
            if n.get('invalidation_reasons') or n.get('validity')=='PENDING_REVALIDATION' else
            'REVIEWED_CLAIM' if positive else 'PRIMARY_SOURCE_LOCATION' if n['kind']=='THEOREM_SPAN' else 'CANDIDATE_OR_BACKGROUND')
        if n['kind']=='CLAIM_REVISION' and n.get('invalidation_reasons'):
            missing.extend('CLAIM_REQUIRES_REVALIDATION:'+n['claim_id']+':'+r for r in n['invalidation_reasons'])
        item={k:n[k] for k in ('claim_id','problem_id','problem_version','obligation_id','statement','title','source_version',
            'location','location_status','review_status','math_render_status','applicability','invalidation_reasons') if k in n}
        item.update(node_id=n['id'],kind=n['kind'],source_file=n.get('source_file',n['source_path']),
            sha256=n.get('sha256',n.get('pinned_sha256',n['source_sha256'])),
            provenance_file=n['source_path'],provenance_sha256=n['source_sha256'],source_scope=n.get('source_scope'),
            claim_revision=n.get('claim_revision'),verification_status=n.get('proof_status',n.get('validity',n['verified_status'])),
            positive_basis=positive,role=role,required=n['id'] in required,source_id=n['source_id'],
            current_sha256=n.get('current_sha256'),relevance_score=score)
        if n['kind']=='CLAIM_REVISION': item['assumptions']=specs[(n['claim_id'],n['claim_revision'])]['assumptions']
        if (n['kind']=='SOURCE_VERSION' and n.get('source_scope')=='PROJECT'
                and n['source_path'].endswith(('.md','.txt','.tex','.lean'))
                and n.get('pinned_sha256') and n.get('pinned_sha256')==n.get('current_sha256')):
            file=projection._safe_reference(project,n['source_path'])
            if file.stat().st_size<=262144:
                raw=file.read_bytes()
                if hashlib.sha256(raw).hexdigest()!=n['pinned_sha256']: raise ValueError('SOURCE_CHANGED_DURING_CONTEXT')
                excerpt=raw[:1024].decode('utf-8-sig',errors='replace')
                item.update(excerpt=excerpt,excerpt_truncated=len(raw)>1024,
                    excerpt_sha256=hashlib.sha256(excerpt.encode('utf8')).hexdigest(),excerpt_is_untrusted=True)
        priority=0 if role=='COUNTEREXAMPLE' else 1 if n['id'] in required and n['kind']=='CLAIM_REVISION' and n['id'] not in seeds else 2 if positive else 3 if n['kind']=='THEOREM_SPAN' else 4 if n['id'] in required else 5
        candidates.append((priority,-score,n['id'],item))
    target=None
    if problem_id and problem_version:
        try:
            record=problem_compiler.get_problem(project,problem_id,problem_version)
            target={'source_file':projection.PROBLEMS,'sha256':next(n['source_sha256'] for n in graph['nodes'] if n['kind']=='PROBLEM_VERSION' and n['problem_id']==problem_id and n['problem_version']==problem_version),
                'spec_sha256':record['spec_sha256'],'spec':record['spec']}
        except (ValueError,KeyError,StopIteration): missing.append('FROZEN_PROBLEM_UNAVAILABLE')
    return {'graph':graph,'goal_anchor_id':focus['anchor_id'],'anchor_origin':origin,'frozen_target':target,'active_attempt':active_context,
        'missing_required':sorted(set(missing)),'candidates':[x[-1] for x in sorted(candidates)],
        'query':{'task':task,'claim_id':claim_id,'problem_id':problem_id,'problem_version':problem_version,'obligation_id':obligation_id},
        'cache_used':False,'index_origin':'LIVE_AUTHORITY_PROJECTION'}
