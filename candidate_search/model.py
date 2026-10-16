"""R11 data vocabulary, conservative duplicate normalization and event hashes."""
from __future__ import annotations
import copy
import re
import unicodedata
from engine.common import object_hash

STATUSES = frozenset({'PROPOSED', 'SCREENING', 'READY_FOR_ATTEMPT', 'ACTIVE',
                      'REFUTED', 'COVERED', 'RETIRED', 'CONDITIONAL'})
ACTIVE_STATUSES = frozenset({'SCREENING', 'READY_FOR_ATTEMPT', 'ACTIVE'})
TERMINAL_STATUSES = frozenset({'REFUTED', 'COVERED', 'RETIRED'})
MAX_ACTIVE = 3
FIELDS = frozenset({'schema_version', 'id', 'title', 'goal_anchor_id', 'problem_id',
    'problem_version', 'problem_proposal_file', 'hypothesis', 'nontriviality_argument',
    'closest_prior_work', 'falsification_gate', 'proof_obligations', 'assumptions',
    'immutable_constraints', 'domain', 'quantifiers', 'security_model',
    'estimated_context_bytes', 'dependency_claims', 'evidence_refs', 'failure_scope',
    'restart_conditions', 'parent'})


def normalized(value):
    """Only conservative exact-text normalization, never semantic equivalence proof."""
    if isinstance(value, str):
        return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', value).casefold()).strip()
    if isinstance(value, list):
        return sorted((normalized(v) for v in value), key=object_hash)
    if isinstance(value, dict): return {k: normalized(v) for k, v in sorted(value.items())}
    return value


def semantic_key(spec, problem_binding):
    fields = ('hypothesis', 'assumptions', 'immutable_constraints', 'domain', 'quantifiers',
              'security_model')
    scientific_fields = ('statement', 'quantifiers', 'domain', 'input_contract', 'output_contract',
                         'assumptions', 'immutable_constraints', 'baseline_exclusions', 'security_model')
    scientific_problem = {k: problem_binding['spec'].get(k) for k in scientific_fields}
    scientific_problem['obligations'] = [
        {k: v for k, v in obligation.items() if k != 'id'}
        for obligation in problem_binding['spec']['obligations']]
    return object_hash(normalized({**{k: spec[k] for k in fields},
                                  'problem_scientific_content': scientific_problem}))


def event(previous, kind, record, reason, at):
    value = {'sequence': len(previous) + 1, 'previous_sha256': previous[-1]['sha256'] if previous else None,
             'type': kind, 'record': copy.deepcopy(record), 'reason': reason, 'at': at}
    value['sha256'] = object_hash(value)
    return value
