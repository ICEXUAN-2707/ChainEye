import unittest,tempfile,json
from pathlib import Path
from fastapi.testclient import TestClient
from chain_eye.api.app import create_app
from chain_eye.api.dto import FactCollection,Dataset,ErrorResponse
ROOT=Path(__file__).resolve().parents[1]
class API(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'db.sqlite';self.app=create_app(self.path);self.client=TestClient(self.app,base_url='http://localhost',client=('127.0.0.1',50000))
 def tearDown(self):self.client.close();self.tmp.cleanup()
 def check_error(self,response,status,code):
  self.assertEqual(response.status_code,status);e=ErrorResponse.model_validate(response.json());self.assertEqual(e.error.code,code);self.assertTrue(e.error.request_id)
 def test_health(self):self.assertEqual(self.client.get('/health').json()['stage'],'R1')
 def test_facts(self):
  r=self.client.get('/api/v1/datasets/demo-catl-2025/facts?version=1');self.assertEqual(r.status_code,200);data=FactCollection.model_validate(r.json());self.assertEqual(len(data.items),30)
 def test_filter(self):self.assertEqual(len(self.client.get('/api/v1/datasets/demo-catl-2025/facts?version=1&segment=power_battery').json()['items']),6)
 def test_version_required(self):self.check_error(self.client.get('/api/v1/datasets/demo-catl-2025/facts'),422,'INVALID_INPUT')
 def test_unknown_version(self):self.check_error(self.client.get('/api/v1/datasets/demo-catl-2025/facts?version=2'),404,'NOT_FOUND')
 def test_unknown_dataset(self):self.check_error(self.client.get('/api/v1/datasets/missing'),404,'NOT_FOUND')
 def test_create_persists(self):
  r=self.client.post('/api/v1/datasets',json={'name':'new','company':'CATL','year':2025});self.assertEqual(r.status_code,201);d=Dataset.model_validate(r.json());app2=create_app(self.path);self.assertEqual(app2.state.repository.get_dataset(d.id).name,'new')
 def test_extra_rejected(self):self.check_error(self.client.post('/api/v1/datasets',json={'name':'x','company':'CATL','year':2025,'bad':1}),422,'INVALID_INPUT')
 def test_evidence(self):
  r=self.client.get('/api/v1/evidence/e-2025-power_battery-revenue');self.assertEqual(r.status_code,200);self.assertEqual(r.json()['pdf_page'],25)
 def test_source(self):self.assertEqual(self.client.get('/api/v1/sources/catl-2025').json()['data_basis'],'reviewed_fixture')
 def test_pdf(self):
  r=self.client.get('/api/v1/sources/catl-2025/content');self.assertEqual(r.status_code,200);self.assertTrue(r.content.startswith(b'%PDF'));self.assertEqual(r.headers['content-type'],'application/pdf')
 def test_source_hash_changed(self):
  p=Path(self.tmp.name)/'changed.pdf';p.write_bytes(b'%PDF changed')
  self.app.state.repository.source_path=lambda id:p
  self.check_error(self.client.get('/api/v1/sources/catl-2025/content'),409,'SOURCE_HASH_MISMATCH')
 def test_mutation_stub(self):
  self.check_error(self.client.post('/api/v1/datasets/demo-catl-2025/sources',files={'file':('a.pdf',b'%PDF-1.0','application/pdf')}),501,'NOT_IMPLEMENTED');self.assertEqual(len(self.client.get('/api/v1/datasets/demo-catl-2025/facts?version=1').json()['items']),30)
 def test_scenario_stub(self):
  body=dict(dataset_id='demo-catl-2025',dataset_version=1,revenue_fact_id='f-2025-power_battery-revenue',cost_fact_id='f-2025-power_battery-cost_of_sales',revenue_revision=1,cost_revision=1,model_version='static-gross-profit-v1',assumptions=dict(cost_exposure='0.1',effective_price_shock='-0.2',customer_pass_through='0.5',basis='user_assumption',acknowledged=True))
  self.check_error(self.client.post('/api/v1/scenarios',json=body,headers={'Idempotency-Key':'scenario-1'}),501,'NOT_IMPLEMENTED')
 def test_idempotency_required(self):
  body={'dataset_id':'demo-catl-2025','dataset_version':1,'question':'q','segment':'power_battery','mode':'live'}
  self.check_error(self.client.post('/api/v1/runs',json=body),422,'INVALID_INPUT')
 def test_replay_validation(self):
  body={'dataset_id':'demo-catl-2025','dataset_version':1,'question':'q','segment':'power_battery','mode':'replay'}
  self.check_error(self.client.post('/api/v1/runs',json=body,headers={'Idempotency-Key':'run-test-1'}),422,'INVALID_INPUT')
 def test_notfound_uniform(self):self.check_error(self.client.get('/not-exist'),404,'NOT_FOUND')
 def test_origin_blocked(self):self.check_error(self.client.get('/health',headers={'Origin':'https://example.com'}),403,'LOCAL_ONLY')
 def test_remote_blocked(self):
  with TestClient(self.app,base_url='http://localhost',client=('192.0.2.1',50000)) as c:self.check_error(c.get('/health'),403,'LOCAL_ONLY')
 def test_contract_export_matches(self):self.assertEqual(self.app.openapi(),json.loads((ROOT/'contracts/openapi.json').read_text(encoding='utf-8')))
 def test_regenerated_migration(self):
  self.assertEqual(create_app(self.path).state.repository.get_dataset('demo-catl-2025').version,1)
