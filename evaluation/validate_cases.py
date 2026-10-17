"""Validate public inputs separately from evaluator-private calibration readiness."""
from . import cases, registry, schema


def validate_dataset(root=None,private_root=None):
    listing=cases.list_cases(root); rows=[]; categories=set()
    for item in listing['cases']:
        view=cases.public_view(item['case_id'],item['version'],root); task=view['task']; categories.add(task['category'])
        status='PENDING_CURATION'
        if private_root is not None:
            from .scoring import validate_oracle
            try:
                _,document=registry.get(private_root,item['case_id'],version=item['version'],root=root)
                validate_oracle(task,document['oracle']); status='CALIBRATION_READY'
            except (ValueError,OSError,KeyError,TypeError): status='PENDING_CURATION'
        rows.append({'case_id':item['case_id'],'version':item['version'],'category':item['category'],'status':status})
    if categories!=schema.CATEGORIES: raise ValueError('Dataset must cover all six distinct research evaluation categories')
    return {'schema_version':1,'status':'CALIBRATION_READY' if all(r['status']=='CALIBRATION_READY' for r in rows) else 'PENDING_CURATION',
        'public_validation':'PASS','cases':rows,'formal_counted':False,'formal_benchmark_available':False,
        'benchmark_agent_isolation':'NOT_ISOLATED','agent_execution_allowed':False,'quality_gain':'NOT_MEASURED'}
