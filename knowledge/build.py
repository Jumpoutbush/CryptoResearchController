"""Rebuildable JSON cache. All project/route/claim inputs are read-only."""
from __future__ import annotations
import copy
import json
from pathlib import Path

import configuration
from engine import knowledge_graph, problem_compiler
from research_quality import hash_file
from route_budget import file_lock
from supervision_contracts import canonical_hash
from supervision_snapshot import _path
from . import schema
from .adapters import claims

CLAIMS = 'research/discovery/CLAIM_GRAPH.json'
PROBLEMS = 'research/discovery/PROBLEMS.json'
ROOTS = knowledge_graph.ROOTS


def _safe_reference(project, relative):
    path = _path(project, relative)
    if relative.split('/')[0] not in ROOTS and relative not in {'GOAL.md','AGENTS.md','PROJECT.json','RESEARCH_PROFILE.json'}:
        raise ValueError('Non-research projection reference')
    if any(p.casefold() in {'.env','auth.json','credentials.json','id_rsa','id_ed25519'} for p in path.parts):
        raise ValueError('Credential reference is not research evidence')
    return path


def _manifest(controller, project):
    from runner_core import project_files
    entries = []
    paths = [('PROJECT', p.relative_to(project).as_posix(), p) for p in project_files(project)]
    key = configuration.project_id(project)
    paths += [('CONTROLLER', s, _path(controller, s)) for s in (
        'state/routes/' + key + '.json', 'state/discovery/' + key + '.json',
        'config/defaults.json', 'config/discovery_defaults.json', 'config/projects/' + key + '.json')]
    for scope, relative, path in paths:
        if scope == 'PROJECT':
            try: path = _safe_reference(project, relative)
            except ValueError:
                # Linked source files must never be hidden by the cache.
                _path(project, relative)
                continue
        source_schema = None
        digest = hash_file(path) if path.is_file() else None
        if digest and path.suffix == '.json' and path.stat().st_size <= 4_000_000:
            try:
                value = configuration.load_json(path)
                if isinstance(value, dict): source_schema = value.get('schema_version')
            except ValueError: pass
        entries.append({'scope':scope,'path':relative,'sha256':digest,'schema_version':source_schema})
    if len(entries) > 10000: raise ValueError('Projection input limit exceeded')
    return sorted(entries, key=lambda e:(e['scope'],e['path']))


class _Graph:
    def __init__(self, controller, project, manifest):
        self.controller, self.project = Path(controller), Path(project)
        self.project_id = configuration.project_id(project)
        self.manifest = {(e['scope'],e['path']):e for e in manifest}
        self.goal = self.digest('GOAL.md')
        self.nodes, self.edges, self.gaps = {}, {}, set()

    def digest(self, path, scope='PROJECT'):
        return self.manifest.get((scope,path),{}).get('sha256')

    def goal_version(self, digest):
        return self.node('GOAL','GOAL',digest or 'MISSING','GOAL.md',goal_sha256=digest,
            source_sha256=digest,pinned_sha256=digest,current_sha256=self.goal,
            validity='SOURCE_BOUND' if digest and digest==self.goal else 'PENDING_REVALIDATION')

    def node(self, kind, source_id, revision, path, *, scope='PROJECT', **attrs):
        uid = schema.identity(self.project_id, kind, source_id, revision)
        value = {'id':uid,'kind':kind,'project_id':self.project_id,'source_id':source_id,'revision':revision,
            'source_path':path,'source_sha256':self.digest(path,scope),'source_scope':scope,
            'goal_sha256':self.goal,'verified_status':'UNVERIFIED_SOURCE',**attrs}
        if uid in self.nodes and self.nodes[uid] != value: raise ValueError('Conflicting projection node identity')
        self.nodes[uid] = value
        return uid

    def edge(self, left, right, relation, path, *, scope='PROJECT', provenance='STRUCTURED_RECORD',
             verified='UNVERIFIED_SOURCE', **attrs):
        item = {'from':left,'to':right,'relation':relation,'provenance_kind':provenance,'source_path':path,
            'source_sha256':self.digest(path,scope),'source_scope':scope,'scope':'DECLARED_RELATION',
            'verified_status':verified,**attrs}
        self.edges[canonical_hash(item)] = item

    def source(self, relative, expected=None):
        try: _safe_reference(self.project, relative)
        except ValueError:
            self.gaps.add('UNSAFE_SOURCE_REFERENCE:' + str(relative)); return None
        actual = self.digest(relative)
        expected = expected or actual
        if not actual: self.gaps.add('SOURCE_UNAVAILABLE:' + relative)
        valid = bool(actual and actual == expected)
        file_id = self.node('EVIDENCE_FILE',relative,1,relative)
        version = self.node('SOURCE_VERSION',relative,expected or 'MISSING',relative,
            pinned_sha256=expected,current_sha256=actual,
            validity='SOURCE_BOUND' if valid else 'PENDING_REVALIDATION')
        self.edge(version,file_id,'DERIVED_FROM',relative,verified='SOURCE_BOUND' if valid else 'PENDING_REVALIDATION')
        return version


def derive(controller, project):
    controller, project = Path(controller).resolve(), Path(project).resolve()
    # Enforce registered local identity, without initializing any runtime file.
    from supervision_ledger import home
    home(controller, project)
    manifest = _manifest(controller, project); g = _Graph(controller, project, manifest)
    project_node = g.node('PROJECT',g.project_id,1,'PROJECT.json')
    goal_node = g.goal_version(g.goal)
    g.edge(project_node,goal_node,'REQUIRES','PROJECT.json')
    if not g.goal: g.gaps.add('MISSING_GOAL')
    problem_nodes, obligation_nodes = {}, {}
    pool = problem_compiler.pool(project)
    if pool.get('schema_version') != 1: raise ValueError('Unsupported problem registry')
    if not pool['problems']: g.gaps.add('NO_COMPILED_PROBLEMS')
    for problem in pool['problems']:
        for revision in problem['revisions']:
            version = revision['version']; spec = revision['spec']
            from engine.common import fresh
            valid = (canonical_hash(spec)==revision['spec_sha256'] and revision['goal_sha256']==g.goal
                     and fresh(project,revision['source_bindings']))
            uid = g.node('PROBLEM_VERSION',problem['id'],version,PROBLEMS,problem_id=problem['id'],
                problem_version=version,statement=spec['statement'],goal_sha256=revision['goal_sha256'],
                validity='SOURCE_BOUND' if valid else 'PENDING_REVALIDATION',spec_sha256=revision['spec_sha256'])
            problem_nodes[(problem['id'],version)] = uid
            frozen_goal = g.goal_version(revision['goal_sha256'])
            g.edge(uid,frozen_goal,'REQUIRES',PROBLEMS)
            for obligation in spec['obligations']:
                key = (problem['id'],version,obligation['id'])
                oid = g.node('OBLIGATION',problem['id']+'/'+str(version)+'/'+obligation['id'],version,PROBLEMS,
                    obligation_id=obligation['id'],problem_id=problem['id'],problem_version=version,
                    statement=obligation['statement'],goal_sha256=revision['goal_sha256'],
                    validity='SOURCE_BOUND' if valid else 'PENDING_REVALIDATION')
                obligation_nodes[key] = oid; g.edge(oid,uid,'REQUIRES',PROBLEMS)
    records = claims.read(project)
    if not records: g.gaps.add('NO_CANONICAL_CLAIMS')
    claim_nodes = {}
    for item, status, current in records:
        spec = item['spec']; key = (item['id'],item['revision'])
        claim_nodes[key] = g.node('CLAIM_REVISION',item['id'],item['revision'],CLAIMS,
            **{k:v for k,v in status.items() if k not in {'id','revision','spec_sha256'}},
            claim_id=item['id'],claim_revision=item['revision'],current=current,spec_sha256=item['spec_sha256'],
            # The stable graph ID is not the local status.id.
            goal_sha256=item['binding']['files'].get('GOAL.md'),verified_status=status['proof_status'])
    for item, status, current in records:
        uid = claim_nodes[(item['id'],item['revision'])]; spec = item['spec']
        for oid in spec['obligation_ids']:
            target = obligation_nodes.get((spec['problem_id'],spec['problem_version'],oid))
            if target: g.edge(uid,target,'REQUIRES',CLAIMS,provenance='CANONICAL_CLAIM')
            else: g.gaps.add('UNMAPPED_OBLIGATION:'+item['id']+':'+oid)
        for dep, pin in item['dependency_pins'].items():
            target = claim_nodes.get((dep,pin['revision']))
            if target and g.nodes[target]['spec_sha256'] != pin['spec_sha256']:
                g.gaps.add('CLAIM_PIN_DIGEST_MISMATCH:'+dep+':'+str(pin['revision'])); continue
            if target: g.edge(uid,target,'REQUIRES',CLAIMS,provenance='CANONICAL_DEPENDENCY_PIN',
                verified='PENDING_REVALIDATION' if status['invalidation_reasons'] else 'UNVERIFIED_SOURCE',pin=copy.deepcopy(pin))
            else: g.gaps.add('MISSING_CLAIM_REVISION:'+dep+':'+str(pin['revision']))
        for relative, expected in item['evidence'].items():
            source = g.source(relative,expected)
            if source: g.edge(source,uid,'SUPPORTS',CLAIMS,provenance='CANONICAL_EVIDENCE_PIN',
                verified='PENDING_REVALIDATION' if g.digest(relative)!=expected else status['proof_status'],
                evidence_sha256=expected)
        for kind, review in item.get('reviews',{}).items():
            for relative, expected in review.get('evidence',{}).items():
                source = g.source(relative,expected)
                review_status = (status.get('novelty_status') if kind=='novelty' else
                    status.get('formal_status','HISTORICAL_NOT_REVALIDATED') if kind=='formal_audit' else status['proof_status'])
                if g.digest(relative)!=expected: review_status = 'PENDING_REVALIDATION'
                if source: g.edge(uid,source,'REVIEWED_BY',CLAIMS,provenance='CANONICAL_REVIEW_RECEIPT',
                    verified=review_status,review_kind=kind,evidence_sha256=expected)
        for field in ('counterexample_receipt','formal_receipt'):
            receipt = item.get(field)
            if not receipt: continue
            rid = g.node('SOURCE_VERSION','claim/'+item['id']+'/'+str(item['revision'])+'/'+field,
                canonical_hash(receipt),CLAIMS,record_kind=field,
                claim_id=item['id'],claim_revision=item['revision'],
                applicability={'assumptions':spec['assumptions'],'machine_statement':spec.get('machine_statement'),
                    'claim_spec_sha256':item['spec_sha256'],'machine_statement_sha256':receipt.get('machine_statement_sha256'),
                    'source_bindings':receipt.get('source_bindings'),
                    'witness':receipt.get('witness'),'bounds':receipt.get('bounds'),'receipt_scope':receipt.get('scope'),
                    'scope':'MACHINE_STATEMENT_ONLY' if field=='counterexample_receipt' else 'DECLARED_FORMAL_STATEMENT_ONLY'},
                verified_status='TOOL_RECEIPT_NOT_PROOF',tool_status=receipt.get('status'))
            refuted = field=='counterexample_receipt' and 'MACHINE_STATEMENT_REFUTED' in status['invalidation_reasons']
            if refuted: g.edge(rid,uid,'REFUTES',CLAIMS,provenance='CANONICAL_COUNTEREXAMPLE_STATUS',verified='MACHINE_STATEMENT_REFUTED')
            else: g.edge(uid,rid,'USES_SOURCE',CLAIMS,provenance='CANONICAL_TOOL_RECEIPT')
    # Reuse the existing read-only view, never its refresh or temporary timestamps.
    view = knowledge_graph.status(project)
    g.gaps.update('LEGACY_INDEX:'+str(e) for e in view['index_errors'])
    if not any(n['kind']=='paper' for n in view['memory_nodes']): g.gaps.add('NO_PAPER_REGISTRY')
    from engine.claim_graph import load
    from engine.knowledge_history import historical_nodes
    raw_graph = load(project)
    memory_goals = {(n['id'],n['revision']):n.get('goal_sha256')
        for current in raw_graph.get('memory',{}).get('nodes',[]) for n in [current,*current.get('history',[])]}
    memories = view['memory_nodes'] + [n for n in historical_nodes(raw_graph) if n['kind']!='claim']
    memory_ids = {}
    for memory in memories:
        refs = memory.get('sources',[])
        if not refs: g.gaps.add('UNMAPPED_MEMORY:'+memory['id']); continue
        path = refs[0]['path']
        try: _safe_reference(project,path)
        except ValueError: g.gaps.add('UNSAFE_MEMORY_SOURCE:'+memory['id']); continue
        kind = {'failed_path':'FAILED_BRANCH','obligation':'OBLIGATION'}.get(memory['kind'],'SOURCE_VERSION')
        metadata = memory.get('metadata',memory.get('spec',{}).get('metadata',{}))
        text_reference = kind=='FAILED_BRANCH' and path.endswith('.md')
        mid = g.node(kind,'memory/'+memory['id'],memory['revision'],path,
            memory_id=memory['id'],current=not memory.get('historical',False),
            title=memory['title'],record_kind=memory['kind'],validity=memory['validity'],
            goal_sha256=memory_goals.get((memory['id'],memory['revision']),memory.get('goal_sha256',g.goal)),
            invalidation_reasons=memory.get('invalidation_reasons',['HISTORICAL_REVISION_NOT_REVALIDATED']),parent_id=None,
            spec_sha256=memory.get('spec_sha256'),origin_role=metadata.get('index_role'),
            verified_status='UNVERIFIED_TEXT_REFERENCE' if text_reference else 'UNVERIFIED_SOURCE')
        memory_ids[(memory['id'],memory['revision'])] = mid
        if text_reference: g.gaps.add('UNMAPPED_TEXT_RELATIONS:'+path)
        for ref in refs:
            source = g.source(ref['path'],ref['sha256'])
            if source: g.edge(mid,source,'USES_SOURCE',path,provenance='LEGACY_SOURCE_BINDING',
                verified='PENDING_REVALIDATION' if memory['validity']!='SOURCE_BOUND' else 'UNVERIFIED_SOURCE',
                locator=ref.get('locator'),evidence_sha256=ref['sha256'])
    # Only explicit existing dependencies are imported, never narrative headings.
    for edge in view['edges']:
        if edge['relation'] != 'depends_on' or not edge['from'].startswith('memory:'): continue
        source = next((n for n in view['memory_nodes'] if n['id']==edge['from'][7:]),None)
        left = memory_ids.get((source['id'],source['revision'])) if source else None
        pin = edge.get('pin') or {}
        right = memory_ids.get((edge['to'][7:],pin.get('revision'))) if edge['to'].startswith('memory:') else None
        if left and right:
            if g.nodes[right]['spec_sha256'] != pin.get('spec_sha256'):
                g.gaps.add('MEMORY_PIN_DIGEST_MISMATCH:'+edge['to']); continue
            text = g.nodes[left]['verified_status']=='UNVERIFIED_TEXT_REFERENCE'
            g.edge(left,right,'DERIVED_FROM' if text else 'REQUIRES',CLAIMS,
                   provenance='TEXT_CONTAINMENT' if text else 'LEGACY_MEMORY_DEPENDENCY_PIN',pin=pin,
                   verified='PENDING_REVALIDATION' if g.nodes[left]['validity']!='SOURCE_BOUND' else 'UNVERIFIED_SOURCE')
        elif left: g.gaps.add('UNMAPPED_MEMORY_DEPENDENCY:'+edge['to'])
    for item, _, _ in records:
        for dep,pin in item.get('knowledge_pins',{}).items():
            target = memory_ids.get((dep,pin.get('revision')))
            if target and g.nodes[target]['spec_sha256']==pin.get('spec_sha256'):
                g.edge(claim_nodes[(item['id'],item['revision'])],target,'REQUIRES',CLAIMS,
                       provenance='CANONICAL_KNOWLEDGE_PIN',pin=pin)
            else: g.gaps.add('UNMAPPED_CLAIM_MEMORY_PIN:'+dep)
    for memory in memories:
        if not memory.get('historical'): continue
        left = memory_ids.get((memory['id'],memory['revision']))
        if not left: continue
        for dep,pin in memory.get('dependency_pins',{}).items():
            right = memory_ids.get((dep,pin.get('revision')))
            if right and g.nodes[right]['spec_sha256']==pin.get('spec_sha256'):
                text = g.nodes[left]['verified_status']=='UNVERIFIED_TEXT_REFERENCE'
                g.edge(left,right,'DERIVED_FROM' if text else 'REQUIRES',CLAIMS,
                       provenance='TEXT_CONTAINMENT' if text else 'HISTORICAL_MEMORY_DEPENDENCY_PIN',
                       pin=pin,verified='PENDING_REVALIDATION')
            else: g.gaps.add('UNMAPPED_HISTORICAL_MEMORY_PIN:'+dep)
    from . import sources
    sources.project(g,claim_nodes)
    _trajectory(g, problem_nodes)
    after = _manifest(controller, project)
    if after != manifest: raise ValueError('SOURCE_CHANGED_DURING_BUILD')
    graph = {'schema_version':schema.SCHEMA_VERSION,'builder_version':schema.BUILDER_VERSION,
        'project_id':g.project_id,'source_manifest':manifest,'input_sha256':canonical_hash(manifest),
        'nodes':sorted(g.nodes.values(),key=lambda n:n['id']),
        'edges':sorted(g.edges.values(),key=canonical_hash),'coverage_gaps':sorted(g.gaps),
        'authority':'Derived cache; claim_graph.status remains the scientific authority'}
    graph['graph_sha256'] = canonical_hash(graph)
    return schema.validate(graph)


def _trajectory(g, problems):
    route_path = 'state/routes/'+g.project_id+'.json'
    route = configuration.load_json(_path(g.controller,route_path),{})
    run_ids = {e['run_id'] for e in route.get('events',[]) if e.get('type') in {'RESEARCH_ROUND','ROUTE_REVIEW'} and e.get('run_id')}
    epochs = {}
    for epoch in route.get('epochs',[]):
        for run in epoch.get('counted_run_ids',[]): run_ids.add(run); epochs.setdefault(run,epoch)
    for run in sorted(run_ids):
        epoch = epochs.get(run,{})
        uid = g.node('RESEARCH_RUN',run,1,route_path,scope='CONTROLLER',run_id=run,
            route_epoch=epoch.get('epoch'),anchor_id=epoch.get('focus',{}).get('anchor_id'),
            goal_sha256=epoch.get('focus',{}).get('binding',{}).get('goal_sha256'))
        relative = 'reports/'+run+'.md'
        source = g.source(relative)
        if source: g.edge(uid,source,'USES_SOURCE',route_path,scope='CONTROLLER',provenance='ACCEPTED_RUN_RECEIPT')
    if not run_ids: g.gaps.add('NO_ROUTE_RECEIPTS')
    path = 'state/discovery/'+g.project_id+'.json'
    data = configuration.load_json(_path(g.controller,path),{})
    if not data.get('attempts'): g.gaps.add('NO_EXPLORATION_RECEIPTS')
    for attempt in data.get('attempts',[]):
        aid = g.node('EXPLORATION_NODE','attempt/'+attempt['id'],1,path,scope='CONTROLLER',
            attempt_id=attempt['id'],status=attempt.get('status'),parent_id=None,
            failure_reason=attempt.get('close_reason'),goal_sha256=attempt.get('binding',{}).get('files',{}).get('GOAL.md'))
        target = problems.get((attempt.get('problem_id'),attempt.get('problem_version')))
        if target: g.edge(aid,target,'REQUIRES',path,scope='CONTROLLER',provenance='FROZEN_ATTEMPT_PROBLEM')
        else: g.gaps.add('UNMAPPED_ATTEMPT_PROBLEM:'+attempt['id'])
        for call in attempt.get('calls',[]):
            failed = call.get('status')=='FAILED'
            cid = g.node('FAILED_BRANCH' if failed else 'EXPLORATION_NODE',
                'attempt/'+attempt['id']+'/call/'+call['run_id'],1,path,scope='CONTROLLER',
                parent_id=aid,run_id=call['run_id'],status=call.get('status'),
                failure_reason=call.get('failure_reason') or ('Research call was rejected; see original receipt' if failed else None))
            g.edge(cid,aid,'DERIVED_FROM',path,scope='CONTROLLER',provenance='EXPLICIT_ATTEMPT_CALL')


def cache_path(controller, project):
    return _path(controller,'state/knowledge/'+configuration.project_id(project)+'/index.json')


def build(controller, project, *, dry_run=False, cache_only=False):
    def perform():
        graph = derive(controller,project)
        raw = (json.dumps(graph,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf8')
        if len(raw)>16_000_000: raise ValueError('Projection cache exceeds 16 MB')
        from . import events
        history=events.summary(controller,project)
        if not dry_run:
            import supervision
            if not cache_only: history=events.record(controller,project,graph)
            target = cache_path(controller,project)
            if not target.exists() or target.read_bytes()!=raw: supervision._write(target,raw)
        return {'schema_version':schema.SCHEMA_VERSION,'builder_version':schema.BUILDER_VERSION,'project_id':graph['project_id'],
            'graph_sha256':graph['graph_sha256'],'input_sha256':graph['input_sha256'],
            'node_count':len(graph['nodes']),'edge_count':len(graph['edges']),
            'source_manifest':graph['source_manifest'],'coverage_gaps':graph['coverage_gaps'],'dry_run':dry_run,
            'history':history,'cache_only':cache_only}
    if dry_run: return perform()
    from supervision_scheduler import _locks
    with _locks(controller,project,execution=True):
        with file_lock(_path(controller,'locks/knowledge-'+configuration.project_id(project)+'.lock')):
            return perform()


def status(controller, project):
    graph = derive(controller,project); path = cache_path(controller,project)
    state = 'ABSENT'
    if path.exists():
        try:
            if path.stat().st_size>16_000_000: raise ValueError('Oversized cache')
            cached = schema.validate(configuration.load_json(path))
            state = 'CURRENT' if cached==graph else 'STALE'
        except (ValueError,KeyError,TypeError,OSError,RecursionError): state = 'CORRUPT'
    from . import events
    return {'schema_version':schema.SCHEMA_VERSION,'builder_version':schema.BUILDER_VERSION,'cache_status':state,
        'history':events.summary(controller,project),
        'graph_sha256':graph['graph_sha256'],'node_count':len(graph['nodes']),
        'edge_count':len(graph['edges']),'coverage_gaps':graph['coverage_gaps']}


def explain_claim(controller, project, claim_id, revision=None):
    graph = derive(controller,project)
    matches = [n for n in graph['nodes'] if n['kind']=='CLAIM_REVISION' and n['claim_id']==claim_id
               and (n['claim_revision']==revision if revision is not None else n['current'])]
    if len(matches)!=1: raise ValueError('Unknown or ambiguous canonical claim revision')
    reachable = {matches[0]['id']}
    # Dependencies follow outgoing edges; evidence support follows incoming edges.
    while True:
        added = {e['to'] for e in graph['edges'] if e['from'] in reachable}
        added |= {e['from'] for e in graph['edges'] if e['to'] in reachable and e['relation'] in {'SUPPORTS','REFUTES'}}
        if added <= reachable: break
        reachable |= added
    from . import events,lineage
    return {'schema_version':schema.SCHEMA_VERSION,'project_id':graph['project_id'],'graph_sha256':graph['graph_sha256'],
        'history':events.summary(controller,project),'lineage':lineage.causes(graph,matches[0]),
        'claim':matches[0],'nodes':[n for n in graph['nodes'] if n['id'] in reachable],
        'edges':[e for e in graph['edges'] if e['from'] in reachable and e['to'] in reachable],
        'coverage_gaps':graph['coverage_gaps']}
