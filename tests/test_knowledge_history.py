"""Exact historical source/dependency pins; no current files or models involved."""
import copy
import unittest

from engine.common import object_hash
from engine.knowledge_history import historical_nodes, pinned_trace


def seal(record):
    record['provenance_sha256'] = object_hash({key: record.get(key) for key in
        ('id', 'revision', 'invalidated', 'source_bindings', 'sources', 'dependency_pins', 'goal_sha256')})
    return record


def memory(node_id, revision, statement, dependencies=None, history=None, source=None):
    pins = dependencies or {}
    path = source or 'literature/' + node_id + '-r' + str(revision) + '.txt'
    spec = {'schema_version': 1, 'id': node_id, 'kind': 'theorem', 'title': node_id,
            'statement': statement, 'sources': [{'path': path, 'locator': 'page:1'}],
            'dependencies': list(pins)}
    record = {'id': node_id, 'revision': revision, 'spec': spec, 'spec_sha256': object_hash(spec),
            'source_bindings': {path: object_hash(statement)},
            'sources': [{'path': path, 'locator': 'page:1', 'sha256': object_hash(statement)}],
            'dependency_pins': copy.deepcopy(pins), 'history': history or []}
    return seal(record)


def claim(node_id, revision, statement, dependencies=None, knowledge=None, history=None):
    deps = dependencies or {}
    spec = {'schema_version': 1, 'id': node_id, 'statement': statement, 'dependencies': list(deps)}
    if knowledge is not None: spec['knowledge_dependencies'] = list(knowledge)
    record = {'id': node_id, 'revision': revision, 'spec': spec, 'spec_sha256': object_hash(spec),
              'evidence': {'proofs/' + node_id + '.md': object_hash(statement)},
              'dependency_pins': copy.deepcopy(deps), 'history': history or [],
              'reviews': {'proof': {'operator': 'Fixture only; must not certify a snapshot'}}}
    if knowledge is not None: record['knowledge_pins'] = copy.deepcopy(knowledge)
    return record


def pin(record):
    return {'revision': record['revision'], 'spec_sha256': record['spec_sha256']}


def graph(memories=None, claims=None):
    return {'schema_version': 1, 'claims': claims or [], 'events': [],
            'memory': {'schema_version': 1, 'nodes': memories or [], 'events': []}}


class KnowledgeHistoryTests(unittest.TestCase):
    def test_old_child_pin_keeps_old_parent_statement_and_source(self):
        old = memory('P', 1, 'The original exact premise', source='literature/original.txt')
        current = memory('P', 2, 'The corrected premise', history=[old], source='literature/corrected.txt')
        child = memory('T', 1, 'Candidate using the original premise', {'P': pin(old)})
        data = graph([current, child]); before = copy.deepcopy(data)
        traced = pinned_trace(data, 'memory:T')
        nodes = {n['key']: n for n in traced['frozen_nodes']}
        parent = nodes['memory:P@r1']
        self.assertEqual(parent['statement'], 'The original exact premise')
        self.assertEqual(parent['sources'][0]['path'], 'literature/original.txt')
        self.assertNotIn('memory:P@r2', nodes)
        self.assertTrue(parent['historical'])
        self.assertEqual(parent['verification_status'], 'UNVERIFIED_SOURCE')
        self.assertEqual(traced['unresolved_pins'], [])
        self.assertEqual(data, before)

    def test_two_layers_follow_each_historical_versions_own_pins(self):
        p1 = memory('P', 1, 'First upstream premise')
        p2 = memory('P', 2, 'Second upstream premise', history=[p1])
        t1 = memory('T', 1, 'Original middle lemma', {'P': pin(p1)})
        t2 = memory('T', 2, 'Revised middle lemma', {'P': pin(p2)}, [t1])
        c1 = claim('C', 1, 'Original canonical claim', knowledge={'T': pin(t1)})
        c2 = claim('C', 2, 'Revised canonical claim', knowledge={'T': pin(t2)}, history=[c1])
        root = claim('R', 1, 'A downstream old-version user', {'C': pin(c1)})
        traced = pinned_trace(graph([p2, t2], [c2, root]), 'claim:R')
        nodes = {n['key']: n for n in traced['frozen_nodes']}
        self.assertEqual(set(nodes), {'claim:R@r1', 'claim:C@r1', 'memory:T@r1', 'memory:P@r1'})
        self.assertEqual(nodes['memory:P@r1']['statement'], 'First upstream premise')
        self.assertEqual(nodes['claim:C@r1']['knowledge_pins'], {'T': pin(t1)})
        self.assertEqual(traced['unresolved_pins'], [])
        self.assertTrue(all('history' not in n and 'reviews' not in n for n in nodes.values()))

    def test_missing_version_or_digest_mismatch_never_uses_latest(self):
        old = memory('P', 1, 'Original premise')
        newer = memory('P', 2, 'Latest premise')
        child = memory('T', 1, 'Still pins version one', {'P': pin(old)})
        missing = pinned_trace(graph([newer, child]), 'memory:T')
        self.assertEqual([n['key'] for n in missing['frozen_nodes']], ['memory:T@r1'])
        self.assertEqual(missing['unresolved_pins'][0]['reason'], 'REVISION_MISSING')
        wrong = copy.deepcopy(old); wrong['spec']['statement'] = 'Tampered old text'
        newer['history'] = [wrong]
        corrupted = pinned_trace(graph([newer, child]), 'memory:T')
        self.assertEqual(corrupted['unresolved_pins'][0]['reason'], 'SPEC_DIGEST_MISMATCH')
        newer['history'] = [old]
        child['dependency_pins']['P']['spec_sha256'] = '0' * 64
        seal(child)
        mismatch = pinned_trace(graph([newer, child]), 'memory:T')
        self.assertEqual(mismatch['unresolved_pins'][0]['reason'], 'PIN_DIGEST_MISMATCH')
        self.assertNotIn('memory:P@r2', {n['key'] for n in mismatch['frozen_nodes']})

    def test_old_claims_without_knowledge_fields_remain_traceable(self):
        parent = claim('C', 1, 'A legacy canonical claim')
        child = claim('D', 1, 'A legacy dependent claim', {'C': pin(parent)})
        traced = pinned_trace(graph(claims=[parent, child]), 'claim:D')
        self.assertEqual({n['key'] for n in traced['frozen_nodes']}, {'claim:C@r1', 'claim:D@r1'})
        self.assertEqual(traced['unresolved_pins'], [])
        self.assertTrue(all(n['verification_status'] == 'UNVERIFIED_SOURCE' for n in traced['frozen_nodes']))

    def test_historical_search_nodes_are_flat_detached_and_do_not_attest_proof(self):
        m1 = memory('M', 1, 'A searchable retired assumption')
        m2 = memory('M', 2, 'A current assumption', history=[m1])
        c1 = claim('C', 1, 'A searchable retired claim')
        c2 = claim('C', 2, 'A current claim', history=[c1])
        data = graph([m2], [c2]); before = copy.deepcopy(data)
        past = historical_nodes(data)
        self.assertEqual({n['key'] for n in past}, {'memory:M@r1', 'claim:C@r1'})
        self.assertTrue(all(n['historical'] and n['verification_status'] == 'UNVERIFIED_SOURCE' for n in past))
        self.assertTrue(all('history' not in n and 'reviews' not in n and 'proof_status' not in n for n in past))
        past[0]['spec']['statement'] = 'Caller mutation'
        self.assertEqual(data, before)

    def test_explicit_historical_root_and_missing_or_ambiguous_pins_fail_closed(self):
        original = memory('M', 1, 'Original root')
        revised = memory('M', 2, 'Revised root', history=[original])
        traced = pinned_trace(graph([revised]), 'memory:M@r1')
        self.assertEqual(traced['frozen_nodes'][0]['statement'], 'Original root')
        revised['history'].append(copy.deepcopy(original))
        bad = pinned_trace(graph([revised]), 'memory:M@r1')
        self.assertEqual(bad['frozen_nodes'], [])
        self.assertEqual(bad['unresolved_pins'][0]['reason'], 'REVISION_AMBIGUOUS')
        invalid = pinned_trace(graph([revised]), 'source:arbitrary')
        self.assertEqual(invalid['frozen_nodes'], [])
        self.assertEqual(invalid['unresolved_pins'][0]['reason'], 'ROOT_KEY_INVALID')

    def test_missing_declared_pin_is_visible_and_provenance_tampering_is_rejected(self):
        parent = memory('P', 1, 'A source snapshot')
        parent['goal_sha256'] = 'fixture-goal'
        seal(parent)
        child = memory('T', 1, 'A dependent source', {'P': pin(parent)})
        parent['sources'][0]['path'] = 'literature/forged.txt'
        broken = pinned_trace(graph([parent, child]), 'memory:T')
        self.assertEqual(broken['unresolved_pins'][0]['reason'], 'PROVENANCE_DIGEST_MISMATCH')
        child['dependency_pins'] = {}
        seal(child)
        missing = pinned_trace(graph([parent, child]), 'memory:T')
        self.assertEqual(missing['unresolved_pins'][0]['reason'], 'DEPENDENCY_BINDING_INVALID')


if __name__ == '__main__': unittest.main()
