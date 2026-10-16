"""Textual assumption mapping never grants mathematical or security equivalence."""
FIELDS=('model','domain','quantifiers','assumptions','parameters','adversary','leakage')


def validate_model(model):
    if not isinstance(model,dict) or set(model)!=set(FIELDS): raise ValueError('Invalid sharing model fields')
    for key,value in model.items():
        values=value if key=='assumptions' else [value]
        if not isinstance(values,list) or len(values)>32 or (key!='assumptions' and len(values)!=1):
            raise ValueError('Invalid sharing model '+key)
        if any(not isinstance(v,str) or not v.strip() or len(v)>2048 for v in values):
            raise ValueError('Invalid sharing model '+key)
    return model


def compare(origin,destination):
    validate_model(origin); validate_model(destination)
    mapping=[{'field':key,'origin':origin[key],'destination':destination[key],
        'status':'EXACT_TEXT_MATCH' if origin[key]==destination[key] else 'DIFFERENT_REQUIRES_REVIEW'} for key in FIELDS]
    reasons=[m['field'].upper()+'_MISMATCH' for m in mapping if m['status']!='EXACT_TEXT_MATCH']
    return {'status':'MODEL_MISMATCH_REVIEW_REQUIRED' if reasons else 'EXACT_TEXT_MAPPING_REVIEW_PENDING',
        'mapping':mapping,'reasons':reasons,'semantically_equivalent':False,'independent_destination_review_required':True,
        'basis':'OPERATOR_DECLARED_TEXT_NOT_INFERRED_SECURITY_EQUIVALENCE'}
