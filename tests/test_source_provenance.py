"""Original PDF location binding, never a theorem or novelty certifier."""
import copy
import unittest
from unittest import mock

from engine import claim_graph
from research_quality import DIMENSIONS, hash_file
import test_knowledge_graph as fixture


class SourceProvenanceTests(unittest.TestCase):
    setUp = fixture.KnowledgeGraphTests.setUp
    put = fixture.KnowledgeGraphTests.put
    files = fixture.KnowledgeGraphTests.files
    legacy_claim = fixture.KnowledgeGraphTests.legacy_claim

    def seed(self):
        from scripts.r07_fixture import seed
        self.legacy_claim()
        return seed(self.project)

    def derive(self):
        from knowledge.build import derive
        return derive(self.root,self.project)

    def test_located_original_and_existing_review_trace_to_claim_without_promotion(self):
        self.seed(); before=self.files(self.root); old=claim_graph.status(self.project)
        g=self.derive(); spans=[n for n in g['nodes'] if n['kind']=='THEOREM_SPAN']
        self.assertEqual(len(spans),1); self.assertEqual(spans[0]['location_status'],'FULLTEXT_LOCATED')
        self.assertEqual(spans[0]['location']['page_start'],2)
        self.assertEqual(spans[0]['review_status'],'COVERS')
        self.assertTrue(any(e.get('provenance_kind')=='TECHNICAL_REVIEW_MAPPING' for e in g['edges']))
        self.assertEqual(before,self.files(self.root)); self.assertEqual(old,claim_graph.status(self.project))

    def test_same_title_versions_remain_separate_and_supersedes_is_explicit(self):
        self.seed(); g=self.derive()
        sources=[n for n in g['nodes'] if n.get('record_kind')=='PRIMARY_PAPER']
        self.assertEqual(len(sources),3); self.assertEqual(len({n['id'] for n in sources}),3)
        self.assertEqual(len([e for e in g['edges'] if e['relation']=='SUPERSEDES']),1)

    def change(self, transform):
        import configuration
        path=self.project/'literature/source_spans.json'; obj=configuration.load_json(path)
        transform(obj); self.put('literature/source_spans.json',obj)

    def test_fabricated_page_or_marker_rejected(self):
        self.seed(); self.change(lambda o:o['spans'][0]['location'].update(page_start=99,page_end=99))
        with self.assertRaisesRegex(ValueError,'location'): self.derive()

    def test_wrong_page_offset_rejected_even_with_valid_page_number(self):
        self.seed(); self.change(lambda o:o['spans'][0]['location'].update(page_start=1,page_end=1))
        with self.assertRaisesRegex(ValueError,'location'): self.derive()

    def test_traversal_rejected(self):
        self.seed(); self.change(lambda o:o['spans'][0].update(source_file='../outside.pdf'))
        with self.assertRaises(ValueError): self.derive()

    def test_review_pdf_pin_disagreement_rejected(self):
        self.seed(); self.change(lambda o:o['spans'][0].update(sha256='0'*64))
        with self.assertRaises(ValueError): self.derive()

    def test_pdf_change_keeps_old_pin_and_blocks_coverage(self):
        self.seed(); path=self.project/'literature/pdfs/toy-v1.pdf'; path.write_bytes(path.read_bytes()+b'\nchanged')
        span=next(n for n in self.derive()['nodes'] if n['kind']=='THEOREM_SPAN')
        self.assertEqual(span['location_status'],'SOURCE_HASH_MISMATCH'); self.assertFalse(span['decisive_eligible'])

    def test_extract_change_blocks_old_reference(self):
        self.seed(); self.put('literature/text/toy-v1.txt','replaced extract')
        span=next(n for n in self.derive()['nodes'] if n['kind']=='THEOREM_SPAN')
        self.assertEqual(span['location_status'],'EXTRACTION_HASH_MISMATCH'); self.assertFalse(span['decisive_eligible'])

    def test_missing_pdf_explicit_recovery(self):
        self.seed(); (self.project/'literature/pdfs/toy-v1.pdf').unlink()
        span=next(n for n in self.derive()['nodes'] if n['kind']=='THEOREM_SPAN')
        self.assertEqual(span['location_status'],'MISSING_PRIMARY_SOURCE'); self.assertTrue(span['recovery_action'])

    def test_missing_span_unknown_location_not_parsed_from_free_text(self):
        self.seed(); (self.project/'literature/source_spans.json').unlink()
        span=next(n for n in self.derive()['nodes'] if n['kind']=='THEOREM_SPAN')
        self.assertEqual(span['location_status'],'LOCATION_UNVERIFIED'); self.assertFalse(span['decisive_eligible'])

    def test_abstract_only_never_effective_covers(self):
        self.seed(); import configuration
        rel='literature/technical_reviews/toy.json'; obj=configuration.load_json(self.project/rel)
        obj['fulltext_status']='ABSTRACT_ONLY'; self.put(rel,obj)
        self.change(lambda o:o['spans'].clear())
        span=next(n for n in self.derive()['nodes'] if n['kind']=='THEOREM_SPAN')
        self.assertEqual(span['original_coverage_verdict'],'COVERS'); self.assertEqual(span['review_status'],'UNVERIFIED')

    def test_adversary_or_quantifier_conflict_never_decisive(self):
        self.seed(); import configuration
        rel='literature/technical_reviews/toy.json'; obj=configuration.load_json(self.project/rel)
        next(r for r in obj['comparison'] if r['dimension']=='adversary')['relation']='INCOMPARABLE'
        self.put(rel,obj); self.change(lambda o:o['spans'].clear())
        span=next(n for n in self.derive()['nodes'] if n['kind']=='THEOREM_SPAN')
        self.assertFalse(span['decisive_eligible']); self.assertEqual(span['review_status'],'UNVERIFIED')

    def test_uncertain_mathematics_kept_explicit(self):
        self.seed(); import configuration
        rel='literature/pdf_index.json'; obj=configuration.load_json(self.project/rel)
        obj['files']['toy-v1.pdf']['math_layout_verified']=False; self.put(rel,obj)
        span=next(n for n in self.derive()['nodes'] if n['kind']=='THEOREM_SPAN')
        self.assertEqual(span['math_render_status'],'MATH_RENDER_UNCERTAIN'); self.assertFalse(span['decisive_eligible'])

    def test_no_network_and_cache_rebuild_is_byte_identical(self):
        self.seed(); from knowledge.build import build,cache_path
        before=self.files()
        with mock.patch('urllib.request.urlopen',side_effect=AssertionError('Network forbidden')):
            build(self.root,self.project); p=cache_path(self.root,self.project); raw=p.read_bytes()
            p.unlink(); build(self.root,self.project); self.assertEqual(raw,p.read_bytes())
        self.assertEqual(before,self.files())

    def test_forged_extraction_with_updated_hash_cannot_forge_original_location(self):
        self.seed(); p=self.project/'literature/text/toy-v1.txt'; p.write_text('forged pages',encoding='utf8')
        self.change(lambda o:o['spans'][0]['extraction'].update(sha256=hash_file(p)))
        with self.assertRaisesRegex(ValueError,'location'): self.derive()

    def test_wrong_claim_spec_hash_rejected(self):
        self.seed(); self.change(lambda o:o['spans'][0].update(claim_spec_sha256='0'*64))
        with self.assertRaisesRegex(ValueError,'claim specification'): self.derive()

    def test_missing_parser_is_explicit_and_readonly(self):
        self.seed(); before=self.files()
        with mock.patch('knowledge.sources._pdf_pages',return_value=(None,None)):
            span=next(n for n in self.derive()['nodes'] if n['kind']=='THEOREM_SPAN')
        self.assertEqual(span['location_status'],'EXTRACTION_UNAVAILABLE'); self.assertFalse(span['decisive_eligible'])
        self.assertEqual(before,self.files())

    def test_duplicate_upload_record_has_gap_but_not_duplicate_identity(self):
        self.seed(); import configuration
        p=self.project/'literature/uploads.json'; obj=configuration.load_json(p); obj['files'].append(obj['files'][0])
        self.put('literature/uploads.json',obj); g=self.derive()
        self.assertTrue(any(s.startswith('DUPLICATE_UPLOAD:') for s in g['coverage_gaps']))
        self.assertEqual(len([n for n in g['nodes'] if n.get('record_kind')=='PRIMARY_PAPER']),3)

    def test_changed_review_pin_rejects_build_and_preserves_cache(self):
        self.seed(); from knowledge.build import build,cache_path
        build(self.root,self.project); raw=cache_path(self.root,self.project).read_bytes()
        p=self.project/'literature/technical_reviews/toy.json'; p.write_bytes(p.read_bytes()+b'\n')
        with self.assertRaises(ValueError): build(self.root,self.project)
        self.assertEqual(raw,cache_path(self.root,self.project).read_bytes())

    def test_duplicate_page_markers_cannot_hide_forged_text(self):
        self.seed(); p=self.project/'literature/text/toy-v1.txt'
        p.write_bytes(b'\n=== PDF PAGE 2 ===\nFAKE DATA TO HIDE\n'+p.read_bytes())
        self.change(lambda o:o['spans'][0]['extraction'].update(sha256=hash_file(p)))
        with self.assertRaisesRegex(ValueError,'location'): self.derive()

    def test_conflicting_version_metadata_never_overwrites_original(self):
        self.seed(); import configuration
        obj=configuration.load_json(self.project/'literature/technical_reviews/toy.json')
        obj['paper']['version']='conflicting-version'; rel='literature/technical_reviews/other.json'; self.put(rel,obj)
        def change(o):
            span=copy.deepcopy(o['spans'][0]); span.update(id='other',version='conflicting-version',
                review_file=rel,review_sha256=hash_file(self.project/rel)); o['spans'].append(span)
        self.change(change)
        with self.assertRaisesRegex(ValueError,'Conflicting metadata'): self.derive()

    def test_explicit_legacy_review_path_outside_conventional_subdirectory(self):
        self.seed(); old=self.project/'literature/technical_reviews/toy.json'; new=self.project/'literature/legacy-review.json'
        old.rename(new); self.change(lambda o:o['spans'][0].update(review_file='literature/legacy-review.json'))
        self.assertTrue(any(n.get('location_status')=='FULLTEXT_LOCATED' for n in self.derive()['nodes']))

    def test_invalid_nested_objects_have_controlled_diagnostics(self):
        self.seed()
        import configuration
        original=configuration.load_json(self.project/'literature/source_spans.json')
        for field,value in [('extraction',[]),('supersedes','invalid')]:
            with self.subTest(field=field):
                self.put('literature/source_spans.json',original)
                self.change(lambda o:o['spans'][0].update({field:value}))
                with self.assertRaises(ValueError): self.derive()

    def test_malformed_old_index_or_review_has_controlled_diagnostic(self):
        self.seed(); import configuration
        rel='literature/pdf_index.json'; original=configuration.load_json(self.project/rel)
        damaged=copy.deepcopy(original); damaged['files']['toy-v1.pdf']=[]; self.put(rel,damaged)
        with self.assertRaises(ValueError): self.derive()
        self.put(rel,original)
        rel='literature/technical_reviews/toy.json'; damaged=configuration.load_json(self.project/rel)
        damaged['derivation_paths']=None; self.put(rel,damaged)
        with self.assertRaises(ValueError): self.derive()


if __name__=='__main__': unittest.main()
