#!/usr/bin/env python3
"""Offline exact-witness smoke benchmark; does not measure AI research quality."""
import argparse
import itertools
import json
from pathlib import Path
import sys
import time
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.falsification import check_witness


def run():
    cases = json.loads((ROOT / 'tests/research_benchmark/cases.json').read_text(encoding='utf8'))['cases']
    rows = []
    for case in cases:
        start = time.monotonic(); found = None; tested = 0
        statement = case['statement']
        for values in itertools.product(range(-3, 4), repeat=len(statement['variables'])):
            tested += 1; witness = dict(zip(statement['variables'], values))
            if check_witness(statement, witness)['is_counterexample']: found = witness; break
        result = 'EXACT_COUNTEREXAMPLE' if found else 'SEARCHED_NOT_FOUND'
        rows.append({'id': case['id'], 'result': result, 'expected': case['expected'],
            'pass': result == case['expected'], 'witness': found, 'tested_cases': tested,
            'seconds': time.monotonic() - start})
    return {'schema_version': 1, 'status': 'PASS' if all(r['pass'] for r in rows) else 'FAIL',
        'scope': 'Bounded exact integer verifier fixtures, no model or Lean call',
        'research_quality_improvement': 'NOT_MEASURED', 'cases': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output')
    args = parser.parse_args(); result = run(); content = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        target = Path(args.output)
        if target.exists(): raise SystemExit('Output exists; choose a new report path')
        target.parent.mkdir(parents=True, exist_ok=True); target.write_text(content + '\n', encoding='utf8')
    print(content); sys.exit(0 if result['status'] == 'PASS' else 2)
