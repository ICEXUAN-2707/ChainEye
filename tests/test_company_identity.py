import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from chain_eye.adapters.sqlite import SQLiteRepository
from chain_eye.api.app import create_app
from chain_eye.api.dto import FactCorrection
from chain_eye.application.extraction import AnnualReportExtractor
from chain_eye.application.fact_review import FactReviewService
from chain_eye.domain.companies import COMPANY_BY_ID,IdentityCandidate
from chain_eye.domain.contracts import Fact
from chain_eye.domain.datasets import DatasetCreate,Source
from chain_eye.domain.extraction import DocumentPage,DocumentPages,ExtractionResult
from chain_eye.domain.review import FactScopeError


ROOT=Path(__file__).resolve().parents[1]


class CompanyIdentityAPI(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        self.app=create_app(root/'db.sqlite',seed=False,upload_dir=root/'sources')
        self.client=TestClient(self.app,base_url='http://localhost',client=('127.0.0.1',50000))
        created=self.client.post('/api/v1/datasets',json={'name':'identity flow','company':'EVE','year':2025})
        self.assertEqual(created.status_code,201);self.dataset=created.json()
        self.source=Source(
            id='identity-source',filename='report.pdf',sha256='a'*64,media_type='application/pdf',page_count=1,
            url='https://static.cninfo.com.cn/example.pdf',published_date='2026-03-28',
            parse_status='queued',data_basis='user_uploaded',
        )
        attachment=self.app.state.repository.attach_source(self.dataset['id'],self.source,'upload:identity-source.pdf')
        candidate=IdentityCandidate(
            source_id=self.source.id,company_id='catl',company_code='CATL',
            legal_name=COMPANY_BY_ID['catl'].legal_name,report_year=2025,report_type='annual_report',
            status='conflict',evidence_pages=[1],warnings=['dataset_document_identity_conflict'],
        )
        self.app.state.repository.apply_extraction(
            self.dataset['id'],self.source.id,
            ExtractionResult(facts=(),evidence=(),parse_status='needs_review',warnings=('identity_conflict',),identity_candidate=candidate),
        )
        self.version=attachment.dataset.version

    def tearDown(self):
        self.client.close();self.tmp.cleanup()

    def test_company_profiles_are_distinct_and_versioned(self):
        response=self.client.get('/api/v1/companies');self.assertEqual(response.status_code,200)
        items={item['id']:item for item in response.json()['items']}
        self.assertEqual(set(items),{'catl','eve-energy'})
        self.assertEqual(items['catl']['security_ids'][0]['value'],'300750')
        self.assertEqual(items['eve-energy']['security_ids'][0]['value'],'300014')
        self.assertEqual(items['eve-energy']['profile_version'],1)
        self.assertEqual(items['eve-energy']['industry_profile_version'],1)
        current=self.client.get(f"/api/v1/datasets/{self.dataset['id']}").json()
        self.assertEqual((current['company_profile_version'],current['industry_profile_version']),(1,1))

    def test_conflict_blocks_capabilities_and_run(self):
        candidates=self.client.get(f"/api/v1/datasets/{self.dataset['id']}/identity-candidates?version={self.version}")
        self.assertEqual(candidates.status_code,200);self.assertEqual(candidates.json()['items'][0]['status'],'conflict')
        capabilities=self.client.get(f"/api/v1/datasets/{self.dataset['id']}/capabilities?version={self.version}&industry_profile_version=1")
        self.assertEqual(capabilities.status_code,200)
        self.assertTrue(all(item['status']=='failed' and item['reason_code']=='IDENTITY_CONFLICT' for item in capabilities.json()['items']))
        body={'dataset_id':self.dataset['id'],'dataset_version':self.version,'question':'q','segment':'power_battery','mode':'live'}
        blocked=self.client.post('/api/v1/runs',json=body,headers={'Idempotency-Key':'identity-conflict-run'})
        self.assertEqual(blocked.status_code,409);self.assertEqual(blocked.json()['error']['code'],'IDENTITY_CONFLICT')

    def test_confirmation_creates_snapshot_and_resolves_matching_candidate(self):
        body={'expected_version':self.version,'company_id':'catl','report_year':2025,'report_type':'annual_report','reason':'reviewed issuer title and stock code'}
        response=self.client.post(f"/api/v1/datasets/{self.dataset['id']}/identity-confirmations",json=body)
        self.assertEqual(response.status_code,201);confirmed=response.json()
        self.assertEqual((confirmed['version'],confirmed['company'],confirmed['company_id']),(self.version+1,'CATL','catl'))
        old=self.client.get(f"/api/v1/datasets/{self.dataset['id']}?version={self.version}").json()
        self.assertEqual((old['company'],old['company_id']),('EVE','eve-energy'))
        candidates=self.client.get(f"/api/v1/datasets/{self.dataset['id']}/identity-candidates?version={confirmed['version']}").json()['items']
        self.assertEqual(candidates[0]['status'],'identified');self.assertIn('identity_confirmed_by_user',candidates[0]['warnings'])
        capabilities=self.client.get(f"/api/v1/datasets/{self.dataset['id']}/capabilities?version={confirmed['version']}&industry_profile_version=1").json()['items']
        self.assertTrue(all(item['status']!='failed' for item in capabilities))
        mismatch=self.client.get(f"/api/v1/datasets/{self.dataset['id']}/capabilities?version={confirmed['version']}&industry_profile_version=2")
        self.assertEqual(mismatch.status_code,409);self.assertEqual(mismatch.json()['error']['code'],'STALE_SNAPSHOT')
        stale=self.client.post(f"/api/v1/datasets/{self.dataset['id']}/identity-confirmations",json=body)
        self.assertEqual(stale.status_code,409);self.assertEqual(stale.json()['error']['code'],'IDENTITY_CONFLICT')


class CompanyIsolationPersistence(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        self.repo=SQLiteRepository(root/'db.sqlite',ROOT,root/'sources')
        self.catl=self.repo.create(DatasetCreate(name='CATL',company='CATL',year=2025))
        self.source=Source(
            id='source',filename='source.pdf',sha256='b'*64,media_type='application/pdf',page_count=1,
            url=None,published_date=None,parse_status='queued',data_basis='user_uploaded',
        )
        self.snapshot=self.repo.attach_source(self.catl.id,self.source,'upload:source.pdf').dataset

    def tearDown(self):self.tmp.cleanup()

    def test_repository_rejects_cross_company_fact(self):
        fact=Fact(
            id='cross-company',company='EVE',metric='revenue',segment='group',statement_scope='consolidated',
            period_kind='annual_flow',period_start='2025-01-01',period_end='2025-12-31',value='100',unit='CNY',
            raw_value='100',raw_unit='CNY_yuan',status='extracted',evidence_ids=[],restatement_status='not_restated',
        )
        result=ExtractionResult(facts=(fact,),evidence=(),parse_status='parsed',warnings=())
        with self.assertRaises(FactScopeError):self.repo.apply_extraction(self.catl.id,self.source.id,result)
        self.assertEqual(self.repo.facts(self.catl.id,self.snapshot.version),[])

    def test_extractor_refuses_unavailable_profile_version(self):
        page=DocumentPage(
            page_no=1,text='宁德时代新能源科技股份有限公司2025年年度报告全文',
            words=(),blocks=(),table_candidates=(),parse_warnings=(),
        )
        result=AnnualReportExtractor().extract(
            self.snapshot.model_copy(update={'company_profile_version':2}),self.source,
            DocumentPages(source_id=self.source.id,page_count=1,pages=(page,)),
        )
        self.assertEqual(result.facts,());self.assertEqual(result.warnings,('profile_version_mismatch',))


class YuanFactReview(unittest.TestCase):
    def test_omitted_raw_value_is_derived_one_to_one_for_yuan(self):
        fact=Fact(
            id='eve-revenue',company='EVE',metric='revenue',segment='group',statement_scope='consolidated',
            period_kind='annual_flow',period_start='2025-01-01',period_end='2025-12-31',value='100',unit='CNY',
            raw_value='100',raw_unit='CNY_yuan',status='extracted',evidence_ids=['eve-evidence'],restatement_status='not_restated',
        )

        class Repository:
            def get_current_fact_context(self,fact_id):
                self.asserted_fact_id=fact_id
                return SimpleNamespace(id='eve-dataset'),fact

            def correct_fact(self,dataset_id,expected_revision,updated,reason):
                self.saved=(dataset_id,expected_revision,updated,reason)
                return updated

        repository=Repository()
        updated=FactReviewService(repository).correct(
            fact.id,
            FactCorrection(
                expected_revision=1,value='101.25',status='verified',evidence_ids=['eve-evidence'],reason='reviewed source value',
            ),
        )
        self.assertEqual(updated.raw_value,'101.25')
        self.assertEqual(repository.saved[:2],('eve-dataset',1))


if __name__=='__main__':unittest.main()
