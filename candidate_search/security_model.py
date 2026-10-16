"""R14 protocol obligation cards are declarations, never security certificates."""
from __future__ import annotations
import copy
from pathlib import Path
import configuration
from engine.common import object_hash
from research_quality import hash_file
from . import catalog, validate
from .verifiers import interface as verification

FRAMEWORKS=('MALICIOUS_MPC','AUTHENTICATED_PIR','ZK_COMPOSITION')


def template():
    """Unknown values stay explicit; a template never passes independent review."""
    return {'schema_version':1,'proof_paths':[],
        'security_game':{'id':'GAME-main','definition':None,'rounds':None,'public_outputs':[]},
        'parties':[],
        'corruption_model':{'timing':None,'claimed_timing':None,'threshold':None,'claimed_threshold':None,
                            'corrupted_parties':[],'dropout_model':None},
        'leakage_function':{'name':None,'real_observable':[],'ideal_leakage':[],'cross_round_linkage':None},
        'setup_assumptions':[],
        'abort_behavior':{'public_reject_bit':None,'ideal_reject_bit':None,'forking_visible':None,'dropout_visible':None},
        'simulator_interface':{'ideal_inputs':[],'required_inputs':[],'authorized_programming':[],
            'required_programming':[],'output_dependencies':{}},
        'reduction_loss':{'parameters':[],'bit_widths':{},'rounds':None,'failure_events':[],
                          'loss_bound':None,'cost_breakdown':[]},
        'composition_scope':{'sessions':None,'rounds':None,'cross_round_collusion':None,
                              'component_theorems':[],'end_to_end_reduction':None},
        'dependencies':[],
        'baseline_comparison':[{'framework':name,'assumptions':None,'functionality':None,
            'cost':None,'difference':None,'source_span_ids':[],'relation':'UNRESOLVED'} for name in FRAMEWORKS],
        'attack_traces':[]}


def _object(value,keys,name):
    if not isinstance(value,dict) or set(value)!=set(keys): raise ValueError('Invalid '+name+' fields')


def _text(value,name,*,nullable=False):
    if nullable and value is None: return
    if not isinstance(value,str) or not value.strip() or len(value)>16000: raise ValueError('Invalid '+name+' text')


def _strings(value,name):
    if not isinstance(value,list) or len(value)>100: raise ValueError('Invalid '+name+' list')
    for item in value: _text(item,name)
    if len(value)!=len(set(value)): raise ValueError('Duplicate '+name)


def _integer(value,name,*,nullable=True):
    if nullable and value is None: return
    if type(value) is not int or not 0<=value<=1000000: raise ValueError('Invalid '+name+' integer')


def ideal_interface_binding(card):
    """Explicit user-frozen game/interface authority, never inferred from prose.

    Store object_hash(this object) as ideal_interface_sha256 in an existing
    operator-owned fixed problem/candidate model. This function writes nothing.
    Simulator *requirements* remain separate proof obligations, not authority.
    """
    return {'security_game':copy.deepcopy(card['security_game']),'parties':copy.deepcopy(card['parties']),
        'corruption_scope':{k:card['corruption_model'][k] for k in ('timing','threshold','dropout_model')},
        'leakage_function':copy.deepcopy(card['leakage_function']),'abort_behavior':copy.deepcopy(card['abort_behavior']),
        'simulator_authorization':{k:copy.deepcopy(card['simulator_interface'][k])
            for k in ('ideal_inputs','authorized_programming')},
        'composition_scope':{k:card['composition_scope'][k] for k in ('sessions','rounds','cross_round_collusion')}}


def validate_card(card):
    """Validate a bounded data schema; missing science is preserved as unknown."""
    expected=template(); _object(card,expected,'security card')
    if type(card['schema_version']) is not int or card['schema_version']!=1: raise ValueError('Security card schema_version must be 1')
    import json
    if len(json.dumps(card,ensure_ascii=False).encode('utf8'))>160000: raise ValueError('Security obligation card exceeds 160 KB')
    for name in ('proof_paths','parties','setup_assumptions'): _strings(card[name],name)
    game=card['security_game']; _object(game,expected['security_game'],'security_game')
    _text(game['id'],'game id'); _text(game['definition'],'game definition',nullable=True)
    _integer(game['rounds'],'game rounds'); _strings(game['public_outputs'],'public outputs')
    corruption=card['corruption_model']; _object(corruption,expected['corruption_model'],'corruption_model')
    for name in ('timing','claimed_timing'):
        if corruption[name] not in {None,'STATIC','ADAPTIVE'}: raise ValueError('Corruption timing must be STATIC/ADAPTIVE or unknown')
    for name in ('threshold','claimed_threshold'): _integer(corruption[name],name)
    _strings(corruption['corrupted_parties'],'corrupted parties'); _text(corruption['dropout_model'],'dropout model',nullable=True)
    if not set(corruption['corrupted_parties'])<=set(card['parties']): raise ValueError('Corruption names parties outside the game')
    leakage=card['leakage_function']; _object(leakage,expected['leakage_function'],'leakage_function')
    _text(leakage['name'],'leakage function',nullable=True)
    for name in ('real_observable','ideal_leakage'): _strings(leakage[name],name)
    if leakage['cross_round_linkage'] not in {None,'NONE','DEFINED','UNDEFINED'}: raise ValueError('Invalid cross-round linkage')
    abort=card['abort_behavior']; _object(abort,expected['abort_behavior'],'abort_behavior')
    if any(value is not None and type(value) is not bool for value in abort.values()): raise ValueError('Abort visibility must be boolean or unknown')
    simulator=card['simulator_interface']; _object(simulator,expected['simulator_interface'],'simulator_interface')
    for name in ('ideal_inputs','required_inputs','authorized_programming','required_programming'): _strings(simulator[name],name)
    if not isinstance(simulator['output_dependencies'],dict): raise ValueError('Invalid simulator output dependencies')
    for output,inputs in simulator['output_dependencies'].items():
        _text(output,'simulator output'); _strings(inputs,'simulator dependencies')
    loss=card['reduction_loss']; _object(loss,expected['reduction_loss'],'reduction_loss')
    for name in ('parameters','failure_events'): _strings(loss[name],name)
    _text(loss['loss_bound'],'loss bound',nullable=True); _integer(loss['rounds'],'reduction rounds')
    if not isinstance(loss['bit_widths'],dict): raise ValueError('Invalid reduction bit widths')
    for variable,width in loss['bit_widths'].items(): _text(variable,'bit-width variable'); _integer(width,'bit width',nullable=False)
    if not isinstance(loss['cost_breakdown'],list) or len(loss['cost_breakdown'])>100: raise ValueError('Invalid cost breakdown')
    for row in loss['cost_breakdown']:
        _object(row,{'component','operation_count','unit','assumptions'},'cost row')
        for name in row: _text(row[name],'cost '+name)
    composition=card['composition_scope']; _object(composition,expected['composition_scope'],'composition_scope')
    for name in ('sessions','rounds'): _integer(composition[name],name)
    for name in ('cross_round_collusion','end_to_end_reduction'): _text(composition[name],name,nullable=True)
    _strings(composition['component_theorems'],'component theorems')
    if not isinstance(card['dependencies'],list) or len(card['dependencies'])>100: raise ValueError('Invalid theorem dependencies')
    for dependency in card['dependencies']:
        _object(dependency,{'span_id','source_file','version','sha256','location','required_assumptions','used_assumptions','proof_step'},'theorem dependency')
        for name in ('span_id','source_file','version','sha256'): _text(dependency[name],name,nullable=True)
        if dependency['sha256'] is not None:
            from knowledge.source_schema import digest
            digest(dependency['sha256'])
        _text(dependency['proof_step'],'proof step')
        for name in ('required_assumptions','used_assumptions'): _strings(dependency[name],name)
        location=dependency['location']
        if location is not None:
            _object(location,{'page_start','page_end','theorem','excerpt'},'theorem location')
            for name in ('page_start','page_end'): _integer(location[name],name,nullable=False)
            if location['page_start']<1 or not location['page_start']<=location['page_end']<=location['page_start']+10:
                raise ValueError('Invalid original theorem page range')
            for name in ('theorem','excerpt'): _text(location[name],name)
    comparison=card['baseline_comparison']
    if not isinstance(comparison,list) or len(comparison)!=3: raise ValueError('Three standard framework comparisons are required')
    seen=set()
    for row in comparison:
        _object(row,{'framework','assumptions','functionality','cost','difference','source_span_ids','relation'},'framework comparison')
        if row['framework'] not in FRAMEWORKS or row['framework'] in seen: raise ValueError('Invalid or duplicate standard framework')
        seen.add(row['framework'])
        for name in ('assumptions','functionality','cost','difference'): _text(row[name],name,nullable=True)
        _strings(row['source_span_ids'],'framework sources')
        if row['relation'] not in {'UNRESOLVED','DIRECT_COMPOSITION','DIFFERENT'}: raise ValueError('Invalid framework relation')
    traces=card['attack_traces']
    if not isinstance(traces,list) or len(traces)>50: raise ValueError('Invalid finite attack trace list')
    for trace in traces:
        _object(trace,{'id','kind','game','proof_step','affected_obligations','execution','scope','restart_conditions'},'attack trace')
        for name in ('id','game','proof_step','scope','restart_conditions'): _text(trace[name],name)
        if trace['kind'] not in {'CORRUPTION_THRESHOLD','SELECTIVE_REJECTION','SIMULATOR_PUBLIC_OUTPUT'}: raise ValueError('Unsupported data-only attack trace kind')
        _strings(trace['affected_obligations'],'affected obligations')
        if not trace['affected_obligations']: raise ValueError('Attack trace must name at least one fixed proof obligation')
        if not isinstance(trace['execution'],list) or not 1<=len(trace['execution'])<=32: raise ValueError('Attack trace must be a bounded finite list')
        for step in trace['execution']:
            _object(step,{'round','corrupted_parties','public_inputs','secret_assignment','ideal_leakage','public_output'},'trace step')
            _integer(step['round'],'trace round',nullable=False); _strings(step['corrupted_parties'],'trace corrupted parties')
            if not set(step['corrupted_parties'])<=set(card['parties']): raise ValueError('Trace corrupts an unknown party')
            for name in ('public_inputs','secret_assignment','ideal_leakage','public_output'):
                if not isinstance(step[name],dict): raise ValueError('Trace '+name+' must be a plain data object')
                for key,value in step[name].items():
                    _text(key,'trace variable')
                    if not (value is None or type(value) in {str,int,bool}): raise ValueError('Trace values must be fixed primitive data')
    return copy.deepcopy(card)


def _source_checks(project,card):
    """Reuse R07's read-only original-PDF/span/technical-review projection."""
    if not card['dependencies']: return [],{}
    from knowledge.build import derive
    from knowledge.source_schema import path as source_path
    from research_quality import validate_technical_review
    for dependency in card['dependencies']:
        if dependency['source_file'] is not None: source_path(project,dependency['source_file'])
    graph=derive(configuration.ROOT,project)
    nodes=[n for n in graph['nodes'] if n['kind']=='THEOREM_SPAN']
    result=[]; pins={}
    for dependency in card['dependencies']:
        check={'span_id':dependency['span_id'],'source_file':dependency['source_file'],'version':dependency['version'],
               'status':'UNVERIFIED','reason':'NEEDS_SOURCE: exact original version and theorem/page location are required',
               'source_assumptions':[],'proof_step':dependency['proof_step']}
        matches=[]
        if all(dependency.get(key) is not None for key in ('span_id','source_file','version','sha256','location')):
            for node in nodes:
                location=node.get('location') or {}
                if (node.get('source_file')==dependency['source_file'] and node.get('source_version')==dependency['version']
                        and node.get('sha256')==dependency['sha256']
                        and str(node.get('source_id','')).endswith('/'+dependency['span_id'])
                        and all(location.get(k)==v for k,v in dependency['location'].items())):
                    matches.append(node)
        if len(matches)==1:
            node=matches[0]
            check.update(location_status=node['location_status'],review_status=node['review_status'],
                         technical_review_path=node['technical_review_path'],coverage_verdict=node.get('review_status'))
            if node['location_status']=='FULLTEXT_LOCATED' and node.get('review_error') is None:
                review=validate_technical_review(project,node['technical_review_path'])
                assumption=next(row['paper'] for row in review['comparison'] if row['dimension']=='assumptions')
                check.update(status='SOURCE_LOCATION_ONLY',reason='Original version/page located; mathematical premises and implication still require independent review',
                             source_assumptions=[assumption])
            for relative in (node['source_file'],node['technical_review_path'],(node.get('extraction') or {}).get('source_file')):
                if relative: pins[relative]=hash_file(validate.safe(project,relative,roots={'literature'}))
        result.append(check)
    for relative in ('literature/source_spans.json','literature/pdf_index.json','literature/uploads.json'):
        if (project/relative).is_file(): pins[relative]=hash_file(validate.safe(project,relative,roots={'literature'}))
    return result,pins


def prepare_request(project,candidate_id,claim_id,card):
    card=validate_card(card)
    base=verification.prepare_request(project,candidate_id,claim_id,adapter_id='protocol-review-v1')
    pins={}
    for relative in card['proof_paths']:
        pins[relative]=hash_file(validate.safe(project,relative,roots={'proofs'}))
    checks,source_pins=_source_checks(project,card)
    candidate=catalog.show(project,candidate_id)
    from engine import claim_graph
    selected_claim=claim_graph.get(project,claim_id)
    claim_status=next(row for row in claim_graph.status(project)['claims'] if row['id']==claim_id)
    authority_pins={'research/discovery/CLAIM_GRAPH.json':hash_file(validate.safe(project,'research/discovery/CLAIM_GRAPH.json'))}
    for receipt in selected_claim.get('reviews',{}).values():
        for relative in receipt.get('evidence',{}):
            # An already missing/stale independent review remains a gap; its
            # actual presence/bytes are still pinned for subsequent freshness.
            if (project/relative).exists(): authority_pins[relative]=hash_file(validate.safe(project,relative))
            else: authority_pins[relative]=None
    fixed=candidate['problem_binding']['spec']
    root=Path(__file__).resolve().parents[1]
    tool_pins={name:hash_file(catalog._unlinked(root/name)) for name in (
        'candidate_search/security_model.py','candidate_search/security_review.py')}
    value={'schema_version':1,'project_id':base['project_id'],'base_request':base,
        'claim_binding':copy.deepcopy(base['claim_binding']),'card':card,
        'source_hashes':{**base['source_hashes'],**pins,**source_pins},'source_checks':checks,
        'frozen_security_model':copy.deepcopy(fixed.get('security_model',{})),
        'candidate_security_model':copy.deepcopy(candidate['spec']['security_model']),
        'frozen_assumptions':copy.deepcopy(fixed['assumptions']),
        'claim_review_status':copy.deepcopy(claim_status),'authority_hashes':authority_pins,
        'frozen_obligations':copy.deepcopy(fixed['obligations']),'tool_bindings':tool_pins}
    digest=object_hash(value); value['request_sha256']=digest; value['request_id']='SR-'+digest
    return value
