"""Unified discovery commands, using the same project resolution and locks."""
from __future__ import annotations
import contextlib
from pathlib import Path
import configuration
from research_quality import read_object
from route_budget import file_lock
from . import claim_graph, discovery_scheduler as scheduler, problem_compiler
from .common import ledger, policy


def dispatch(args):
    import research
    project = research.resolve_project(args.project)
    group, action = args.command, args.action
    if group == 'attempt' and action == 'run':
        if scheduler.active(project) is None: raise ValueError('Start a fixed-problem attempt first')
        scheduler.check(project)
        return research.run_child(research.runner_command(project, args))
    readonly = (group == 'problem' and action in {'list', 'show'}) or (group == 'attempt' and action == 'status') or (group == 'claim' and action in {'status', 'show'}) or (group == 'discovery' and not args.file)
    with contextlib.ExitStack() as stack:
        if not readonly:
            stack.enter_context(research.project_lock(project))
            stack.enter_context(file_lock(configuration.ROOT / 'locks' / (configuration.project_id(project) + '.lock')))
        if group == 'problem':
            if action == 'list': result = problem_compiler.pool(project)
            elif action == 'show': result = problem_compiler.get_problem(project, args.id, args.version)
            else: result = problem_compiler.import_problem(project, read_object(Path(args.file)), args.reason)
        elif group == 'attempt':
            if action == 'start': result = scheduler.start(project, args.problem, version=args.version)
            elif action == 'extend': result = scheduler.extend(project, args.reason)
            elif action == 'close': result = scheduler.close(project, args.reason)
            else:
                result = ledger(project)
                try: scheduler.check(project); result['preflight'] = 'READY' if scheduler.active(project) else 'NO_ACTIVE_ATTEMPT'
                except (ValueError, OSError) as exc: result['preflight'] = str(exc)
        elif group == 'claim':
            if action == 'import': result = claim_graph.import_claim(project, read_object(Path(args.file)), args.reason)
            elif action == 'show': result = claim_graph.get(project, args.id)
            elif action == 'status': result = claim_graph.status(project)
            elif action == 'refresh': result = claim_graph.refresh(project)
            elif action == 'invalidate': result = claim_graph.invalidate(project, args.id, args.reason)
            else: result = claim_graph.review(project, args.id, args.kind, args.evidence, args.reviewer, args.reason)
        elif group == 'verify':
            if action == 'lean':
                from .formal_verifier import run
                result = run(project, args.claim, args.file, args.declaration)
            else:
                from .falsification import search
                witness = read_object(Path(args.witness)) if args.witness else None
                result = search(project, args.claim, *args.bounds, witness=witness)
        else:
            if args.file:
                override = read_object(Path(args.file))
                proposed = configuration.deep_merge(policy(project), override)
                scheduler.validate_policy(proposed)
                dest = configuration.ROOT / 'config/projects' / (configuration.project_id(project) + '.json')
                data = configuration.load_json(dest, {'schema_version': 1})
                data['discovery_policy'] = configuration.deep_merge(data.get('discovery_policy', {}), override)
                configuration.atomic_json(dest, data)
            result = {'project': configuration.project_id(project), 'discovery_policy': policy(project),
                      'active_attempt': scheduler.active(project)}
        research.print_json(result)
        if group == 'verify' and action == 'lean' and result['status'] != 'TOOL_PASSED_AUDIT_PENDING': return 2
    return 0


def dispatch_knowledge(args):
    """Inspect or extend the existing graph without consuming research budget."""
    import research
    from . import knowledge_graph
    action = args.action
    if action in {'shared','share-preview'}:
        if args.project=='all': raise ValueError('Sharing requires one explicit destination/source project')
        project=research.resolve_project(args.project)
        from knowledge import federation
        if action=='shared': result=federation.search(configuration.ROOT,project,query=args.query,model_path=args.model)
        else:
            result=federation.preview(configuration.ROOT,project,claim_id=args.claim,reference_id=args.reference_id,
                revision=args.revision,model_path=args.model,summary_path=args.summary,public_sources=args.public_source,
                license_id=args.license,approved_by=args.approved_by,reason=args.reason)
        research.print_json({'project':configuration.project_id(project),'knowledge':result})
        return 0
    if action in {'build', 'explain', 'diff', 'context'}:
        from knowledge import build as projection
        if args.project == 'all': raise ValueError('Projection operations require one explicit project')
        project = research.resolve_project(args.project)
        if action=='context':
            from knowledge.context_builder import build
            result=build(configuration.ROOT,project,task=args.task,claim_id=args.claim,problem_id=args.problem,
                problem_version=args.problem_version,obligation_id=args.obligation,goal_anchor_id=args.goal_anchor,
                max_bytes=args.max_bytes)
        elif action=='build': result=projection.build(configuration.ROOT,project,dry_run=args.dry_run,cache_only=args.cache_only)
        elif action=='diff':
            from knowledge import events
            result=events.diff(configuration.ROOT,project,args.from_index,args.to_index)
        else: result=projection.explain_claim(configuration.ROOT,project,args.claim,args.revision)
        research.print_json({'project':configuration.project_id(project),'knowledge':result})
        return 0
    readonly = action in {'status', 'search', 'show', 'trace', 'impact'}
    if args.project == 'all':
        if action not in {'status', 'search'}:
            raise ValueError('knowledge all only supports status or search')
        selected = research.projects()
    else:
        selected = [research.resolve_project(args.project)]
    for project in selected:
        with contextlib.ExitStack() as stack:
            if not readonly:
                stack.enter_context(research.project_lock(project))
                stack.enter_context(file_lock(configuration.ROOT / 'locks' / (configuration.project_id(project) + '.lock')))
            if action == 'status':
                result = knowledge_graph.status(project)
                from knowledge import build as projection
                result['projection'] = projection.status(configuration.ROOT,project)
            elif action == 'search': result = knowledge_graph.search(project, args.query, kind=args.kind, limit=args.limit)
            elif action == 'show': result = knowledge_graph.get(project, args.id, revision=args.revision)
            elif action == 'trace': result = knowledge_graph.trace(project, args.id)
            elif action == 'impact': result = knowledge_graph.impact(project, args.id)
            elif action == 'import': result = knowledge_graph.import_record(project, read_object(Path(args.file)), args.reason)
            elif action == 'invalidate': result = knowledge_graph.invalidate(project, args.id, args.reason)
            else: result = knowledge_graph.refresh(project)
            research.print_json({'project': configuration.project_id(project), 'knowledge': result})
    return 0


def add_commands(subparsers, add_project, common_run_options):
    from .candidate_cli import add_commands as add_candidates
    add_candidates(subparsers, add_project)
    top = subparsers.add_parser('knowledge', help='长期科研知识：来源追溯、失效传播与现有主张图')
    subs = top.add_subparsers(dest='action', required=True)
    descriptions = {'status': '只读查看来源、知识与现有主张的当前状态',
        'build':'构建可删重建的只读来源投影；仅写state/knowledge缓存',
        'explain':'只读解释精确主张版本、义务、问题、目标和来源',
        'diff':'只读比较两个已保存的图谱版本与失效原因',
        'context':'只读预览按义务分级的有来源上下文，不调用模型',
        'shared':'双向白名单中的公开参考；只读、不传递科学认可',
        'share-preview':'源项目只读生成待操作员审批的公开摘要草稿',
        'search': '只读检索当前及历史知识；历史命中不表示当前通过',
        'show': '只读查看节点；--revision 选择知识历史版本',
        'trace': '只读追溯当前状态和精确绑定的历史来源快照',
        'impact': '只读查看下游依赖影响',
        'import': '持锁登记结构化知识及精确来源',
        'refresh': '持锁刷新本地来源索引，不调用模型',
        'invalidate': '持锁登记明确失效原因，保留历史'}
    for action in ('status', 'search', 'show', 'trace', 'impact', 'import', 'refresh', 'invalidate', 'build', 'explain', 'diff', 'context','shared','share-preview'):
        cmd = subs.add_parser(action, help=descriptions[action], description=descriptions[action])
        add_project(cmd); cmd.set_defaults(function=dispatch_knowledge)
        if action in {'shared','share-preview'}:
            cmd.add_argument('--model',default='knowledge/shared/MODEL.json'); cmd.add_argument('--dry-run',action='store_true')
        if action=='shared': cmd.add_argument('--query',default='')
        if action=='share-preview':
            cmd.add_argument('--claim',required=True); cmd.add_argument('--reference-id',required=True)
            cmd.add_argument('--revision',type=int,default=1); cmd.add_argument('--summary',required=True)
            cmd.add_argument('--public-source',action='append',required=True)
            cmd.add_argument('--license',required=True); cmd.add_argument('--approved-by',required=True); cmd.add_argument('--reason',required=True)
        if action=='context':
            cmd.add_argument('--task',default=''); cmd.add_argument('--claim'); cmd.add_argument('--problem')
            cmd.add_argument('--problem-version',type=int); cmd.add_argument('--obligation'); cmd.add_argument('--goal-anchor')
            cmd.add_argument('--max-bytes',type=int,default=32768); cmd.add_argument('--dry-run',action='store_true')
        if action == 'build':
            cmd.add_argument('--dry-run', action='store_true')
            cmd.add_argument('--cache-only',action='store_true',help='仅重建索引，保留并报告损坏的历史，不追加事件')
        if action == 'diff':
            cmd.add_argument('--from-index',required=True); cmd.add_argument('--to-index',required=True)
        if action == 'explain':
            cmd.add_argument('--claim',required=True); cmd.add_argument('--revision',type=int)
        if action in {'show', 'trace', 'impact', 'invalidate'}: cmd.add_argument('--id', required=True)
        if action == 'show': cmd.add_argument('--revision', type=int, help='知识节点历史版本；主张沿用现有 claim show')
        if action == 'search':
            cmd.add_argument('--query', required=True)
            cmd.add_argument('--kind', help='paper/theorem/evidence/failed_path/obligation/claim/source')
            cmd.add_argument('--limit', type=int, default=20)
        if action == 'import': cmd.add_argument('--file', required=True)
        if action in {'import', 'invalidate'}: cmd.add_argument('--reason', required=True)
    for group, actions in [('problem', ('list', 'show', 'import')),
            ('attempt', ('start', 'status', 'run', 'extend', 'close')),
            ('claim', ('import', 'status', 'show', 'review', 'invalidate', 'refresh')),
            ('verify', ('lean', 'counterexample'))]:
        top = subparsers.add_parser(group, help='Mathematical Discovery Engine: ' + group)
        subs = top.add_subparsers(dest='action', required=True)
        for action in actions:
            cmd = subs.add_parser(action); add_project(cmd); cmd.set_defaults(function=dispatch)
            if group in {'problem', 'claim'}:
                if action in {'show', 'review', 'invalidate'}: cmd.add_argument('--id', required=True)
                if action == 'import': cmd.add_argument('--file', required=True)
                if action in {'import', 'review', 'invalidate'}: cmd.add_argument('--reason', required=True)
                if group == 'problem' and action == 'show': cmd.add_argument('--version', type=int)
                if action == 'review':
                    cmd.add_argument('--kind', choices=('proof', 'statement', 'proof_and_statement', 'novelty', 'formal_audit'), required=True)
                    cmd.add_argument('--evidence', required=True); cmd.add_argument('--reviewer', required=True)
            elif group == 'attempt':
                if action == 'start': cmd.add_argument('--problem', required=True); cmd.add_argument('--version', type=int)
                if action in {'extend', 'close'}: cmd.add_argument('--reason', required=True)
                if action == 'run':
                    common_run_options(cmd); cmd.add_argument('--dry-run', action='store_true')
            else:
                cmd.add_argument('--claim', required=True)
                if action == 'lean':
                    cmd.add_argument('--file', required=True); cmd.add_argument('--declaration', required=True)
                else:
                    cmd.add_argument('--bounds', nargs=2, type=int, default=[-3, 3], metavar=('LOW', 'HIGH'))
                    cmd.add_argument('--witness')
    cmd = subparsers.add_parser('discovery', help='查看数学发现配置；--file 保存项目局部覆盖')
    add_project(cmd); cmd.add_argument('--file'); cmd.set_defaults(function=dispatch, action='config')
