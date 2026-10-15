"""Bounded exact-integer counterexamples; no Python eval and no proof by testing."""
from __future__ import annotations
import ast
import itertools
import re
import time
from .common import object_hash, policy, stamp, strings, text


def parse(expression, variables):
    text(expression, 'integer predicate')
    if len(expression) > 2048: raise ValueError('Expression too long')
    try: node = ast.parse(expression, mode='eval')
    except (SyntaxError, RecursionError) as exc: raise ValueError('Invalid integer expression') from exc
    nodes = list(ast.walk(node))
    allowed = (ast.Expression, ast.Constant, ast.Name, ast.Load, ast.BinOp, ast.UnaryOp,
               ast.Add, ast.Sub, ast.Mult, ast.Pow, ast.Mod, ast.USub, ast.UAdd,
               ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)
    if len(nodes) > 128 or any(not isinstance(n, allowed) for n in nodes):
        raise ValueError('Only bounded integer arithmetic and comparisons are supported')
    for n in nodes:
        if isinstance(n, ast.Name) and n.id not in variables: raise ValueError('Unknown integer variable')
        if isinstance(n, ast.Constant) and (type(n.value) is not int or abs(n.value) > 10**9):
            raise ValueError('Integer constant outside supported bound')
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Pow):
            if not isinstance(n.right, ast.Constant) or type(n.right.value) is not int or not 0 <= n.right.value <= 8:
                raise ValueError('Exponent must be a literal integer in 0..8')
    if not isinstance(node.body, ast.Compare): raise ValueError('Predicate must be a comparison')
    return node.body


def value(node, assignment):
    if isinstance(node, ast.Constant): return node.value
    if isinstance(node, ast.Name): return assignment[node.id]
    if isinstance(node, ast.UnaryOp):
        operand = value(node.operand, assignment)
        if type(operand) is not int: raise ValueError('Arithmetic operand must be integer')
        return -operand if isinstance(node.op, ast.USub) else operand
    if isinstance(node, ast.BinOp):
        left, right = value(node.left, assignment), value(node.right, assignment)
        if type(left) is not int or type(right) is not int: raise ValueError('Arithmetic operands must be integers')
        if isinstance(node.op, ast.Add): result = left + right
        elif isinstance(node.op, ast.Sub): result = left - right
        elif isinstance(node.op, ast.Mult): result = left * right
        elif isinstance(node.op, ast.Mod): result = left % right
        else: result = left ** right
        if result.bit_length() > 4096: raise ValueError('Exact arithmetic bound exceeded')
        return result
    if isinstance(node, ast.Compare):
        left = value(node.left, assignment)
        for op, other in zip(node.ops, node.comparators):
            right = value(other, assignment)
            if type(left) is not int or type(right) is not int: raise ValueError('Comparison operands must be integers')
            if isinstance(op, ast.Eq): passed = left == right
            elif isinstance(op, ast.NotEq): passed = left != right
            elif isinstance(op, ast.Lt): passed = left < right
            elif isinstance(op, ast.LtE): passed = left <= right
            elif isinstance(op, ast.Gt): passed = left > right
            else: passed = left >= right
            if not passed: return False
            left = right
        return True
    raise ValueError('Unsupported expression node')


def validate_statement(statement):
    if not isinstance(statement, dict) or set(statement) != {'domain', 'variables', 'preconditions', 'conclusion'}:
        raise ValueError('Machine statement requires domain/variables/preconditions/conclusion')
    if statement['domain'] != 'INTEGER': raise ValueError('Only exact INTEGER predicates are implemented')
    variables = strings(statement['variables'], 'variables')
    if len(variables) > 8 or len(variables) != len(set(variables)) or any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,31}', v) for v in variables):
        raise ValueError('Need 1..8 unique integer variables')
    strings(statement['preconditions'], 'preconditions', empty=True)
    if len(statement['preconditions']) > 20: raise ValueError('Too many preconditions')
    for expr in statement['preconditions'] + [statement['conclusion']]: parse(expr, variables)
    return statement


def check_witness(statement, witness):
    validate_statement(statement)
    if not isinstance(witness, dict) or set(witness) != set(statement['variables']): raise ValueError('Witness variables mismatch')
    if any(type(v) is not int or abs(v) > 10**9 for v in witness.values()): raise ValueError('Invalid integer witness')
    for expr in statement['preconditions']:
        if not value(parse(expr, statement['variables']), witness):
            return {'preconditions_satisfied': False, 'conclusion_holds': None, 'is_counterexample': False}
    conclusion = value(parse(statement['conclusion'], statement['variables']), witness)
    return {'preconditions_satisfied': True, 'conclusion_holds': conclusion,
            'is_counterexample': not conclusion}


def search(project, claim_id, low=-3, high=3, witness=None):
    from .claim_graph import get, record_tool
    item = get(project, claim_id); statement = item['spec'].get('machine_statement')
    validate_statement(statement)
    if type(low) is not int or type(high) is not int or not -1000 <= low <= high <= 1000:
        raise ValueError('Counterexample bounds must satisfy -1000 <= low <= high <= 1000')
    config = policy(project); start = time.monotonic(); cases = 0; found = None; undefined = 0
    candidates = [witness] if witness is not None else (dict(zip(statement['variables'], values)) for values in itertools.product(range(low, high + 1), repeat=len(statement['variables'])))
    for assignment in candidates:
        if cases >= config['counterexample_max_cases'] or time.monotonic() - start >= config['counterexample_max_seconds']: break
        cases += 1
        try: result = check_witness(statement, assignment)
        except ZeroDivisionError:
            undefined += 1; continue
        if result['is_counterexample']:
            found = {'assignment': assignment, **result}; break
    receipt = {'schema_version': 1, 'claim_id': claim_id, 'claim_revision': item['revision'],
        'claim_sha256': item['spec_sha256'], 'machine_statement_sha256': object_hash(statement),
        'status': 'EXACT_COUNTEREXAMPLE' if found else 'SEARCHED_NOT_FOUND',
        'source_bindings': dict(item['evidence']), 'witness': found, 'tested_cases': cases,
        'undefined_cases': undefined, 'bounds': [low, high], 'seconds': time.monotonic() - start,
        'statement_match': 'REQUIRES_INDEPENDENT_REVIEW', 'at': stamp(),
        'scope': 'One exact witness refutes the registered integer predicate; bounded failure to find one proves nothing'}
    # An unsuccessful bounded search must not erase an earlier exact refutation.
    if found: record_tool(project, claim_id, 'counterexample_receipt', receipt)
    return receipt
