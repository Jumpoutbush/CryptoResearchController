"""R13 fixed trusted workers and immutable, non-authoritative verification receipts."""
import copy
import json
import subprocess
import unittest
from unittest import mock
import configuration
import test_candidate_contract as fixture
from candidate_search import catalog
from candidate_search.verifiers import interface
from engine import claim_graph, falsification, formal_verifier


class VerifierAdapterTests(unittest.TestCase):
    setUp=fixture.CandidateContractTests.setUp
    tearDown=fixture.CandidateContractTests.tearDown
    put=fixture.CandidateContractTests.put
    claim=fixture.CandidateContractTests.claim
    files=fixture.CandidateContractTests.files
    candidate_spec=fixture.CandidateContractTests.candidate_spec
    make=fixture.CandidateContractTests.make
    spec_problem=fixture.CandidateContractTests.spec_problem
    add=fixture.CandidateContractTests.add

    def prepare(self,statement=None,**options):
        self.add()
        self.claim('CLAIM-1',machine_statement=statement or {'domain':'INTEGER','variables':['x'],
            'preconditions':[],'conclusion':'x*x == x'})
        return interface.prepare_request(self.project,'C-0001','CLAIM-1',**options)

    def test_false_polynomial_has_exact_recheckable_counterexample(self):
        request=self.prepare()
        before=(self.project/'research/discovery/CLAIM_GRAPH.json').read_bytes()
        receipt=interface.verify(self.project,request)
        self.assertEqual(receipt['result_status'],'COUNTEREXAMPLE_FOUND')
        self.assertTrue(interface.recheck(self.project,request['request_id'])['certificate_valid'])
        self.assertEqual((self.project/'research/discovery/CLAIM_GRAPH.json').read_bytes(),before)
        self.assertFalse(receipt['scientific_acceptance'])

    def test_bounded_10000_points_is_not_a_proof(self):
        request=self.prepare({'domain':'INTEGER','variables':['x','y'],
            'preconditions':[],'conclusion':'x*x + y*y >= 0'},low=0,high=99,max_cases=10000)
        receipt=interface.verify(self.project,request)
        self.assertEqual(receipt['result_status'],'NO_COUNTEREXAMPLE_WITHIN_BOUND')
        self.assertEqual(receipt['result']['tested_cases'],10000)
        self.assertNotIn('PROVED',receipt['result_status'])

    def test_request_and_receipt_bind_exact_versions_and_sources(self):
        request=self.prepare(); receipt=interface.verify(self.project,request)
        for key in ('claim_binding','source_hashes','adapter_id','tool_version','result_status',
                    'evidence_files','reproduction_command','limitations'):
            self.assertIn(key,receipt)
        self.assertEqual(receipt['claim_binding']['claim_revision'],1)
        self.assertEqual(receipt['claim_binding']['candidate_revision'],1)

    def test_same_frozen_request_is_replayed_without_worker(self):
        request=self.prepare(); first=interface.verify(self.project,request)
        with mock.patch('candidate_search.verifiers.integer_adapter.execute',side_effect=AssertionError('No redispatch')):
            second=interface.verify(self.project,request)
        self.assertEqual(first,second)

    def test_mutated_source_makes_old_receipt_inapplicable(self):
        request=self.prepare(); interface.verify(self.project,request)
        self.put('proofs/derivation.md','Changed exact original evidence')
        result=interface.recheck(self.project,request['request_id'])
        self.assertFalse(result['fresh']); self.assertFalse(result['certificate_valid'])

    def test_claim_revision_makes_old_receipt_inapplicable(self):
        request=self.prepare(); interface.verify(self.project,request)
        self.claim('CLAIM-1',statement='A revised exact claim statement')
        self.assertFalse(interface.recheck(self.project,request['request_id'])['fresh'])

    def test_candidate_revision_makes_old_receipt_inapplicable(self):
        request=self.prepare(); interface.verify(self.project,request)
        catalog.propose(self.project,self.make(hypothesis='A new exact candidate construction'),
            'Explicit candidate revision',revise=True,expected_revision=1)
        self.assertFalse(interface.recheck(self.project,request['request_id'])['fresh'])

    def test_wrong_request_hash_is_failed_without_process(self):
        request=self.prepare(); request['claim_binding']['claim_revision']=2
        with mock.patch('subprocess.Popen',side_effect=AssertionError('No process for corrupt request')):
            receipt=interface.verify(self.project,request)
        self.assertEqual(receipt['result_status'],'FAILED')

    def test_unknown_adapter_is_unsupported_without_process(self):
        request=self.prepare(adapter_id='unknown-adapter')
        with mock.patch('subprocess.Popen',side_effect=AssertionError('No unknown tool')):
            receipt=interface.verify(self.project,request)
        self.assertEqual(receipt['result_status'],'UNSUPPORTED')

    def test_worker_exception_records_failed_without_science_changes(self):
        request=self.prepare(); before=(self.project/'research/discovery/CLAIM_GRAPH.json').read_bytes()
        with mock.patch('candidate_search.verifiers.integer_adapter.execute',side_effect=RuntimeError('injected worker failure')):
            receipt=interface.verify(self.project,request)
        self.assertEqual(receipt['result_status'],'FAILED')
        self.assertEqual((self.project/'research/discovery/CLAIM_GRAPH.json').read_bytes(),before)

    def test_real_integer_worker_wall_timeout_is_reaped_and_recorded(self):
        request=self.prepare(wall_timeout_seconds=0.000001)
        receipt=interface.verify(self.project,request)
        self.assertEqual(receipt['result_status'],'FAILED')
        self.assertEqual(receipt['tool_status'],'TIMEOUT')
        self.assertTrue(receipt['execution_started'])

    def test_missing_python_worker_tool_is_failed_without_claim_mutation(self):
        request=self.prepare()
        with mock.patch('candidate_search.verifiers.integer_adapter.ProcessTree.start',side_effect=FileNotFoundError('missing Python')):
            receipt=interface.verify(self.project,request)
        self.assertEqual(receipt['result_status'],'FAILED')
        self.assertFalse(receipt['execution_started'])

    def test_existing_resource_policy_can_only_reduce_adapter_bounds(self):
        request=self.prepare()
        settings=configuration.load_json(self.root/'config/projects/example.json',{'schema_version':1})
        settings['discovery_policy']={'counterexample_max_cases':2,'counterexample_max_seconds':1,'verifier_timeout_seconds':1}
        configuration.atomic_json(self.root/'config/projects/example.json',settings)
        limited=interface.prepare_request(self.project,'C-0001','CLAIM-1')
        self.assertEqual(limited['options']['max_cases'],2)
        self.assertEqual(limited['options']['max_seconds'],1)
        self.assertEqual(limited['options']['wall_timeout_seconds'],1)
        self.assertNotEqual(request['request_id'],limited['request_id'])
        self.assertEqual(interface.verify(self.project,request)['result_status'],'FAILED')

    def test_integer_predicate_rejects_arbitrary_code_and_unsupported_domain(self):
        for statement in ({'domain':'INTEGER','variables':['x'],'preconditions':[],
                           'conclusion':"__import__('os').system('echo forbidden') == 0"},
                          {'domain':'REAL','variables':['x'],'preconditions':[],'conclusion':'x*x >= 0'}):
            with self.subTest(statement=statement), self.assertRaises(ValueError): falsification.search_statement(statement)

    def test_deleted_completed_receipt_is_unknown_without_worker_retry(self):
        request=self.prepare(); interface.verify(self.project,request)
        interface._paths(self.project,request['request_id'])['receipt'].unlink()
        with mock.patch('candidate_search.verifiers.integer_adapter.execute',side_effect=AssertionError('No retry')):
            result=interface.verify(self.project,request)
        self.assertEqual(result['result_status'],'FAILED'); self.assertIn('UNKNOWN_LOCAL_VERIFICATION_OUTCOME',str(result))

    def test_read_only_recheck_does_not_dispatch_a_second_search(self):
        request=self.prepare(); interface.verify(self.project,request); before=self.files()
        with mock.patch('subprocess.Popen',side_effect=AssertionError('No certificate re-search')):
            self.assertTrue(interface.recheck(self.project,request['request_id'])['certificate_valid'])
        self.assertEqual(before,self.files())

    def test_prepare_is_deterministic_and_does_not_write_any_files(self):
        first=self.prepare(); before=self.files()
        second=interface.prepare_request(self.project,'C-0001','CLAIM-1')
        self.assertEqual(first,second); self.assertEqual(before,self.files())

    def test_started_without_result_is_unknown_and_never_retried(self):
        request=self.prepare()
        with mock.patch('candidate_search.verifiers.integer_adapter.execute',side_effect=KeyboardInterrupt('hard interruption')):
            with self.assertRaises(KeyboardInterrupt): interface.verify(self.project,request)
        with mock.patch('candidate_search.verifiers.integer_adapter.execute',side_effect=AssertionError('No retry')):
            receipt=interface.verify(self.project,request)
        self.assertEqual(receipt['result_status'],'FAILED')
        self.assertIn('UNKNOWN_LOCAL_VERIFICATION_OUTCOME',str(receipt))

    def test_false_worker_witness_is_not_accepted(self):
        request=self.prepare()
        with mock.patch('candidate_search.verifiers.integer_adapter.execute',return_value={
                'result_status':'COUNTEREXAMPLE_FOUND','result':{'witness':{'assignment':{'x':1}}},
                'execution_started':True,'tool_version':'mocked trusted-output fault'}):
            receipt=interface.verify(self.project,request)
        self.assertEqual(receipt['result_status'],'FAILED')

    def lean_request(self,text='theorem target : True := by trivial'):
        self.put('proofs/lean/Main.lean',text)
        self.put('proofs/lean/lean-toolchain','leanprover/lean4:v4.19.0')
        self.put('proofs/lean/lake-manifest.json',{'version':'1.1.0','packages':[]})
        return self.prepare(adapter_id='lean-v1',proof_file='proofs/lean/Main.lean',declaration='target')

    def test_lean_true_does_not_certify_original_statement_or_start_process(self):
        request=self.lean_request()
        with (mock.patch('subprocess.Popen',side_effect=AssertionError('Lean execution must remain blocked')),
                mock.patch('engine.formal_verifier.shutil.which',return_value='elan.exe')):
            receipt=interface.verify(self.project,request)
        self.assertEqual(receipt['result_status'],'UNSUPPORTED')
        self.assertEqual(receipt['tool_status'],'ISOLATION_UNCERTIFIED')
        self.assertEqual(receipt['statement_match'],'REQUIRES_INDEPENDENT_REVIEW')
        self.assertFalse(receipt['execution_started'])
        self.assertIn('TRIVIAL_TRUE_DECLARATION',str(receipt['diagnostics']))

    def test_lean_missing_tool_is_explicit_unavailable_no_download(self):
        request=self.lean_request()
        with mock.patch('engine.formal_verifier.shutil.which',return_value=None):
            receipt=interface.verify(self.project,request)
        self.assertEqual(receipt['result_status'],'UNSUPPORTED'); self.assertEqual(receipt['tool_status'],'UNAVAILABLE')

    def test_lean_sorry_is_failed_and_natural_semantics_stays_pending(self):
        request=self.lean_request('theorem target : True := by sorry')
        with mock.patch('engine.formal_verifier.shutil.which',return_value='elan.exe'):
            receipt=interface.verify(self.project,request)
        self.assertEqual(receipt['result_status'],'FAILED')

    def test_legacy_integer_search_and_shared_pure_helper_agree(self):
        request=self.prepare(); statement=request['statement']
        pure=falsification.search_statement(statement,-3,3)
        legacy=falsification.search(self.project,'CLAIM-1',-3,3)
        self.assertEqual(pure['witness'],legacy['witness']); self.assertEqual(pure['status'],legacy['status'])

    def test_legacy_lean_run_still_records_blocked_receipt(self):
        self.lean_request()
        with mock.patch('engine.formal_verifier.shutil.which',return_value='elan.exe'):
            receipt=formal_verifier.run(self.project,'CLAIM-1','proofs/lean/Main.lean','target')
        self.assertEqual(receipt['status'],'ISOLATION_UNCERTIFIED')
        self.assertEqual(claim_graph.get(self.project,'CLAIM-1')['formal_receipt'],receipt)
