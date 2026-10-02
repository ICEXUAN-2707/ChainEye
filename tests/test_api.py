import unittest,tempfile,json,hashlib
from pathlib import Path
import fitz
from fastapi.testclient import TestClient
from chain_eye.api.app import create_app
from chain_eye.api.dto import FactCollection,Dataset,ErrorResponse
ROOT=Path(__file__).resolve().parents[1]
def pdf_bytes(text='uploaded text',pages=1,encryption=False):
 doc=fitz.open()
 for index in range(pages):
  page=doc.new_page()
  if text:page.insert_text((72,72),f'{text} {index}')
 options={'encryption':fitz.PDF_ENCRYPT_AES_256,'owner_pw':'owner','user_pw':'user'} if encryption else {}
 data=doc.tobytes(**options);doc.close();return data
class API(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'db.sqlite';self.upload_dir=Path(self.tmp.name)/'sources';self.app=create_app(self.path,upload_dir=self.upload_dir);self.client=TestClient(self.app,base_url='http://localhost',client=('127.0.0.1',50000))
 def tearDown(self):self.client.close();self.tmp.cleanup()
 def check_error(self,response,status,code):
  self.assertEqual(response.status_code,status);e=ErrorResponse.model_validate(response.json());self.assertEqual(e.error.code,code);self.assertTrue(e.error.request_id)
 def test_health(self):self.assertEqual(self.client.get('/health').json()['stage'],'R2-upload')
 def test_facts(self):
  r=self.client.get('/api/v1/datasets/demo-catl-2025/facts?version=1');self.assertEqual(r.status_code,200);data=FactCollection.model_validate(r.json());self.assertEqual(len(data.items),30)
 def test_filter(self):self.assertEqual(len(self.client.get('/api/v1/datasets/demo-catl-2025/facts?version=1&segment=power_battery').json()['items']),6)
 def test_version_required(self):self.check_error(self.client.get('/api/v1/datasets/demo-catl-2025/facts'),422,'INVALID_INPUT')
 def test_unknown_version(self):self.check_error(self.client.get('/api/v1/datasets/demo-catl-2025/facts?version=2'),404,'NOT_FOUND')
 def test_unknown_dataset(self):self.check_error(self.client.get('/api/v1/datasets/missing'),404,'NOT_FOUND')
 def test_create_persists(self):
  r=self.client.post('/api/v1/datasets',json={'name':'new','company':'CATL','year':2025});self.assertEqual(r.status_code,201);d=Dataset.model_validate(r.json());app2=create_app(self.path,upload_dir=self.upload_dir);self.assertEqual(app2.state.repository.get_dataset(d.id).name,'new')
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
 def create_dataset(self,name='upload test'):
  response=self.client.post('/api/v1/datasets',json={'name':name,'company':'CATL','year':2025});self.assertEqual(response.status_code,201);return response.json()
 def upload(self,dataset_id,data=None,filename='upload.pdf',**form):
  return self.client.post(f'/api/v1/datasets/{dataset_id}/sources',files={'file':(filename,data or pdf_bytes(),'application/pdf')},data=form)
 def test_upload_versions_snapshot_and_content(self):
  body=pdf_bytes('versioned upload');expected_hash=hashlib.sha256(body).hexdigest()
  r=self.upload('demo-catl-2025',body,filename='../report.pdf',url='https://example.com/report.pdf',published_date='2026-09-30')
  self.assertEqual(r.status_code,201);attachment=r.json();self.assertEqual(attachment['dataset']['version'],2);self.assertEqual(attachment['source']['filename'],'report.pdf');self.assertEqual(attachment['source']['sha256'],expected_hash);self.assertEqual(attachment['source']['parse_status'],'queued')
  self.assertEqual(set(self.client.get('/api/v1/datasets/demo-catl-2025?version=1').json()['source_ids']),{'catl-2024','catl-2025'})
  self.assertEqual(len(self.client.get('/api/v1/datasets/demo-catl-2025/facts?version=2').json()['items']),30)
  content=self.client.get(f"/api/v1/sources/{attachment['source']['id']}/content");self.assertEqual(content.status_code,200);self.assertEqual(content.content,body)
 def test_duplicate_upload_reuses_source_without_new_version(self):
  dataset=self.create_dataset();body=pdf_bytes('same')
  first=self.upload(dataset['id'],body).json();second=self.upload(dataset['id'],body).json()
  self.assertEqual(first['source']['id'],second['source']['id']);self.assertEqual(first['dataset']['version'],2);self.assertEqual(second['dataset']['version'],2)
 def test_cross_dataset_duplicate_reuses_source(self):
  one=self.create_dataset('one');two=self.create_dataset('two');body=pdf_bytes('shared')
  first=self.upload(one['id'],body).json();second=self.upload(two['id'],body).json()
  self.assertEqual(first['source']['id'],second['source']['id']);self.assertEqual(second['dataset']['version'],2)
 def test_scanned_pdf_requires_review(self):
  dataset=self.create_dataset();r=self.upload(dataset['id'],pdf_bytes(text=None));self.assertEqual(r.status_code,201);self.assertEqual(r.json()['source']['parse_status'],'needs_review')
 def test_invalid_pdf_rejected(self):
  dataset=self.create_dataset();self.check_error(self.upload(dataset['id'],b'not a pdf'),422,'INVALID_INPUT');self.check_error(self.upload(dataset['id'],b'%PDF-broken'),422,'INVALID_INPUT')
 def test_encrypted_pdf_rejected(self):
  dataset=self.create_dataset();r=self.upload(dataset['id'],pdf_bytes(encryption=True));self.check_error(r,422,'INVALID_INPUT');self.assertEqual(r.json()['error']['details']['reason'],'PDF_ENCRYPTED')
 def test_page_limit(self):
  dataset=self.create_dataset();r=self.upload(dataset['id'],pdf_bytes(text=None,pages=501));self.check_error(r,422,'INVALID_INPUT');self.assertEqual(r.json()['error']['details']['reason'],'TOO_MANY_PAGES')
 def test_size_limit(self):
  dataset=self.create_dataset();r=self.upload(dataset['id'],b'%PDF-'+b'x'*(30*1024*1024));self.check_error(r,422,'INVALID_INPUT');self.assertEqual(r.json()['error']['details']['reason'],'FILE_TOO_LARGE')
 def test_dataset_source_limit(self):
  dataset=self.create_dataset()
  for index in range(5):self.assertEqual(self.upload(dataset['id'],pdf_bytes(f'file {index}')).status_code,201)
  r=self.upload(dataset['id'],pdf_bytes('sixth'));self.check_error(r,422,'INVALID_INPUT');self.assertEqual(r.json()['error']['details']['reason'],'SOURCE_LIMIT');self.assertEqual(len(list(self.upload_dir.glob('*.pdf'))),5)
 def test_upload_metadata_validation(self):
  dataset=self.create_dataset();self.check_error(self.upload(dataset['id'],published_date='2026-02-30'),422,'INVALID_INPUT');self.check_error(self.upload(dataset['id'],url='file:///secret.pdf'),422,'INVALID_INPUT')
 def test_correction_remains_explicitly_unimplemented(self):
  body={'expected_revision':1,'value':'1','raw_value':'0.001','status':'verified','evidence_ids':['e-2025-power_battery-revenue'],'reason':'test only'}
  self.check_error(self.client.patch('/api/v1/facts/f-2025-power_battery-revenue',json=body),501,'NOT_IMPLEMENTED')
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
