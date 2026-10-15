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


def add_commands(subparsers, add_project, common_run_options):
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
