"""Bind procedural progress to an operator-owned research objective.

This validates declarations and evidence freshness, not mathematical relevance
or truth. Missing legacy declarations are accepted as work, but cannot reset
mainline stagnation. Scientific acceptance remains in the existing gates.
"""
from __future__ import annotations

import copy
import hashlib
import json

SCOPES = {'CORE', 'DIRECT_DEPENDENCY', 'SUPPORT'}


def binding(project, state):
    return {'goal_sha256': hashlib.sha256((project / 'GOAL.md').read_bytes()).hexdigest(),
            'research_route': state.get('research_route'),
            'selected_idea': copy.deepcopy(state.get('selected_idea'))}


def make_focus(project, state, problem=None):
    # A migrated project's current priority may already describe a side quest.
    obj = {'binding': binding(project, state),
           'core_problem': problem or (project / 'GOAL.md').read_text(encoding='utf-8-sig')}
    obj['anchor_id'] = hashlib.sha256(json.dumps(obj, sort_keys=True,
        ensure_ascii=False).encode('utf-8')).hexdigest()
    return obj


def ensure_focus(project, epoch, state):
    # Do not follow a model's changing priority_problem after the first pin.
    if 'focus' not in epoch:
        epoch['focus'] = make_focus(project, state)
    return epoch['focus']


def require_current(project, epoch, state):
    focus = ensure_focus(project, epoch, state)
    if focus['binding'] != binding(project, state):
        raise ValueError('RESEARCH_FOCUS_STALE: goal or selected idea changed; use refocus explicitly')
    return focus


def validate_impact(impact, focus):
    if not isinstance(impact, dict) or impact.get('anchor_id') != focus['anchor_id']:
        raise ValueError('goal_impact must reference the controller focus anchor')
    if impact.get('scope') not in SCOPES:
        raise ValueError('goal_impact.scope must be CORE, DIRECT_DEPENDENCY or SUPPORT')
    for key in ('target_obligation', 'before', 'after', 'next_mainline_task'):
        if not isinstance(impact.get(key), str) or not impact[key].strip():
            raise ValueError('goal_impact missing ' + key)
    if impact['scope'] == 'DIRECT_DEPENDENCY':
        for key in ('consumer_claim', 'dependency_argument'):
            if not isinstance(impact.get(key), str) or not impact[key].strip():
                raise ValueError('A direct dependency requires ' + key)
    return impact


def assess_progress(project, epoch, receipt, changed_paths):
    """Do not reject useful files merely because their relevance is unproven."""
    impact = receipt.get('goal_impact')
    result = {'mainline_progress': False, 'scope': 'UNCLASSIFIED',
              'reason': 'Missing goal_impact; retained as unclassified work'}
    try:
        validate_impact(impact, epoch['focus'])
    except (KeyError, ValueError) as exc:
        result['reason'] = str(exc)
        return result
    result['scope'] = impact['scope']
    if impact['scope'] == 'SUPPORT' or receipt.get('result_status') in {'SUPPORT_ONLY', 'NO_PROGRESS'}:
        result['reason'] = 'Supporting result does not reset mainline stagnation'
        return result
    if receipt.get('work_kind') in {'ENGINEERING_SUPPORT', 'EXECUTION_DIAGNOSIS', 'SYSTEM_IMPLEMENTATION', 'SYSTEM_TEST'}:
        result['reason'] = 'Implementation and diagnostic work are not theoretical progress'
        return result
    if impact['before'].strip() == impact['after'].strip():
        result['reason'] = 'No declared change to the target obligation'
        return result
    # The progress signal and the research receipt must share fresh evidence.
    paths = sorted(set(changed_paths) & set(receipt.get('evidence_paths', [])))
    if not paths:
        result['reason'] = 'No shared changed evidence for the claimed progress'
        return result
    from research_quality import local_file, hash_file
    hashes = sorted({hash_file(local_file(project, p)) for p in paths})
    fingerprint = hashlib.sha256(json.dumps({'anchor': epoch['focus']['anchor_id'],
        'evidence': hashes}, sort_keys=True).encode()).hexdigest()
    if fingerprint in epoch.get('mainline_fingerprints', []):
        result['reason'] = 'Previously counted evidence content, possibly renamed'
        return result
    result.update(mainline_progress=True, reason='Bound mainline progress claim; not scientific certification',
                  fingerprint=fingerprint)
    return result


def validate_next_task(verdict, focus):
    """Require a concrete return path before a same-route refocus or extension."""
    impact = validate_impact(verdict.get('next_goal_impact'), focus)
    task = verdict.get('next_task')
    if not isinstance(task, str) or len(task.strip()) < 24:
        raise ValueError('A route continuation requires a concrete next_task')
    if impact['scope'] == 'SUPPORT':
        raise ValueError('A route continuation must address the core or a direct dependency')
    if task.strip() != impact['next_mainline_task'].strip():
        raise ValueError('next_task must match next_goal_impact.next_mainline_task')
    if impact['before'].strip() == impact['after'].strip():
        raise ValueError('A continuation must state the question and its decisive expected resolution')
    return impact


def prompt(focus):
    example = {'anchor_id': focus['anchor_id'], 'scope': 'CORE|DIRECT_DEPENDENCY|SUPPORT',
               'target_obligation': '现有核心义务的标识和具体内容',
               'before': '本轮开始时的准确缺口', 'after': '本轮证据具体消除了什么或限定了什么',
               'next_mainline_task': '回到核心义务后的具体下一动作'}
    return ('# Controller-owned mainline focus\n' + json.dumps(focus, ensure_ascii=False, indent=2)
        + '\n每轮 ROUND_REVIEW.json 增加 goal_impact，格式：\n'
        + json.dumps(example, ensure_ascii=False, indent=2)
        + '\nDIRECT_DEPENDENCY 另填 consumer_claim 和 dependency_argument，说明哪条主构造声明直接使用该引理，'
          '以及缺少它会阻断哪一步。无法建立直接依赖的文献补证、勘误和局部边界研究记为 SUPPORT。'
          '允许登记贡献类型 NONE 的必要反例或中间推导；无需虚构新原语来获得进展。'
          'SUPPORT_ONLY、缺失关联和重复证据仍消耗轮数，但不清零主线停滞。'
          '将反例转成设计约束，随后选择能推进核心构造、安全界或成本界的任务。'
          '原文的非必要引理待审可单独保留；不能把其独立审查自动设成全项目继续的前置条件。'
          '本声明只供调度，绝不关闭科学门禁。\n')
