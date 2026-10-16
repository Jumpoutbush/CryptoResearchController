"""F02: no public entry may execute candidate Lean on the controller host."""
import copy
import json
import os
from pathlib import Path
import unittest
from unittest import mock

import configuration
import test_discovery as fixtures
from engine import claim_graph, formal_verifier, verification_engine


class FormalBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.DiscoveryTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.project = self.fixture.project
        self.sentinel = self.fixture.root / 'outside-project-sentinel.txt'
        payload = '#eval IO.FS.writeFile ' + json.dumps(str(self.sentinel)) + ' "candidate executed"\n'
        self.fixture.put('proofs/lean/Check.lean', payload + 'theorem target : True := True.intro\n')
        self.fixture.put('proofs/lean/lean-toolchain', 'leanprover/lean4:v4.29.1')
        self.fixture.put('proofs/lean/lake-manifest.json', {'version': '1.1.0', 'packages': []})
        self.spec = self.fixture.claim(verification_mode='FORMAL_REQUIRED',
            formal_target={'file': 'proofs/lean/Check.lean', 'declaration': 'target'})

    def source_bytes(self):
        return {p.relative_to(self.project).as_posix(): p.read_bytes()
                for p in (self.project / 'proofs/lean').rglob('*') if p.is_file()}

    def assert_blocked(self, receipt):
        self.assertEqual(receipt['status'], 'ISOLATION_UNCERTIFIED')
        self.assertEqual(receipt['isolation'], 'NOT_IMPLEMENTED')
        self.assertFalse(receipt['execution_started'])
        self.assertFalse(self.sentinel.exists())
        self.assertFalse((self.fixture.root / 'logs').exists())
        self.assertFalse(list(self.project.rglob('ControllerAudit_*.lean')))

    def test_direct_candidate_is_blocked_before_any_process_or_audit_copy(self):
        before = self.source_bytes()
        with mock.patch.object(formal_verifier.shutil, 'which', return_value='/fixture/elan'), \
                mock.patch.object(formal_verifier.subprocess, 'run',
                    return_value=mock.Mock(returncode=0, stdout='Fixture Lean version', stderr='')) as probe, \
                mock.patch.object(formal_verifier.subprocess, 'Popen',
                    return_value=mock.Mock(wait=mock.Mock(return_value=0))) as child, \
                mock.patch.dict(os.environ, {'FORMAL_HOST_SECRET': 'fixture-secret'}):
            receipt = formal_verifier.run(self.project, 'C-1', 'proofs/lean/Check.lean', 'target')
            self.assertEqual(probe.call_count, 0, 'Lean version probe reached the host boundary')
            self.assertEqual(child.call_count, 0, 'Lean candidate reached the host boundary')
        self.assert_blocked(receipt)
        self.assertEqual(self.source_bytes(), before)
        self.assertNotIn('fixture-secret', json.dumps(receipt))
        self.assertEqual(claim_graph.get(self.project, 'C-1')['formal_receipt'], receipt)
        self.assertEqual(claim_graph.status(self.project)['claims'][0]['formal_status'], 'NOT_VERIFIED')

    def test_accepted_candidate_pipeline_cannot_bypass_the_gate(self):
        (self.project / 'research/discovery/CLAIM_GRAPH.json').unlink()
        relative = 'research/attempts/fixture/proposals/C-1.json'
        self.fixture.put(relative, copy.deepcopy(self.spec))
        checkpoint = {'run_id': 'run-fixture', 'attempt_id': 'attempt-fixture',
                      'evidence': {}, 'candidate_claim_files': [relative]}
        before = self.source_bytes()
        config = dict(verification_engine.policy(self.project), automatic_falsification=False)
        with mock.patch.object(verification_engine, 'policy', return_value=config), \
                mock.patch.object(formal_verifier.shutil, 'which', return_value='/fixture/elan'), \
                mock.patch.object(formal_verifier.subprocess, 'run',
                    return_value=mock.Mock(returncode=0, stdout='Fixture Lean version', stderr='')) as probe, \
                mock.patch.object(formal_verifier.subprocess, 'Popen',
                    return_value=mock.Mock(wait=mock.Mock(return_value=0))) as child:
            results = verification_engine.process_candidates(self.project, checkpoint)
            self.assertEqual(probe.call_count, 0, 'Lean version probe reached the host boundary')
            self.assertEqual(child.call_count, 0, 'Lean candidate reached the host boundary')
        self.assertEqual(results[0]['status'], 'CANDIDATE_IMPORTED')
        self.assertFalse(results[0]['accepted_as_proof'])
        self.assert_blocked(results[0]['formal_check'])
        self.assertEqual(self.source_bytes(), before)

    def test_explicit_verify_cli_is_also_blocked_before_process(self):
        before = self.source_bytes()
        with mock.patch.object(formal_verifier.shutil, 'which', return_value='/fixture/elan'), \
                mock.patch.object(formal_verifier.subprocess, 'run',
                    return_value=mock.Mock(returncode=0, stdout='Fixture Lean version', stderr='')) as probe, \
                mock.patch.object(formal_verifier.subprocess, 'Popen',
                    return_value=mock.Mock(wait=mock.Mock(return_value=0))) as child:
            code = self.fixture.cli(['verify', 'lean', 'example', '--claim', 'C-1',
                '--file', 'proofs/lean/Check.lean', '--declaration', 'target'])
            self.assertEqual(probe.call_count, 0, 'Lean version probe reached the host boundary')
            self.assertEqual(child.call_count, 0, 'Lean candidate reached the host boundary')
        self.assertEqual(code, 2)
        self.assert_blocked(claim_graph.get(self.project, 'C-1')['formal_receipt'])
        self.assertEqual(self.source_bytes(), before)

    def test_missing_optional_tool_remains_unavailable_without_process(self):
        with mock.patch.object(formal_verifier.shutil, 'which', return_value=None), \
                mock.patch.object(formal_verifier.subprocess, 'run',
                    return_value=mock.Mock(returncode=0, stdout='Fixture Lean version', stderr='')) as probe, \
                mock.patch.object(formal_verifier.subprocess, 'Popen',
                    return_value=mock.Mock(wait=mock.Mock(return_value=0))) as child:
            receipt = formal_verifier.run(self.project, 'C-1', 'proofs/lean/Check.lean', 'target')
            self.assertEqual(probe.call_count, 0, 'Lean version probe reached the host boundary')
            self.assertEqual(child.call_count, 0, 'Lean candidate reached the host boundary')
        self.assertEqual(receipt['status'], 'UNAVAILABLE')
        self.assertFalse(self.sentinel.exists())

    def test_manual_nonformal_reviews_keep_existing_approval_rules(self):
        self.fixture.claim('C-MANUAL')
        self.fixture.review_proof('C-MANUAL')
        states = {item['id']: item for item in claim_graph.status(self.project)['claims']}
        self.assertEqual(states['C-MANUAL']['proof_status'], 'INDEPENDENTLY_REVIEWED')
        self.assertFalse(states['C-MANUAL']['accepted_contribution'])
        self.assertEqual(states['C-1']['proof_status'], 'CANDIDATE')


if __name__ == '__main__':
    unittest.main()
