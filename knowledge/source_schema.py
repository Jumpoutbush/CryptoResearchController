"""Operator supplied locations: data identifiers never certify source truth."""
import re
from supervision_snapshot import _path

REGISTRY = 'literature/source_spans.json'


def digest(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value):
        raise ValueError('Source citation needs a SHA-256')
    return value


def path(project, relative):
    if not isinstance(relative,str) or not relative.startswith('literature/'):
        raise ValueError('Source citation must use a literature path')
    from .build import _safe_reference
    return _safe_reference(project,relative)


def validate(project, obj):
    if not isinstance(obj,dict) or type(obj.get('schema_version')) is not int or obj['schema_version']!=1:
        raise ValueError('Unsupported source span registry')
    if not isinstance(obj.get('spans'),list): raise ValueError('Source spans must be a list')
    seen=set()
    for span in obj['spans']:
        if not isinstance(span,dict) or not isinstance(span.get('id'),str) or not span['id'] or span['id'] in seen:
            raise ValueError('Duplicate/invalid source span identity')
        seen.add(span['id'])
        for key in ('source_file','review_file'): path(project,span.get(key))
        for key in ('sha256','review_sha256'): digest(span.get(key))
        digest(span.get('claim_spec_sha256'))
        if not isinstance(span.get('version'),str) or not span['version'].strip(): raise ValueError('Source version required')
        extract=span.get('extraction',{})
        if not isinstance(extract,dict): raise ValueError('Extraction must be an object')
        path(project,extract.get('source_file')); digest(extract.get('sha256'))
        if not all(isinstance(extract.get(k),str) and extract[k] for k in ('parser','version')):
            raise ValueError('Extraction parser/version required')
        loc=span.get('location')
        if loc is not None:
            if not isinstance(loc,dict) or any(type(loc.get(k)) is not int or loc[k]<1 for k in ('page_start','page_end')):
                raise ValueError('Invalid source location pages')
            if loc['page_end']<loc['page_start'] or loc['page_end']-loc['page_start']>10:
                raise ValueError('Invalid source location range')
            if not all(isinstance(loc.get(k),str) and loc[k].strip() for k in ('theorem','excerpt')):
                raise ValueError('Invalid source location marker/excerpt')
        if 'claim_revision' in span and (type(span['claim_revision']) is not int or span['claim_revision']<1):
            raise ValueError('Invalid citation claim revision')
        old=span.get('supersedes')
        if old is not None:
            if not isinstance(old,dict): raise ValueError('Superseded source must be an object')
            path(project,old.get('source_file')); digest(old.get('sha256'))
            if not isinstance(old.get('version'),str) or not old['version'].strip():
                raise ValueError('Superseded source version required')
    return obj
