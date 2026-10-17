"""Offline evaluator commands, separate from project research and budgets."""
from pathlib import Path

from research_quality import read_object


def dispatch(args):
    import research
    root = getattr(args, 'dataset_root', None)
    action = args.action
    if action == 'validate':
        from evaluation.validate_cases import validate_dataset
        result = validate_dataset(root=root, private_root=args.private_root)
    elif action in {'list', 'show', 'bundle'}:
        from evaluation import cases
        if action == 'list': result = cases.list_cases(root=root)
        elif action == 'show': result = cases.public_view(args.case, version=args.version, root=root)
        else: result = cases.build_agent_bundle(args.case, args.destination, version=args.version, root=root)
    elif action in {'register-oracle', 'history', 'diff'}:
        from evaluation import registry
        if action == 'register-oracle':
            result = registry.register(args.private_root, args.case, read_object(args.oracle_file),
                reviewer=args.reviewer, reason=args.reason, version=args.version, root=root)
        elif action == 'history': result = registry.history(args.private_root, args.case, root=root)
        else: result = registry.diff(args.private_root, args.case, args.from_version, args.to_version, root=root)
    elif action == 'score-fixture':
        from evaluation.scoring import score_fixture
        result = score_fixture(args.case, read_object(args.response), private_root=args.private_root,
                               version=args.version, root=root)
    elif action == 'isolation-status':
        result = {'isolation_status': 'NOT_ISOLATED', 'formal_counted': False,
            'agent_execution_allowed': False, 'real_supervision_enabled': False, 'lean_enabled': False,
            'reason': 'R16 has no certified research-agent executor; a token access probe cannot certify another process.'}
    else:
        from evaluation.isolation import probe_isolation
        result = probe_isolation(args.public_task, args.private_sentinel, timeout_seconds=5)
    research.print_json(result)
    if action == 'score-fixture' and result.get('status') == 'STALE_OR_INVALID': return 2
    if action == 'isolation-probe' and result.get('os_probe_status') != 'VERIFIED_READ_DENIAL': return 2
    return 0


def add_commands(subparsers):
    top = subparsers.add_parser('benchmark', help='独立离线题库和私有评分；不派发科研或计正式质量统计')
    actions = top.add_subparsers(dest='action', required=True)
    for action in ('list', 'show', 'validate', 'bundle', 'register-oracle', 'score-fixture',
                   'history', 'diff', 'isolation-status', 'isolation-probe'):
        command = actions.add_parser(action)
        command.set_defaults(function=dispatch)
        if action not in {'isolation-status', 'isolation-probe'}:
            command.add_argument('--dataset-root', type=Path)
        if action in {'show', 'bundle', 'register-oracle', 'score-fixture', 'history', 'diff'}:
            command.add_argument('--case', required=True)
        if action in {'show', 'bundle', 'register-oracle', 'score-fixture'}:
            command.add_argument('--version', type=int)
        if action == 'bundle': command.add_argument('--destination', type=Path, required=True)
        if action in {'register-oracle', 'score-fixture', 'history', 'diff'}:
            command.add_argument('--private-root', type=Path, required=True)
        if action == 'validate': command.add_argument('--private-root', type=Path)
        if action == 'register-oracle':
            command.add_argument('--oracle-file', type=Path, required=True)
            command.add_argument('--reviewer', required=True)
            command.add_argument('--reason', required=True)
        if action == 'score-fixture': command.add_argument('--response', type=Path, required=True)
        if action == 'diff':
            command.add_argument('--from-version', type=int, required=True)
            command.add_argument('--to-version', type=int, required=True)
        if action == 'isolation-probe':
            command.add_argument('--public-task', type=Path, required=True)
            command.add_argument('--private-sentinel', type=Path, required=True)
