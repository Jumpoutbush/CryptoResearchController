"""Evaluator-side synthetic curation seeds; never copied into agent bundles."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from evaluation import cases, registry, schema, scoring, validate_cases


def fixture_oracle(task):
    """Create a temporary evaluator oracle from independently curated fixtures."""
    category=task['category']; data=task['public_input']; first=task['sources'][0]
    if category=='THEOREM_COVERAGE':
        evidence={'kind':'CURATED_WRITTEN_DERIVATION','source_file':first['file'],'source_sha256':first['sha256'],
            'source_version':first['version'],'locator':first['locator'],'mapping':copy.deepcopy(data['candidate_scope']),
            'review_note':'Independent synthetic derivation review: distributivity expands the square and commutativity combines both cross terms under the exact integer scope.'}
        expected={'decision':'COVERED'}
    elif category=='COUNTEREXAMPLE': evidence={'kind':'EXACT_INTEGER_WITNESS','witness':{'a':0,'q':2}}; expected={'decision':'COUNTEREXAMPLE'}
    elif category=='SECURITY_FLAW':
        evidence={'kind':'TWO_TOY_TRANSCRIPTS','worlds':[{'x1':1,'x2':2,'y1':3,'y2':5},{'x1':2,'x2':1,'y1':3,'y2':4}]}
        expected={'decision':'LEAKAGE_FOUND'}
    elif category=='OPEN_BOUNDARY':
        evidence={'kind':'OPEN_BOUNDARY_ONLY','unresolved_obligations':copy.deepcopy(data['open_obligations'])}; expected={'decision':'OPEN'}
    elif category=='RESEARCH_DRIFT':
        reference=schema.read(schema.CONTROLLER/'tests/research_benchmark/supervision_cases.json')
        original=next(c for c in reference['cases'] if c['id']==data['legacy_fixture_adapter']['id'])['expected']
        evidence={'kind':'ORIGINAL_RECEIPT_REPLAY','adapter':'supervision_quality.assess_quality'}
        expected={'decision':original['assessment'],'finding_codes':sorted(original['finding_codes'])}
    else:
        evidence={'kind':'FROZEN_LOCAL_AFTERIMAGE'}
        expected={'decision':'RECOVER_LOCAL_AFTERIMAGE','afterimage_sha256':data['afterimage_sha256'],'redispatch':False,
            'preserved_run_ids':['synthetic-reserved-run']}
    return {'schema_version':1,'category':category,'evidence':evidence,'expected':expected}


def fixture_response(task):
    oracle=fixture_oracle(task); evidence=oracle['evidence']; category=task['category']; data=task['public_input']
    answer={k:task[k] for k in ('case_id','version','input_sha256')}; answer['decision']=oracle['expected']['decision']
    if category=='THEOREM_COVERAGE':
        answer.update(source={k:evidence[k] for k in ('source_file','source_sha256','source_version','locator')},coverage_mapping=copy.deepcopy(evidence['mapping']))
    elif category=='COUNTEREXAMPLE': answer['witness']=copy.deepcopy(evidence['witness'])
    elif category=='SECURITY_FLAW': answer.update(worlds=copy.deepcopy(evidence['worlds']),recovered_expression=data['recovered_expression'],scope='EXACT_TWO_QUERY_TOY_ONLY')
    elif category=='OPEN_BOUNDARY': answer.update(frozen_model=copy.deepcopy(data['frozen_model']),unresolved_obligations=copy.deepcopy(evidence['unresolved_obligations']),proof_status='UNRESOLVED')
    elif category=='RESEARCH_DRIFT': answer['finding_codes']=copy.deepcopy(oracle['expected']['finding_codes'])
    else: answer.update({k:v for k,v in oracle['expected'].items() if k!='decision'})
    return answer


class BenchmarkScoringTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='r16 evaluator fixture '); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.private=self.root/'evaluator-only'; self.views={}
        for item in cases.list_cases()['cases']:
            view=cases.public_view(item['case_id']); task=view['task']; self.views[task['category']]=view
            registry.register(self.private,task['case_id'],fixture_oracle(task),reviewer='independent-fixture-curator',
                reason='Independent offline review of the exact synthetic derivation, predicate, or finite-state boundary.')

    def task(self,category): return self.views[category]['task']
    def score(self,category,response=None):
        task=self.task(category)
        return scoring.score_fixture(task['case_id'],response or fixture_response(task),private_root=self.private)

    def test_all_six_curated_fixture_responses_score_without_scientific_or_formal_acceptance(self):
        self.assertEqual(validate_cases.validate_dataset(private_root=self.private)['status'],'CALIBRATION_READY')
        with mock.patch('subprocess.Popen',side_effect=AssertionError('No child or candidate code execution')):
            for category in schema.CATEGORIES:
                with self.subTest(category=category):
                    result=self.score(category); self.assertEqual(result['status'],'PASS',result)
                    self.assertFalse(result['formal_counted']); self.assertFalse(result['scientific_acceptance'])
                    self.assertEqual(result['quality_gain'],'NOT_MEASURED'); self.assertEqual(result['isolation_status'],'NOT_ISOLATED')

    def test_each_category_rejects_an_incorrect_answer_without_private_values_in_feedback(self):
        for category in schema.CATEGORIES:
            response=fixture_response(self.task(category)); response['decision']='UNSUPPORTED_CERTAINTY'
            with self.subTest(category=category):
                result=self.score(category,response); self.assertEqual(result['status'],'FAIL')
                self.assertNotIn('expected',json.dumps(result)); self.assertNotIn(str(self.private),json.dumps(result))

    def test_any_valid_counterexample_is_accepted_but_violated_precondition_is_not(self):
        answer=fixture_response(self.task('COUNTEREXAMPLE')); answer['witness']={'a':6,'q':3}
        self.assertEqual(self.score('COUNTEREXAMPLE',answer)['status'],'PASS')
        answer['witness']={'a':3,'q':2}
        self.assertEqual(self.score('COUNTEREXAMPLE',answer)['status'],'FAIL')

    def test_wrong_security_reduction_or_unequal_ideal_worlds_are_rejected(self):
        answer=fixture_response(self.task('SECURITY_FLAW')); answer['recovered_expression']='y1-y2'
        self.assertEqual(self.score('SECURITY_FLAW',answer)['status'],'FAIL')
        answer=fixture_response(self.task('SECURITY_FLAW')); answer['worlds'][1]['y1']=4
        self.assertEqual(self.score('SECURITY_FLAW',answer)['status'],'FAIL')

    def test_open_problem_is_scored_for_boundary_without_requiring_a_new_proof(self):
        answer=fixture_response(self.task('OPEN_BOUNDARY')); self.assertEqual(self.score('OPEN_BOUNDARY',answer)['status'],'PASS')
        answer['proof_status']='PROVED'; self.assertEqual(self.score('OPEN_BOUNDARY',answer)['status'],'FAIL')
        answer=fixture_response(self.task('OPEN_BOUNDARY')); answer['frozen_model']['corruption_threshold']=0
        self.assertEqual(self.score('OPEN_BOUNDARY',answer)['status'],'FAIL')

    def test_open_frozen_numeric_threshold_cannot_be_replaced_by_boolean_true(self):
        answer=fixture_response(self.task('OPEN_BOUNDARY')); answer['frozen_model']['corruption_threshold']=True
        self.assertEqual(self.score('OPEN_BOUNDARY',answer)['status'],'FAIL')

    def test_coverage_omitted_assumption_or_wrong_source_version_cannot_pass(self):
        answer=fixture_response(self.task('THEOREM_COVERAGE')); answer['coverage_mapping']['assumptions']=[]
        self.assertEqual(self.score('THEOREM_COVERAGE',answer)['status'],'FAIL')
        answer=fixture_response(self.task('THEOREM_COVERAGE')); answer['source']['source_version']='v-other'
        self.assertEqual(self.score('THEOREM_COVERAGE',answer)['status'],'FAIL')

    def test_recovery_cannot_redispatch_or_discard_the_original_unknown_run(self):
        answer=fixture_response(self.task('STATE_RECOVERY')); answer['redispatch']=True
        self.assertEqual(self.score('STATE_RECOVERY',answer)['status'],'FAIL')
        answer=fixture_response(self.task('STATE_RECOVERY')); answer['preserved_run_ids']=[]
        self.assertEqual(self.score('STATE_RECOVERY',answer)['status'],'FAIL')

    def test_recovery_oracle_rejects_reassigned_owner_or_rewritten_original_call(self):
        for scenario in ('owner','unknown-status','terminal-status','duplicate-owner','duplicate-run'):
            with self.subTest(scenario=scenario):
                task=copy.deepcopy(self.task('STATE_RECOVERY')); data=task['public_input']
                before={'attempts':[{'id':'attempt-0001','calls':[{'run_id':'synthetic-reserved-run','status':'RESERVED','payload':'frozen original reservation'}]}]}
                after=copy.deepcopy(before)
                if scenario=='owner': after['attempts'][0]['id']='attempt-0002'
                elif scenario=='unknown-status': after['attempts'][0]['calls'][0]['status']='COMPLETE'
                elif scenario=='terminal-status': after['attempts'][0]['calls'][0]['status']='FAILED'
                elif scenario=='duplicate-owner': after['attempts'].append(copy.deepcopy(after['attempts'][0]))
                else: after['attempts'][0]['calls'].append(copy.deepcopy(after['attempts'][0]['calls'][0]))
                data.update(before_image=before,pending_afterimage=after,before_sha256=schema.digest(before),
                    afterimage_sha256=schema.digest(after),actual_sha256=schema.digest(before)); task['input_sha256']=schema.digest(data)
                with self.assertRaisesRegex(ValueError,'owner|call|phase|identity|consumption'):
                    scoring.validate_oracle(task,fixture_oracle(task))

    def test_caller_isolation_or_scientific_self_rating_is_not_a_scoring_input(self):
        answer=fixture_response(self.task('COUNTEREXAMPLE')); answer.update(isolation_status='ISOLATED',scientific_acceptance=True)
        result=self.score('COUNTEREXAMPLE',answer)
        self.assertEqual(result['status'],'FAIL'); self.assertFalse(result['formal_counted'])
        with self.assertRaises(TypeError):
            scoring.score_fixture('BENCH-CE-001',answer,private_root=self.private,isolation_verified=True)

    def test_oracle_mutation_or_evaluator_revision_makes_old_results_stale(self):
        entry=registry.history(self.private,'BENCH-CE-001')['entries'][0]
        path=self.private/entry['oracle_file']; raw=path.read_bytes(); path.write_bytes(raw+b' ')
        self.assertEqual(self.score('COUNTEREXAMPLE')['status'],'STALE_OR_INVALID'); path.write_bytes(raw)
        with mock.patch.object(schema,'EVALUATOR_VERSION','changed-evaluator'):
            self.assertEqual(self.score('COUNTEREXAMPLE')['status'],'STALE_OR_INVALID')

    def test_immutable_registration_rejects_same_version_replacement_and_history_loss(self):
        task=self.task('THEOREM_COVERAGE'); oracle=fixture_oracle(task); oracle['evidence']['review_note']+=' A changed private review.'
        with self.assertRaisesRegex(ValueError,'frozen oracle'):
            registry.register(self.private,task['case_id'],oracle,reviewer='independent-fixture-curator',reason='Independent offline review of the exact synthetic derivation, predicate, or finite-state boundary.')
        path=self.private/'registry.json'; value=schema.read(path); value['entries'].pop(); path.write_bytes(schema.canonical_bytes(value))
        with self.assertRaisesRegex(ValueError,'truncated|orphaned'): registry.history(self.private)

    def test_orphaned_private_file_stops_history_even_when_tail_record_was_deleted(self):
        path=self.private/'registry.json'; value=schema.read(path); tail=value['entries'].pop()
        path.write_bytes(schema.canonical_bytes(value))
        (self.private/registry._record_name(tail['case_id'],tail['version'])).unlink()
        self.assertTrue((self.private/tail['oracle_file']).exists())
        with self.assertRaisesRegex(ValueError,'orphaned|truncated'): registry.history(self.private)
        orphan=self.root/'interrupted-oracle-only'; source=self.private/tail['oracle_file']; target=orphan/tail['oracle_file']
        target.parent.mkdir(parents=True); target.write_bytes(source.read_bytes())
        with self.assertRaisesRegex(ValueError,'orphaned|lost'): registry.history(orphan)

    def test_new_public_version_preserves_old_curation_and_records_responsibility_diff(self):
        dataset=self.root/'public-dataset'; shutil.copytree(schema.root_path(),dataset)
        manifest=schema.read(dataset/'manifest.json'); original=self.task('THEOREM_COVERAGE'); revised=copy.deepcopy(original)
        revised['version']=2; revised['public_input']['scope_clarification']='Same exact integer obligation, explicit new task revision.'
        revised['input_sha256']=schema.digest(revised['public_input'])
        relative='public/BENCH-LIT-001/v2/task.json'; path=dataset/relative; path.parent.mkdir(parents=True); path.write_bytes(schema.canonical_bytes(revised))
        manifest['cases'].append({'case_id':revised['case_id'],'version':2,'category':revised['category'],'task_file':relative,
            'task_sha256':schema.sha_file(path),'input_sha256':revised['input_sha256']}); (dataset/'manifest.json').write_bytes(schema.canonical_bytes(manifest))
        registry.register(self.private,revised['case_id'],fixture_oracle(revised),reviewer='second-independent-curator',
            reason='Independent review of the explicit version-two clarification with the previous source derivation preserved.',version=2,root=dataset)
        result=registry.diff(self.private,revised['case_id'],1,2,root=dataset)
        self.assertIn('input_sha256',result['changed_fields']); self.assertEqual(result['responsibility']['after']['reviewer'],'second-independent-curator')
        self.assertEqual(scoring.score_fixture(original['case_id'],fixture_response(original),private_root=self.private,version=1,root=dataset)['status'],'PASS')
