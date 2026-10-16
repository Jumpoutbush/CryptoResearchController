"""Read-only comparisons and canonical invalidation explanations, never approval."""
from supervision_contracts import canonical_hash


def _claims(graph):
    return {n['claim_id']:n for n in graph['nodes'] if n['kind']=='CLAIM_REVISION' and n.get('current')}


def source_changes(before,after):
    old={(s['scope'],s['path']):s['sha256'] for s in before['source_manifest']}
    new={(s['scope'],s['path']):s['sha256'] for s in after['source_manifest']}
    removed=set(old)-set(new); added=set(new)-set(old); result=[]
    for left in sorted(removed):
        right=next((k for k in sorted(added) if k[0]==left[0] and old[left] and new[k]==old[left]),None)
        if right:
            result.append({'kind':'PATH_RELOCATED','scope':left[0],'before_path':left[1],
                'after_path':right[1],'before_sha256':old[left],'after_sha256':new[right]})
            added.remove(right)
        else: result.append({'kind':'SOURCE_REMOVED','scope':left[0],'before_path':left[1],
                'after_path':None,'before_sha256':old[left],'after_sha256':None})
    for right in sorted(added):
        result.append({'kind':'SOURCE_ADDED','scope':right[0],'before_path':None,
            'after_path':right[1],'before_sha256':None,'after_sha256':new[right]})
    for key in sorted(set(old)&set(new)):
        if old[key]!=new[key]: result.append({'kind':'CONTENT_CHANGED','scope':key[0],
            'before_path':key[1],'after_path':key[1],'before_sha256':old[key],'after_sha256':new[key]})
    return result


def _state(node):
    if node is None: return None
    return {k:node.get(k) for k in ('id','claim_id','claim_revision','spec_sha256','proof_status',
        'novelty_status','formal_status','accepted_contribution','invalidation_reasons','source_path','source_sha256')}


def lost_scopes(before,after):
    if not before or not after: return []
    result=[]
    for field,label,value in (('proof_status','PROOF','INDEPENDENTLY_REVIEWED'),
            ('novelty_status','NOVELTY','REVIEWED_THEORETICAL_CONTRIBUTION'),
            ('formal_status','FORMAL','AUDITED_TOOL_CHECK'),('accepted_contribution','CONTRIBUTION',True)):
        if before.get(field)==value and after.get(field)!=value: result.append(label)
    if after.get('invalidation_reasons')!=before.get('invalidation_reasons') and after.get('invalidation_reasons'):
        result.append('CANONICAL_DEPENDENCY_OR_EVIDENCE')
    return result


def compare(before,after):
    old,new=_claims(before),_claims(after); affected=[]
    for cid in sorted(set(old)|set(new)):
        a,b=_state(old.get(cid)),_state(new.get(cid))
        # The enclosing CLAIM_GRAPH file changes for unrelated reviews too. Its
        # digest is provenance, not a new invalidation of every already-pending claim.
        logical=lambda x:{k:v for k,v in x.items() if k!='source_sha256'} if x else None
        if logical(a)!=logical(b): affected.append({'claim_id':cid,'before':a,'after':b,'lost_scopes':lost_scopes(a,b),
            'reasons':b['invalidation_reasons'] if b else ['CURRENT_CLAIM_UNAVAILABLE']})
    # Every node and relation remains traceable by exact content identity.
    a={n['id']:n for n in before['nodes']}; b={n['id']:n for n in after['nodes']}
    fields=('validity','location_status','review_status','verified_status','invalidation_reasons')
    affected_nodes=[{'id':k,'kind':b[k]['kind'],'before':{f:a[k].get(f) for f in fields},
        'after':{f:b[k].get(f) for f in fields}} for k in sorted(set(a)&set(b))
        if b[k]['kind']!='CLAIM_REVISION' and any(a[k].get(f)!=b[k].get(f) for f in fields)]
    ae={canonical_hash(e):e for e in before['edges']}; be={canonical_hash(e):e for e in after['edges']}
    return {'status':'OK','from_index':before['graph_sha256'],'to_index':after['graph_sha256'],
        'affected_claims':affected,'affected_nodes':affected_nodes,'source_changes':source_changes(before,after),
        'added_node_ids':sorted(set(b)-set(a)),'removed_node_ids':sorted(set(a)-set(b)),
        'changed_node_ids':sorted(k for k in set(a)&set(b) if a[k]!=b[k]),
        'added_edges':[be[k] for k in sorted(set(be)-set(ae))],
        'removed_edges':[ae[k] for k in sorted(set(ae)-set(be))],
        'scientific_discovery':False,'authority':'Original claim_graph.status; content differences are not scientific discoveries'}


def causes(graph,claim):
    current=_claims(graph); nodes={n['id']:n for n in graph['nodes']}; outgoing={}
    memory={n['memory_id']:n for n in graph['nodes'] if n.get('memory_id') and n.get('current')}
    for e in graph['edges']: outgoing.setdefault(e['from'],[]).append(e)
    def evidence(node):
        refs=[]
        for e in graph['edges']:
            source=None
            if e['to']==node['id'] and e['relation']=='SUPPORTS': source=nodes[e['from']]
            elif e['from']==node['id'] and e['relation'] in {'USES_SOURCE','REVIEWED_BY'}: source=nodes[e['to']]
            if source and source['kind']=='SOURCE_VERSION': refs.append({'relation':e['relation'],
                'review_kind':e.get('review_kind'),'source_file':source['source_path'],
                'pinned_sha256':source.get('pinned_sha256'),'current_sha256':source.get('current_sha256'),
                'binding_matches':bool(source.get('pinned_sha256') and source.get('pinned_sha256')==source.get('current_sha256')),
                'verified_status':e['verified_status']})
        return refs
    # Iterative, bounded traversal follows observed canonical dependencies as well
    # as displaying the exact old pin. It never replaces that pin in the graph.
    stack=[(claim,[],frozenset())]; paths=[]; truncated=False; steps=0
    while stack:
        node,prefix,seen=stack.pop(); steps+=1
        if steps>4096 or len(prefix)>128: truncated=True; break
        is_claim=node['kind']=='CLAIM_REVISION'
        cid=node['claim_id'] if is_claim else node['memory_id']; key=('claim' if is_claim else 'memory',cid)
        state=_state(node) if is_claim else {k:node.get(k) for k in ('id','memory_id','revision','spec_sha256','validity','invalidation_reasons','source_path','source_sha256')}
        id_field='claim_id' if is_claim else 'memory_id'
        if key in seen:
            paths.append(prefix+[{id_field:cid,'reason':'UNRESOLVED_DEPENDENCY_CYCLE'}]); continue
        reasons=node.get('invalidation_reasons',[])
        if not reasons:
            paths.append(prefix+[{id_field:cid,'reason':'CANONICAL_STATUS:'+node.get('proof_status',node.get('validity','UNVERIFIED')),
                'state':state,'evidence':evidence(node)}]); continue
        for reason in reasons:
            step={id_field:cid,'reason':reason,'state':state}
            if reason.startswith('REVALIDATION_REQUIRED:'):
                scope=reason.split(':',1)[1]
                step['persisted_revocation']=node.get('revocation_latches',{}).get(scope)
            if reason.startswith(('DEPENDENCY_REVISED:','DEPENDENCY_NOT_VALID:','DEPENDENCY_MISSING:',
                    'KNOWLEDGE_REVISED:','KNOWLEDGE_NOT_VALID:','KNOWLEDGE_MISSING:')):
                dep=reason.split(':',1)[1]; use_memory=not is_claim or reason.startswith('KNOWLEDGE_')
                parent=(memory if use_memory else current).get(dep); field='memory_id' if use_memory else 'claim_id'
                edge=next((e for e in outgoing.get(node['id'],[]) if e['relation']=='REQUIRES'
                    and nodes[e['to']].get(field)==dep),None)
                step.update(dependency_id=dep,pinned=edge.get('pin') if edge else None,
                    pinned_node_id=edge['to'] if edge else None,
                    observed={'revision':parent.get('claim_revision',parent['revision']),'spec_sha256':parent['spec_sha256']} if parent else None)
                if parent: stack.append((parent,prefix+[step],seen|{key})); continue
            step['evidence']=evidence(node)
            paths.append(prefix+[step])
    return {'authority':'Original current claim_graph.status, with exact historical pins',
        'cause_paths':paths,'truncated':truncated,'history_is_not_approval':True}
