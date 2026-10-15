"""Theory-first implementation gate with operator-owned, hash-bound approvals."""
from __future__ import annotations
import json
from pathlib import Path
from configuration import settings_for
from research_quality import hash_file, local_file, read_object

SYSTEM_PHASES = {'IMPLEMENTATION', 'SYSTEM_TEST', 'EXPERIMENT'}
CODE_SUFFIXES = {'.py','.c','.cpp','.cc','.h','.hpp','.rs','.go','.js','.ts','.tsx','.jsx','.sh','.ps1','.cmd','.java','.cu','.ipynb'}
MATH_ROOTS = ('proofs/checks/', 'experiments/math_checks/')
APPROVAL_PATH = 'research/THEORY_READINESS.json'


def check_readiness(project):
    project = Path(project).resolve()
    record = read_object(project / APPROVAL_PATH)
    if record.get('schema_version') != 1 or record.get('decision') != 'APPROVED':
        raise ValueError('Theory gate has no operator approval')
    for key in ('reviewer','claim_id','reason','approved_at'):
        if not isinstance(record.get(key),str) or not record[key].strip(): raise ValueError('Theory approval missing '+key)
    required = {'contribution','correctness','novelty'}
    evidence = record.get('evidence', {})
    if not isinstance(evidence, dict) or not required <= set(evidence):
        raise ValueError('Approval needs contribution/correctness/novelty evidence')
    for key, item in evidence.items():
        if not isinstance(item,dict): raise ValueError('Invalid approval evidence')
        path = local_file(project,item.get('file'),roots={'proofs','research','literature'})
        if path.relative_to(project).as_posix() == APPROVAL_PATH: raise ValueError('Approval cannot certify itself')
        if hash_file(path) != item.get('sha256'): raise ValueError('Approved '+key+' evidence changed; theory review is stale')
    if hash_file(project/'GOAL.md') != record.get('goal_sha256'):
        raise ValueError('Goal changed after theory approval')
    inputs = record.get('inputs', {})
    if not isinstance(inputs, dict): raise ValueError('Invalid approval input binding')
    present_inputs={p.relative_to(project).as_posix():hash_file(p) for p in (project/'inputs').rglob('*') if p.is_file()}
    if present_inputs != inputs: raise ValueError('User inputs changed after theory approval')
    constraints=record.get('constraint_files',{})
    if not isinstance(constraints,dict): raise ValueError('Invalid constraint binding')
    names=('AGENTS.md','RESEARCH_PROFILE.json','research/THREAT_MODEL.md','research/SECURITY_MODEL.md','research/SECURITY_DEFINITIONS.md')
    present_constraints={name:hash_file(project/name) for name in names if (project/name).is_file()}
    if present_constraints != constraints: raise ValueError('Security/model constraints changed after theory approval')
    state=read_object(project/'research/STATE.json')
    if state.get('research_route') != record.get('research_route'):
        raise ValueError('Research route changed after theory approval')
    pins={'selected_idea':state.get('selected_idea'),'supporting_ideas':state.get('supporting_ideas',[])}
    if pins != record.get('idea_pins'): raise ValueError('Idea versions changed after theory approval')
    if record.get('remaining_critical_obligations') != []:
        raise ValueError('Critical theoretical obligations remain open')
    from engine.claim_graph import require_theory_claim
    discovery = require_theory_claim(project, record['claim_id'])
    if discovery and record.get('discovery_claim_sha256') != discovery['spec_sha256']:
        raise ValueError('Theory approval does not bind the current discovery claim')
    return record


def require_system_ready(project):
    if not settings_for(project)['research_policy']['theory_first']: return None
    try: return check_readiness(project)
    except (OSError, ValueError, KeyError) as exc:
        raise ValueError('THEORY_GATE_BLOCKED: 系统实现/测试前，须由用户确认理论贡献与正确性，并登记具体证据。'+str(exc)) from exc


def validate_code_changes(project, baseline):
    """Reject system implementation before approval; bound minimal math checks."""
    policy=settings_for(project)['research_policy']
    if not policy['theory_first']: return []
    try:
        check_readiness(project)
        return []
    except (OSError, ValueError, KeyError): pass
    changes=[]
    for rel in baseline:
        path=project/rel
        if path.suffix.lower() in CODE_SUFFIXES and not path.exists() and not any(rel.startswith(root) for root in MATH_ROOTS):
            raise ValueError('THEORY_GATE_BLOCKED: 理论审查前禁止删除系统代码：'+rel)
    from runner_core import project_files
    for path in project_files(project):
        if path.suffix.lower() not in CODE_SUFFIXES: continue
        rel=path.relative_to(project).as_posix()
        original=baseline.get(rel)
        if original == hash_file(path): continue
        if not any(rel.startswith(root) for root in MATH_ROOTS):
            raise ValueError('THEORY_GATE_BLOCKED: 理论审查前禁止新增或修改系统代码：'+rel)
        changes.append((rel,path))
    if len(changes)>policy['max_math_code_files']:
        raise ValueError('Minimal mathematical-check file budget exceeded')
    lines=sum(len(path.read_text(encoding='utf-8-sig').splitlines()) for _,path in changes)
    if lines>policy['max_math_code_lines']:
        raise ValueError('Minimal mathematical-check line budget exceeded')
    if changes:
        plan=read_object(project/'research/MATH_CHECK_PLAN.json')
        for field in ('question','why_code_is_necessary','success_criterion','failure_criterion'):
            if not isinstance(plan.get(field),str) or not plan[field].strip():raise ValueError('MATH_CHECK_PLAN missing '+field)
        listed=plan.get('files')
        if not isinstance(listed,list) or not {rel for rel,_ in changes} <= set(listed):
            raise ValueError('MATH_CHECK_PLAN must name every changed mathematical-check file')
        seconds=plan.get('max_seconds')
        if type(seconds) is not int or not 1 <= seconds <= policy['math_check_timeout_seconds']:
            raise ValueError('Mathematical check time limit exceeds policy')
    return [rel for rel,_ in changes]
