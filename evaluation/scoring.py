"""Independent data-only fixture scoring; no model, Lean, or candidate execution."""
from __future__ import annotations
import copy
from engine.falsification import check_witness
from engine.common import identifier
import supervision_quality
from . import cases, schema


def _drift(task):
    data=task['public_input']
    result=supervision_quality.assess_quality(data['rounds'],core_obligations=data['core_obligations'],anchor_id=data['anchor_id'])
    return {'decision':result['assessment'],'finding_codes':sorted(item['code'] for item in result['findings'])}


def _worlds(task,worlds):
    data=task['public_input']
    if not isinstance(worlds,list) or len(worlds)!=2: return False
    try:
        if not all(check_witness(data['machine_statement'],world)['is_counterexample'] for world in worlds): return False
        return (worlds[0][data['ideal_field']]==worlds[1][data['ideal_field']]
                and worlds[0][data['observed_field']]!=worlds[1][data['observed_field']])
    except (ValueError,KeyError,TypeError,ZeroDivisionError): return False


def _recovery(task):
    data=task['public_input']; before=data['before_image']; after=data['pending_afterimage']
    if (data['before_sha256']!=schema.digest(before) or data['afterimage_sha256']!=schema.digest(after)
            or data['actual_sha256'] not in {data['before_sha256'],data['afterimage_sha256']}):
        raise ValueError('Synthetic recovery material has no exact owned afterimage')
    def indexed(image):
        if not isinstance(image,dict) or set(image)!={'attempts'} or not isinstance(image['attempts'],list):
            raise ValueError('Synthetic recovery owner schema is invalid')
        owners={}; calls={}
        for attempt in image['attempts']:
            if not isinstance(attempt,dict) or 'id' not in attempt or not isinstance(attempt.get('calls'),list):
                raise ValueError('Synthetic recovery owner/call schema is invalid')
            owner=identifier(attempt['id'])
            if owner in owners: raise ValueError('Synthetic recovery owner identity is duplicated')
            owners[owner]=attempt
            for call in attempt['calls']:
                if not isinstance(call,dict) or 'run_id' not in call: raise ValueError('Synthetic recovery call schema is invalid')
                run=identifier(call['run_id'])
                if run in calls: raise ValueError('Synthetic recovery call identity is duplicated')
                if call.get('status') not in {'RESERVED','PENDING_WRAPPER','SETTLING','SETTLEMENT_READY','ACCEPTED','FAILED'}:
                    raise ValueError('Synthetic recovery call phase is unknown')
                calls[run]=(owner,call)
        return owners,calls
    old_owners,old=indexed(before); new_owners,new=indexed(after)
    if set(old_owners)!=set(new_owners): raise ValueError('Synthetic reservation recovery cannot replace original owner identity')
    for owner,attempt in old_owners.items():
        if schema.digest({k:v for k,v in attempt.items() if k!='calls'})!=schema.digest({k:v for k,v in new_owners[owner].items() if k!='calls'}):
            raise ValueError('Synthetic recovery cannot rewrite original owner payload')
    if not set(old)<=set(new) or not new: raise ValueError('Synthetic recovery material discards original consumption')
    for run,(owner,call) in old.items():
        if new[run][0]!=owner or schema.digest(new[run][1])!=schema.digest(call):
            raise ValueError('Synthetic recovery cannot move or rewrite the original call payload')
    if any(call['status']!='RESERVED' for run,(_,call) in new.items() if run not in old):
        raise ValueError('Synthetic recovery newly recorded calls must remain original unknown reservations')
    return {'decision':'RECOVER_LOCAL_AFTERIMAGE','afterimage_sha256':data['afterimage_sha256'],
            'redispatch':False,'preserved_run_ids':sorted(new)}


def validate_oracle(task,value):
    if (not isinstance(value,dict) or set(value)!={'schema_version','category','evidence','expected'}
            or type(value['schema_version']) is not int or value['schema_version']!=1 or value['category']!=task['category']
            or not isinstance(value['evidence'],dict) or not isinstance(value['expected'],dict)):
        raise ValueError('Invalid evaluator-private curation contract')
    evidence=value['evidence']; expected=value['expected']; category=task['category']; data=task['public_input']
    if category=='THEOREM_COVERAGE':
        if set(evidence)!={'kind','source_file','source_sha256','source_version','locator','mapping','review_note'}:
            raise ValueError('Theorem coverage needs a reviewed exact derivation and full mapping')
        pin=next((s for s in task['sources'] if s['file']==evidence['source_file']),None)
        if (pin is None or evidence['kind']!='CURATED_WRITTEN_DERIVATION' or evidence['source_sha256']!=pin['sha256']
                or evidence['source_version']!=pin['version'] or evidence['locator']!=pin['locator']
                or set(evidence['mapping'])!={'domain','quantifiers','assumptions','input_contract','output_contract','proof_obligations'}
                or evidence['mapping']!=data['candidate_scope'] or expected!={'decision':'COVERED'}):
            raise ValueError('Theorem coverage source, scope, or derivation pins are incomplete')
        schema.text(evidence['review_note'],'independent written derivation review')
        if len(evidence['review_note'].strip())<32: raise ValueError('Written derivation requires explicit independent review rationale')
    elif category=='COUNTEREXAMPLE':
        if set(evidence)!={'kind','witness'} or evidence['kind']!='EXACT_INTEGER_WITNESS' or expected!={'decision':'COUNTEREXAMPLE'}:
            raise ValueError('Counterexample oracle needs an exact predicate witness')
        if not check_witness(data['machine_statement'],evidence['witness'])['is_counterexample']:
            raise ValueError('Hidden integer witness does not refute the exact public predicate')
    elif category=='SECURITY_FLAW':
        if (set(evidence)!={'kind','worlds'} or evidence['kind']!='TWO_TOY_TRANSCRIPTS'
                or not _worlds(task,evidence['worlds']) or expected!={'decision':'LEAKAGE_FOUND'}):
            raise ValueError('Toy security oracle requires same ideal leakage with distinguishable public transcripts')
    elif category=='OPEN_BOUNDARY':
        if (set(evidence)!={'kind','unresolved_obligations'} or evidence['kind']!='OPEN_BOUNDARY_ONLY'
                or evidence['unresolved_obligations']!=data['open_obligations'] or expected!={'decision':'OPEN'}):
            raise ValueError('OPEN curation may only score frozen boundaries and explicit unresolved obligations')
    elif category=='RESEARCH_DRIFT':
        if evidence!={'kind':'ORIGINAL_RECEIPT_REPLAY','adapter':'supervision_quality.assess_quality'} or expected!=_drift(task):
            raise ValueError('Drift curation must match the original deterministic receipt assessor')
    elif category=='STATE_RECOVERY':
        if evidence!={'kind':'FROZEN_LOCAL_AFTERIMAGE'} or expected!=_recovery(task):
            raise ValueError('Recovery curation must preserve exact finite-state afterimage consumption')
    return value


def _checks(task,oracle,response):
    category=task['category']; data=task['public_input']; evidence=oracle['evidence']
    fields={'case_id','version','input_sha256','decision'}
    extra={'THEOREM_COVERAGE':{'source','coverage_mapping'},'COUNTEREXAMPLE':{'witness'},
        'SECURITY_FLAW':{'worlds','recovered_expression','scope'},'OPEN_BOUNDARY':{'frozen_model','unresolved_obligations','proof_status'},
        'RESEARCH_DRIFT':{'finding_codes'},'STATE_RECOVERY':{'afterimage_sha256','redispatch','preserved_run_ids'}}[category]
    if not isinstance(response,dict) or set(response) not in (fields|extra,fields|extra|{'rationale'}):
        return [{'id':'RESPONSE_SCHEMA','passed':False}]
    checks=[{'id':'EXACT_INPUT_BINDING','passed':all(response.get(k)==task[k] and type(response.get(k)) is type(task[k]) for k in ('case_id','version','input_sha256'))},
            {'id':'CURATED_DECISION','passed':response['decision']==oracle['expected']['decision']}]
    def add(name,passed): checks.append({'id':name,'passed':bool(passed)})
    if category=='THEOREM_COVERAGE':
        add('ORIGINAL_SOURCE_POSITION',response['source']=={k:evidence[k] for k in ('source_file','source_sha256','source_version','locator')})
        add('ALL_SCOPE_AXES_PRESERVED',schema.digest(response['coverage_mapping'])==schema.digest(evidence['mapping']))
    elif category=='COUNTEREXAMPLE':
        try: result=check_witness(data['machine_statement'],response['witness']); passed=result['is_counterexample']
        except (ValueError,TypeError,ZeroDivisionError): passed=False
        add('EXACT_PREDICATE_WITNESS',passed)
    elif category=='SECURITY_FLAW':
        add('SAME_IDEAL_DIFFERENT_TRANSCRIPT',_worlds(task,response['worlds']))
        add('EXACT_TOY_RECOVERY_RELATION',response['recovered_expression']==data['recovered_expression'])
        add('TOY_SCOPE_ONLY',response['scope']=='EXACT_TWO_QUERY_TOY_ONLY')
    elif category=='OPEN_BOUNDARY':
        add('FROZEN_MODEL_PRESERVED',schema.digest(response['frozen_model'])==schema.digest(data['frozen_model']))
        add('OPEN_OBLIGATIONS_RETAINED',response['unresolved_obligations']==evidence['unresolved_obligations'])
        add('NO_UNSUPPORTED_PROOF_PROMOTION',response['proof_status']=='UNRESOLVED')
    elif category=='RESEARCH_DRIFT': add('ORIGINAL_FINDING_CODES',response['finding_codes']==oracle['expected']['finding_codes'])
    elif category=='STATE_RECOVERY':
        for key in ('afterimage_sha256','redispatch','preserved_run_ids'):
            add('RECOVERY_'+key.upper(),type(response[key]) is type(oracle['expected'][key]) and response[key]==oracle['expected'][key])
    return checks


def score_fixture(case_id,response,*,private_root,version=None,root=None):
    """No caller isolation flag is accepted. These are calibration receipts."""
    from . import registry
    receipt={'schema_version':1,'case_id':case_id,'version':version,'status':'PENDING_CURATION','checks':[],
        'scope':'OFFLINE_CALIBRATION_FIXTURE_ONLY','scientific_acceptance':False,'quality_gain':'NOT_MEASURED',
        'isolation_status':'NOT_ISOLATED','formal_counted':False,'agent_execution_allowed':False}
    try:
        view=cases.public_view(case_id,version,root); task=view['task']; entry,document=registry.get(private_root,case_id,version=task['version'],root=root)
        oracle=validate_oracle(task,document['oracle']); checks=_checks(task,oracle,response)
        receipt.update(version=task['version'],input_sha256=task['input_sha256'],task_sha256=entry['task_sha256'],
            oracle_sha256=entry['oracle_sha256'],evaluator_version=entry['evaluator_version'],evaluator_sha256=entry['evaluator_sha256'],
            status='PASS' if all(row['passed'] for row in checks) else 'FAIL',checks=checks,
            response_sha256=schema.digest(response))
    except (ValueError,OSError,TypeError,KeyError):
        # Errors never echo private paths, private answers, or expected values.
        receipt.update(status='STALE_OR_INVALID',reason='Exact public, private curation, or evaluator binding is unavailable or changed')
    receipt['receipt_sha256']=schema.digest(receipt); return receipt
