"""Retrieval is opt-in, bounded and always local."""
DEFAULTS={'schema_version':1,'enabled':False,'max_context_bytes':32768}


def validate(value):
    if not isinstance(value,dict) or set(value)!=set(DEFAULTS) or type(value['schema_version']) is not int or value['schema_version']!=1:
        raise ValueError('Invalid knowledge_policy keys/schema')
    if type(value['enabled']) is not bool: raise ValueError('knowledge_policy.enabled must be boolean')
    if type(value['max_context_bytes']) is not int or not 2048<=value['max_context_bytes']<=32768:
        raise ValueError('Knowledge context budget must be 2048..32768 bytes')
    return value
