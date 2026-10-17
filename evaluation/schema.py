"""Strict data-only R16 contracts and provenance helpers."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
from engine.common import object_hash

CATEGORIES={'THEOREM_COVERAGE','COUNTEREXAMPLE','SECURITY_FLAW','OPEN_BOUNDARY','RESEARCH_DRIFT','STATE_RECOVERY'}
EVALUATOR_VERSION='r16-calibration-v1'
PACKAGE=Path(__file__).resolve().parent
CONTROLLER=PACKAGE.parent
RULE_FILES=['evaluation/schema.py','evaluation/cases.py','evaluation/scoring.py','evaluation/registry.py',
            'evaluation/validate_cases.py','engine/falsification.py','supervision_quality.py']


def sha_file(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical_bytes(value): return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf8')
def root_path(root=None):
    if root is None: return PACKAGE/'benchmarks'
    path=Path(root)
    return path/'evaluation/benchmarks' if (path/'evaluation/benchmarks').is_dir() else path
def digest(value): return object_hash(value)
def is_sha(value): return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) is not None


def safe(base,relative):
    if (not isinstance(relative,str) or not relative or '\\' in relative or ':' in relative
            or any(p in {'','.','..'} for p in relative.split('/')) or relative.startswith('/')):
        raise ValueError('Benchmark paths must be bounded relative public or evaluator paths')
    base=Path(base); path=base/relative
    from runner_core import project_link
    for part in (path,*path.parents):
        if part.exists() and project_link(part): raise ValueError('Linked benchmark input is forbidden')
        if part==base: break
    if not path.resolve().is_relative_to(base.resolve()): raise ValueError('Benchmark input escaped its root')
    return path


def decode(raw):
    try:
        if len(raw)>2_000_000: raise ValueError('Benchmark JSON exceeds its data-only bound')
        def reject(value): raise ValueError('Nonfinite benchmark JSON is forbidden')
        return json.loads(raw.decode('utf8'),parse_constant=reject)
    except (UnicodeError,json.JSONDecodeError) as exc: raise ValueError('Benchmark input missing or malformed') from exc


def read(path):
    try: return decode(Path(path).read_bytes())
    except OSError as exc: raise ValueError('Benchmark input missing or malformed') from exc


def text(value,name):
    if not isinstance(value,str) or not value.strip() or len(value)>20000: raise ValueError('Invalid benchmark '+name)


def strings(value,name,*,empty=False):
    if not isinstance(value,list) or (not empty and not value) or len(value)>200: raise ValueError('Invalid benchmark '+name)
    for item in value: text(item,name)
    if len(set(value))!=len(value): raise ValueError('Duplicate benchmark '+name)


def identity(case_id,version):
    if not isinstance(case_id,str) or not re.fullmatch('BENCH-[A-Z]+-[0-9]{3}',case_id): raise ValueError('Invalid benchmark case ID')
    if type(version) is not int or not 1<=version<=10000: raise ValueError('Invalid benchmark case version')


def evaluator_binding():
    files={name:sha_file(CONTROLLER/name) for name in RULE_FILES}
    return {'version':EVALUATOR_VERSION,'sha256':digest(files),'files':files}


def validate_task(value):
    fields={'schema_version','case_id','version','category','answer_status','source_review_status','author',
            'frozen_goal','public_input','input_sha256','sources','allowed_tools','budget','output_contract'}
    if not isinstance(value,dict) or set(value)!=fields or type(value['schema_version']) is not int or value['schema_version']!=1:
        raise ValueError('Invalid public benchmark task schema')
    identity(value['case_id'],value['version'])
    if value['category'] not in CATEGORIES or value['answer_status'] not in {'KNOWN','OPEN'}: raise ValueError('Invalid benchmark category/status')
    if (value['category']=='OPEN_BOUNDARY')!=(value['answer_status']=='OPEN'): raise ValueError('OPEN cases only score problem boundaries')
    if value['source_review_status']!='SYNTHETIC_EXPLICIT': raise ValueError('Uncurated real-source cases are not supported by this fixture evaluator')
    text(value['author'],'author'); text(value['frozen_goal'],'frozen goal')
    if not isinstance(value['public_input'],dict) or value['input_sha256']!=digest(value['public_input']): raise ValueError('Public input SHA mismatch')
    if not isinstance(value['sources'],list) or not value['sources'] or len(value['sources'])>30: raise ValueError('Benchmark requires exact source evidence')
    for item in value['sources']:
        if (not isinstance(item,dict) or set(item)!={'id','version','file','sha256','locator','kind'}
                or not is_sha(item['sha256']) or item['kind'] not in {'SYNTHETIC_WRITTEN_DERIVATION','SYNTHETIC_DATA_TRACE','EXISTING_FIXTURE_ADAPTER'}):
            raise ValueError('Invalid benchmark source pin')
        for key in ('id','version','file','locator'): text(item[key],'source '+key)
    strings(value['allowed_tools'],'allowed tools')
    if set(value['budget'])!={'model_calls','tool_calls','wall_seconds'} or value['budget']['model_calls']!=0:
        raise ValueError('Calibration fixtures cannot dispatch models')
    for number in value['budget'].values():
        if type(number) is not int or not 0<=number<=10000: raise ValueError('Invalid calibration resource bound')
    if not isinstance(value['output_contract'],dict) or set(value['output_contract'])!={'format','required_fields','scope'}:
        raise ValueError('Invalid public output contract')
    if value['output_contract']['format']!='JSON': raise ValueError('Only data-only JSON responses are accepted')
    strings(value['output_contract']['required_fields'],'response fields'); text(value['output_contract']['scope'],'response scope')
    return value


def source_bindings(task): return {item['file']:item['sha256'] for item in task['sources']}


def no_private_fields(value):
    """Public schema rejects concealed labels, private paths, and answer digests."""
    if isinstance(value,dict):
        for key,item in value.items():
            if any(part in key.casefold() for part in ('oracle','expected','reference_answer','gold_answer','private_path')):
                raise ValueError('Private grading fields must not enter public benchmark artifacts')
            no_private_fields(item)
    elif isinstance(value,list):
        for item in value: no_private_fields(item)
