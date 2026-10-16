"""Operator-owned candidate catalog commands; registration never runs research."""
import contextlib
from pathlib import Path

import configuration
from research_quality import read_object
from route_budget import file_lock


def dispatch(args):
    import research
    from candidate_search import catalog
    project = research.resolve_project(args.project)
    with contextlib.ExitStack() as stack:
        if args.action not in {'list', 'show', 'anchor', 'plan', 'schedule-status',
                                'verify-prepare', 'verification-show', 'verification-recheck',
                                'security-prepare', 'security-show', 'security-recheck'}:
            stack.enter_context(research.project_lock(project))
            stack.enter_context(file_lock(configuration.ROOT / 'locks' /
                                          (configuration.project_id(project) + '.lock')))
        if args.action in {'security-prepare', 'security-review', 'security-show', 'security-recheck'}:
            from candidate_search import security_model, security_review
            if args.action == 'security-prepare':
                result = security_model.prepare_request(project, args.id, args.claim, read_object(Path(args.card)))
            elif args.action == 'security-review':
                result = security_review.review(project, read_object(Path(args.request)), locks_held=True)
            elif args.action == 'security-show':
                result = security_review.show(project, args.request_id)
            else:
                result = security_review.recheck(project, args.request_id)
        elif args.action in {'verify-prepare', 'verify', 'verification-show', 'verification-recheck'}:
            from candidate_search.verifiers import interface
            if args.action == 'verify-prepare':
                result = interface.prepare_request(project, args.id, args.claim,
                    adapter_id=args.adapter, low=args.bounds[0], high=args.bounds[1],
                    max_cases=args.max_cases, max_seconds=args.max_seconds,
                    wall_timeout_seconds=args.wall_timeout, proof_file=args.proof_file,
                    declaration=args.declaration)
            elif args.action == 'verify':
                result = interface.verify(project, read_object(Path(args.request)), locks_held=True)
            elif args.action == 'verification-show':
                result = interface.show(project, args.request_id)
            else:
                result = interface.recheck(project, args.request_id)
        elif args.action in {'plan', 'schedule-status', 'select', 'bind-attempt', 'map-run'}:
            from candidate_search import scheduler
            if args.action == 'plan':
                result = scheduler.plan(project, dry_run=True)
            elif args.action == 'schedule-status':
                result = scheduler.status(project)
            elif args.action == 'select':
                plan = read_object(Path(args.plan_file))
                snapshot = plan.get('snapshot')
                if (not isinstance(snapshot, dict) or not isinstance(plan.get('snapshot_sha256'), str)
                        or not {'goal_anchor_id', 'route_epoch', 'last_processed_run'} <= snapshot.keys()):
                    raise ValueError('Select requires a complete candidate plan and frozen snapshot SHA')
                result = scheduler.select(project, args.id, expected_revision=args.expected_revision,
                    reason=args.reason, expected_goal_anchor_id=snapshot['goal_anchor_id'],
                    expected_route_epoch=snapshot['route_epoch'],
                    expected_last_processed_run=snapshot['last_processed_run'],
                    expected_snapshot_sha256=plan['snapshot_sha256'], locks_held=True)
            elif args.action == 'bind-attempt':
                result = scheduler.bind_attempt(project, args.selection_id, args.attempt_id,
                    reason=args.reason, locks_held=True)
            else:
                result = scheduler.record_run_mapping(project, args.selection_id, args.run_id,
                    reason=args.reason, expected_attempt_id=args.attempt_id, locks_held=True)
        elif args.action == 'list':
            result = catalog.list_candidates(project)
        elif args.action == 'show':
            result = catalog.show(project, args.id, args.revision)
        elif args.action == 'anchor':
            result = catalog.anchor(project)
        elif args.action == 'status':
            disposition = read_object(Path(args.disposition)) if args.disposition else None
            result = catalog.transition(project, args.id, args.status, args.reason,
                expected_revision=args.expected_revision, disposition=disposition)
        else:
            result = catalog.propose(project, read_object(Path(args.file)), args.reason,
                revise=args.action == 'revise',
                expected_revision=getattr(args, 'expected_revision', None))
        research.print_json(result)
        if args.action in {'verify', 'verification-recheck'} and result.get('result_status') in {'FAILED', 'UNSUPPORTED'}:
            return 2
        if args.action in {'security-review', 'security-recheck'} and result.get('decision') in {'FAILED', 'NEEDS_INPUT', 'NEEDS_SOURCE'}:
            return 2
    return 0


def add_commands(subparsers, add_project):
    top = subparsers.add_parser('candidate', help='候选登记与可追溯分支；不调用模型或修改科学等级')
    actions = top.add_subparsers(dest='action', required=True)
    for action in ('anchor', 'list', 'show', 'propose', 'revise', 'status',
                   'plan', 'schedule-status', 'select', 'bind-attempt', 'map-run',
                   'verify-prepare', 'verify', 'verification-show', 'verification-recheck',
                   'security-prepare', 'security-review', 'security-show', 'security-recheck'):
        command = actions.add_parser(action)
        add_project(command)
        command.set_defaults(function=dispatch)
        if action == 'show':
            command.add_argument('--id', required=True)
            command.add_argument('--revision', type=int)
        if action in {'propose', 'revise'}:
            command.add_argument('--file', required=True)
        if action in {'revise', 'status', 'select'}:
            command.add_argument('--expected-revision', type=int, required=True)
        if action == 'plan':
            command.add_argument('--dry-run', action='store_true', help='计划始终只读且不调用模型')
        if action == 'select':
            command.add_argument('--id', required=True)
            command.add_argument('--plan-file', required=True, help='完整只读plan JSON，绑定所有前置摘要')
        if action in {'bind-attempt', 'map-run'}:
            command.add_argument('--selection-id', required=True)
            command.add_argument('--attempt-id', required=True)
        if action == 'map-run':
            command.add_argument('--run-id', required=True)
        if action == 'verify-prepare':
            command.add_argument('--id', required=True)
            command.add_argument('--claim', required=True)
            command.add_argument('--adapter', default='integer-v1')
            command.add_argument('--bounds', nargs=2, type=int, default=[-3, 3], metavar=('LOW', 'HIGH'))
            command.add_argument('--max-cases', type=int, default=10000)
            command.add_argument('--max-seconds', type=float, default=3)
            command.add_argument('--wall-timeout', type=float, default=5)
            command.add_argument('--proof-file')
            command.add_argument('--declaration')
        if action == 'verify':
            command.add_argument('--request', required=True)
        if action == 'security-prepare':
            command.add_argument('--id', required=True)
            command.add_argument('--claim', required=True)
            command.add_argument('--card', required=True, help='协议义务卡JSON，不授予科学审查权限')
        if action == 'security-review':
            command.add_argument('--request', required=True)
        if action in {'verification-show', 'verification-recheck'}:
            command.add_argument('--request-id', required=True)
        if action in {'security-show', 'security-recheck'}:
            command.add_argument('--request-id', required=True)
        if action == 'status':
            command.add_argument('--id', required=True)
            command.add_argument('--status', required=True, choices=('SCREENING',
                'READY_FOR_ATTEMPT', 'REFUTED', 'COVERED', 'RETIRED', 'CONDITIONAL'))
            command.add_argument('--disposition', help='范围、证据与重启条件 JSON')
        if action in {'propose', 'revise', 'status', 'select', 'bind-attempt', 'map-run'}:
            command.add_argument('--reason', required=True)
