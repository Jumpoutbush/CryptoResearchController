import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import literature

class LiteratureTests(unittest.TestCase):
    def test_all_queries_rotate_and_catalog_retains_prior(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=Path(tmp); lit=project/'literature'; lit.mkdir()
            (lit/'queries.json').write_text(json.dumps({'queries':['query '+str(i) for i in range(24)],'keywords':[],'eprint_rss':False}),encoding='utf8')
            batches=[]
            def metadata(q,*args):
                batches.append(list(q))
                return [{'doi':term,'title':term,'url':'https://example.invalid/'+term,'source':'mock'} for term in q]
            policy={'literature':{'automatic_pdf_download':False,'max_pdf_downloads_per_round':3,'max_pdf_mb':25}}
            with patch.object(literature,'fetch_crossref',side_effect=metadata),patch.object(literature,'settings_for',return_value=policy):
                for i in range(3): literature.update_literature(project)
                history=(lit/'SEARCH_COVERAGE.json').read_bytes()
                literature.update_literature(project,offline=True)
                self.assertEqual(history,(lit/'SEARCH_COVERAGE.json').read_bytes())
                result=literature.update_literature(project)
            self.assertEqual(len(set(sum(batches[:3],[]))),24)
            self.assertEqual(len(json.loads((lit/'CATALOG.json').read_text())['items']),24)
            self.assertEqual(result['new_candidate_count'],0)

    def test_downloads_use_controller_policy_not_query_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=Path(tmp);lit=project/'literature';lit.mkdir()
            (lit/'queries.json').write_text(json.dumps({'queries':[],'eprint_rss':False,'download_open_pdfs':True}),encoding='utf8')
            policy={'literature':{'automatic_pdf_download':False,'max_pdf_downloads_per_round':3,'max_pdf_mb':25}}
            with patch.object(literature,'settings_for',return_value=policy),patch.object(literature,'download_open_pdfs') as downloader:
                literature.update_literature(project)
                downloader.assert_not_called()

if __name__=='__main__': unittest.main()
