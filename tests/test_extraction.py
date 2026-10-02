import json
import tempfile
import unittest
from pathlib import Path

from chain_eye.adapters.pymupdf import PyMuPDFParser
from chain_eye.adapters.sqlite import SQLiteRepository
from chain_eye.application.extraction import AnnualReportExtractor
from chain_eye.domain.contracts import Evidence,Fact
from chain_eye.domain.datasets import Dataset,DatasetCreate,Source
from chain_eye.domain.extraction import DocumentPage,DocumentPages,ExtractionResult

ROOT=Path(__file__).resolve().parents[1]


class DeterministicExtraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads((ROOT/'data/source_manifest.json').read_text(encoding='utf-8'))
        cls.gold=json.loads((ROOT/'data/fixtures/facts.json').read_text(encoding='utf-8'))
        cls.gold_by_key={(item['period_end'][:4],item['segment'],item['metric']):item for item in cls.gold}
        cls.dataset=Dataset(id='extraction-test',name='gold extraction',company='CATL',year=2025,version=1,source_ids=[item['id'] for item in cls.manifest],created_at='2026-10-01T00:00:00+00:00',data_basis='user_uploaded')

    def source(self,item):
        return Source(id=item['id'],filename=Path(item['path']).name,sha256=item['sha256'],media_type='application/pdf',page_count=item['pages'],url=item['url'],published_date=item['published_date'],parse_status='queued',data_basis='user_uploaded')

    def test_30_gold_fields_match_before_manual_correction(self):
        actual=[]
        for item in self.manifest:
            document=PyMuPDFParser().parse(item['id'],(ROOT/item['path']).read_bytes())
            result=AnnualReportExtractor().extract(self.dataset,self.source(item),document)
            self.assertEqual(result.parse_status,'parsed',[(fact.metric,fact.segment) for fact in result.facts if fact.status=='missing'])
            self.assertEqual(len(result.facts),15)
            self.assertTrue(all(fact.status=='extracted' for fact in result.facts))
            actual.extend(result.facts)
        self.assertEqual(len(actual),30)
        for fact in actual:
            expected=self.gold_by_key[(fact.period_end[:4],fact.segment,fact.metric)]
            self.assertEqual(fact.raw_value,expected['raw_value'])
            self.assertEqual(fact.value,expected['value'])
            self.assertEqual(fact.raw_unit,expected['raw_unit'])
            self.assertEqual(fact.unit,expected['unit'])
            self.assertEqual(fact.period_kind,expected['period_kind'])
            self.assertEqual(fact.statement_scope,'consolidated')
            self.assertEqual(len(fact.evidence_ids),1)

    def test_segment_evidence_uses_cost_and_margin_table(self):
        expected_pages={'2024':20,'2025':25}
        for item in self.manifest:
            document=PyMuPDFParser().parse(item['id'],(ROOT/item['path']).read_bytes())
            result=AnnualReportExtractor().extract(self.dataset,self.source(item),document)
            evidence={entry.id:entry for entry in result.evidence}
            for fact in result.facts:
                if fact.segment!='group':self.assertEqual(evidence[fact.evidence_ids[0]].pdf_page,expected_pages[fact.period_end[:4]])

    def test_missing_unit_context_does_not_extract_values(self):
        page=DocumentPage(page_no=1,text='宁德时代新能源科技股份有限公司2025年年度报告全文\n主要会计数据和财务指标\n营业收入 123',words=(),blocks=(),table_candidates=(),parse_warnings=())
        document=DocumentPages(source_id='synthetic',page_count=1,pages=(page,))
        source=Source(id='synthetic',filename='synthetic.pdf',sha256='0'*64,media_type='application/pdf',page_count=1,url=None,published_date=None,parse_status='queued',data_basis='user_uploaded')
        result=AnnualReportExtractor().extract(self.dataset,source,document)
        self.assertEqual(result.parse_status,'needs_review')
        self.assertEqual(len(result.facts),15)
        self.assertTrue(all(fact.status=='missing' and fact.value is None for fact in result.facts))

    def test_non_catl_document_is_not_treated_as_supported_report(self):
        page=DocumentPage(page_no=1,text='其他公司2025年年度报告全文 单位：千元',words=(),blocks=(),table_candidates=(),parse_warnings=())
        document=DocumentPages(source_id='other',page_count=1,pages=(page,))
        source=Source(id='other',filename='other.pdf',sha256='0'*64,media_type='application/pdf',page_count=1,url=None,published_date=None,parse_status='queued',data_basis='user_uploaded')
        result=AnnualReportExtractor().extract(self.dataset,source,document)
        self.assertEqual(result.facts,())
        self.assertEqual(result.parse_status,'needs_review')


class ExtractionPersistence(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        self.repo=SQLiteRepository(root/'db.sqlite',ROOT,root/'sources')
        self.dataset=self.repo.create(DatasetCreate(name='conflict test',company='CATL',year=2025))

    def tearDown(self):self.tmp.cleanup()

    def source(self,id,digit):
        source=Source(id=id,filename=f'{id}.pdf',sha256=digit*64,media_type='application/pdf',page_count=1,url=None,published_date=None,parse_status='queued',data_basis='user_uploaded')
        return self.repo.attach_source(self.dataset.id,source,f'upload:{id}.pdf').source

    def result(self,source,fact_id,raw):
        evidence=Evidence(id=f'e-{fact_id}',source_id=source.id,locator_kind='pdf',pdf_page=1,bbox=[1,1,2,2],excerpt='营业收入',sha256=source.sha256)
        fact=Fact(id=fact_id,company='CATL',metric='revenue',segment='group',statement_scope='consolidated',period_kind='annual_flow',period_start='2025-01-01',period_end='2025-12-31',value=str(int(raw)*1000),unit='CNY',raw_value=raw,raw_unit='CNY_thousand',status='extracted',evidence_ids=[evidence.id],restatement_status='not_restated')
        return ExtractionResult(facts=(fact,),evidence=(evidence,),parse_status='parsed',warnings=())

    def test_differing_candidate_is_added_as_conflict_without_overwrite(self):
        first=self.source('source-one','1');self.repo.apply_extraction(self.dataset.id,first.id,self.result(first,'fact-one','1'))
        second=self.source('source-two','2');attachment=self.repo.apply_extraction(self.dataset.id,second.id,self.result(second,'fact-two','2'))
        facts=self.repo.facts(self.dataset.id,attachment.dataset.version)
        self.assertEqual(len(facts),2)
        self.assertEqual({fact.status for fact in facts},{'extracted','conflict'})
        previous=self.repo.facts(self.dataset.id,3)
        self.assertEqual(len(previous),1);self.assertEqual(previous[0].value,'1000')


if __name__=='__main__':unittest.main()
