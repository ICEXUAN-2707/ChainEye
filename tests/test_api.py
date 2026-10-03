import unittest,tempfile,json,hashlib
from pathlib import Path
import fitz
from fastapi.testclient import TestClient
from chain_eye.api.app import create_app
from chain_eye.api.dto import FactCollection,Dataset,ErrorResponse
from chain_eye.domain.contracts import Calculation,Evidence,ScenarioResult
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
 def test_health(self):self.assertEqual(self.client.get('/health').json()['stage'],'R4')
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
  self.assertEqual(r.status_code,201);attachment=r.json();self.assertEqual(attachment['dataset']['version'],2);self.assertEqual(attachment['source']['filename'],'report.pdf');self.assertEqual(attachment['source']['sha256'],expected_hash);self.assertEqual(attachment['source']['parse_status'],'needs_review')
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
 def test_real_report_upload_extracts_15_candidates_and_evidence(self):
  dataset=self.create_dataset();body=(ROOT/'data/raw/catl_2025.pdf').read_bytes()
  response=self.upload(dataset['id'],body,filename='catl-2025.pdf')
  self.assertEqual(response.status_code,201);attachment=response.json()
  self.assertEqual(attachment['dataset']['version'],3);self.assertEqual(attachment['source']['parse_status'],'parsed')
  self.assertEqual(self.client.get(f"/api/v1/datasets/{dataset['id']}/facts?version=2").json()['items'],[])
  facts=self.client.get(f"/api/v1/datasets/{dataset['id']}/facts?version=3").json()['items']
  self.assertEqual(len(facts),15);self.assertTrue(all(fact['status']=='extracted' for fact in facts))
  evidence=self.client.get(f"/api/v1/evidence/{facts[0]['evidence_ids'][0]}")
  self.assertEqual(evidence.status_code,200);self.assertEqual(evidence.json()['source_id'],attachment['source']['id']);self.assertEqual(len(evidence.json()['bbox']),4)
  duplicate=self.upload(dataset['id'],body,filename='duplicate.pdf')
  self.assertEqual(duplicate.status_code,201);self.assertEqual(duplicate.json()['dataset']['version'],3)
 def test_correction_creates_fact_revision_dataset_version_and_log(self):
  body={'expected_revision':1,'value':'316506370000','status':'verified','evidence_ids':['e-2025-power_battery-revenue'],'reason':'checked against annual report'}
  response=self.client.patch('/api/v1/facts/f-2025-power_battery-revenue',json=body)
  self.assertEqual(response.status_code,200);self.assertEqual(response.json()['revision'],2);self.assertEqual(response.json()['raw_value'],'316506370')
  self.assertEqual(self.client.get('/api/v1/datasets/demo-catl-2025').json()['version'],2)
  old=self.client.get('/api/v1/datasets/demo-catl-2025/facts?version=1').json()['items'];new=self.client.get('/api/v1/datasets/demo-catl-2025/facts?version=2').json()['items']
  self.assertEqual(next(f for f in old if f['id']=='f-2025-power_battery-revenue')['revision'],1)
  self.assertEqual(next(f for f in new if f['id']=='f-2025-power_battery-revenue')['revision'],2)
  with self.app.state.repository.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM fact_corrections WHERE fact_id=?',('f-2025-power_battery-revenue',)).fetchone()[0],1)
 def test_correction_revision_conflict_is_atomic(self):
  body={'expected_revision':1,'value':'316506370000','status':'verified','evidence_ids':['e-2025-power_battery-revenue'],'reason':'first review'}
  self.assertEqual(self.client.patch('/api/v1/facts/f-2025-power_battery-revenue',json=body).status_code,200)
  self.check_error(self.client.patch('/api/v1/facts/f-2025-power_battery-revenue',json=body),409,'REVISION_CONFLICT')
  self.assertEqual(self.client.get('/api/v1/datasets/demo-catl-2025').json()['version'],2)
 def test_correction_derives_percent_raw_value(self):
  body={'expected_revision':1,'value':'0.2385','status':'verified','evidence_ids':['e-2025-power_battery-reported_gross_margin'],'reason':'margin review'}
  response=self.client.patch('/api/v1/facts/f-2025-power_battery-reported_gross_margin',json=body)
  self.assertEqual(response.status_code,200);self.assertEqual(response.json()['raw_value'],'23.85')
 def test_correction_rejects_raw_normalized_mismatch(self):
  body={'expected_revision':1,'value':'316506370000','raw_value':'1','status':'verified','evidence_ids':['e-2025-power_battery-revenue'],'reason':'mismatched units'}
  self.check_error(self.client.patch('/api/v1/facts/f-2025-power_battery-revenue',json=body),422,'INVALID_INPUT')
  self.assertEqual(self.client.get('/api/v1/datasets/demo-catl-2025').json()['version'],1)
 def test_correction_rejects_unknown_evidence_without_writes(self):
  body={'expected_revision':1,'value':'316506370000','status':'verified','evidence_ids':['not-in-dataset'],'reason':'invalid evidence'}
  self.check_error(self.client.patch('/api/v1/facts/f-2025-power_battery-revenue',json=body),409,'SCOPE_MISMATCH')
  self.assertEqual(self.client.get('/api/v1/datasets/demo-catl-2025').json()['version'],1)
  with self.app.state.repository.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM facts WHERE id=?',('f-2025-power_battery-revenue',)).fetchone()[0],1)
 def test_correction_rejects_evidence_from_another_dataset(self):
  other=self.create_dataset('other evidence owner');attachment=self.upload(other['id'],pdf_bytes('separate source')).json();source=attachment['source']
  evidence=Evidence(id='cross-dataset-evidence',source_id=source['id'],locator_kind='pdf',pdf_page=1,excerpt='separate source',sha256=source['sha256'])
  with self.app.state.repository.connect() as db:db.execute('INSERT INTO evidence VALUES (?,?,?)',(evidence.id,evidence.source_id,evidence.model_dump_json()))
  body={'expected_revision':1,'value':'316506370000','status':'verified','evidence_ids':[evidence.id],'reason':'wrong dataset evidence'}
  self.check_error(self.client.patch('/api/v1/facts/f-2025-power_battery-revenue',json=body),409,'SCOPE_MISMATCH')
  self.assertEqual(self.client.get('/api/v1/datasets/demo-catl-2025').json()['version'],1)
 def test_missing_correction_requires_null_raw_value(self):
  body={'expected_revision':1,'value':None,'raw_value':'1','status':'missing','evidence_ids':[],'reason':'not disclosed','missing_reason':'not disclosed'}
  self.check_error(self.client.patch('/api/v1/facts/f-2025-power_battery-revenue',json=body),422,'INVALID_INPUT')
 def test_missing_correction_keeps_null_semantics(self):
  body={'expected_revision':1,'value':None,'status':'missing','evidence_ids':[],'reason':'not disclosed after review','missing_reason':'not disclosed'}
  response=self.client.patch('/api/v1/facts/f-2025-power_battery-revenue',json=body)
  self.assertEqual(response.status_code,200);self.assertIsNone(response.json()['value']);self.assertIsNone(response.json()['raw_value']);self.assertEqual(response.json()['revision'],2)
 def scenario_body(self,segment='power_battery'):
  return dict(dataset_id='demo-catl-2025',dataset_version=1,revenue_fact_id=f'f-2025-{segment}-revenue',cost_fact_id=f'f-2025-{segment}-cost_of_sales',revenue_revision=1,cost_revision=1,model_version='static-gross-profit-v1',assumptions=dict(cost_exposure='0.1',effective_price_shock='-0.2',customer_pass_through='0.5',basis='user_assumption',acknowledged=True))
 def test_scenario_persists_traceable_calculations_for_both_segments(self):
  for index,segment in enumerate(('power_battery','energy_storage')):
   response=self.client.post('/api/v1/scenarios',json=self.scenario_body(segment),headers={'Idempotency-Key':f'scenario-{index}'})
   self.assertEqual(response.status_code,201);result=ScenarioResult.model_validate(response.json())
   self.assertEqual(len(result.calculation_ids),9);self.assertEqual(result.mode,'conditional_scenario')
   calculations={}
   for calculation_id in result.calculation_ids:
    calculation=Calculation.model_validate(self.client.get(f'/api/v1/calculations/{calculation_id}').json())
    self.assertTrue(calculation.input_fact_ids);self.assertEqual(set(calculation.input_fact_ids),set(calculation.input_revisions))
    calculations[calculation.formula_id]=calculation
   self.assertEqual(set(calculations),{'baseline-gross-profit','baseline-gross-margin','scenario-delta-cost','scenario-revenue','scenario-cost-of-sales','scenario-gross-profit','scenario-gross-margin','scenario-delta-gross-profit','scenario-delta-gross-margin-pp'})
   expected={
    'baseline-gross-profit':(result.baseline.gross_profit,'CNY'),'baseline-gross-margin':(result.baseline.gross_margin,'ratio'),
    'scenario-delta-cost':(result.outputs.delta_cost,'CNY'),'scenario-revenue':(result.outputs.revenue,'CNY'),
    'scenario-cost-of-sales':(result.outputs.cost_of_sales,'CNY'),'scenario-gross-profit':(result.outputs.gross_profit,'CNY'),
    'scenario-gross-margin':(result.outputs.gross_margin,'ratio'),'scenario-delta-gross-profit':(result.outputs.delta_gross_profit,'CNY'),
    'scenario-delta-gross-margin-pp':(result.outputs.delta_gross_margin_pp,'pp'),
   }
   for formula_id,(value,unit) in expected.items():
    self.assertEqual((calculations[formula_id].value,calculations[formula_id].unit),(value,unit))
    self.assertEqual(calculations[formula_id].formula_version,'1')
   self.assertEqual(calculations['baseline-gross-profit'].assumption_snapshot,{})
   self.assertEqual(calculations['scenario-gross-profit'].assumption_snapshot,{'cost_exposure':'0.1','effective_price_shock':'-0.2','customer_pass_through':'0.5','basis':'user_assumption','acknowledged':'true','evidence_ids':'[]'})
 def test_scenario_idempotency_reuses_and_conflicts(self):
  body=self.scenario_body();headers={'Idempotency-Key':'scenario-same'}
  first=self.client.post('/api/v1/scenarios',json=body,headers=headers);second=self.client.post('/api/v1/scenarios',json=body,headers=headers)
  self.assertEqual(first.status_code,201);self.assertEqual(second.status_code,201);self.assertEqual(first.json(),second.json())
  body['assumptions']['cost_exposure']='0.2';body['revenue_fact_id']='missing';conflict=self.client.post('/api/v1/scenarios',json=body,headers=headers)
  self.check_error(conflict,409,'INVALID_INPUT');self.assertEqual(conflict.json()['error']['details']['reason'],'IDEMPOTENCY_KEY_REUSED')
  with self.app.state.repository.connect() as db:
   self.assertEqual(db.execute('SELECT COUNT(*) FROM scenarios').fetchone()[0],1);self.assertEqual(db.execute('SELECT COUNT(*) FROM calculations').fetchone()[0],9)
 def test_scenario_rejects_unknown_and_wrong_snapshot_fact(self):
  body=self.scenario_body();body['revenue_fact_id']='missing'
  self.check_error(self.client.post('/api/v1/scenarios',json=body,headers={'Idempotency-Key':'scenario-missing'}),404,'NOT_FOUND')
  body=self.scenario_body();body['revenue_revision']=2
  self.check_error(self.client.post('/api/v1/scenarios',json=body,headers={'Idempotency-Key':'scenario-revision'}),409,'SCOPE_MISMATCH')
 def test_scenario_rejects_mixed_scope(self):
  body=self.scenario_body();body['cost_fact_id']='f-2025-energy_storage-cost_of_sales'
  self.check_error(self.client.post('/api/v1/scenarios',json=body,headers={'Idempotency-Key':'scenario-scope'}),409,'SCOPE_MISMATCH')
  with self.app.state.repository.connect() as db:
   self.assertEqual(db.execute('SELECT COUNT(*) FROM scenarios').fetchone()[0],0);self.assertEqual(db.execute('SELECT COUNT(*) FROM calculations').fetchone()[0],0)
 def test_scenario_assumption_evidence_must_belong_to_snapshot(self):
  body=self.scenario_body();body['assumptions']['basis']='research_assumption';body['assumptions']['evidence_ids']=['e-2025-power_battery-revenue']
  response=self.client.post('/api/v1/scenarios',json=body,headers={'Idempotency-Key':'scenario-evidence-valid'});self.assertEqual(response.status_code,201)
  calculation=self.client.get(f"/api/v1/calculations/{response.json()['calculation_ids'][2]}").json()
  self.assertEqual(calculation['assumption_snapshot']['evidence_ids'],'["e-2025-power_battery-revenue"]')
  body=self.scenario_body();body['assumptions']['evidence_ids']=['unknown-evidence']
  self.check_error(self.client.post('/api/v1/scenarios',json=body,headers={'Idempotency-Key':'scenario-evidence-missing'}),404,'NOT_FOUND')
  other=self.create_dataset('other evidence owner');attachment=self.upload(other['id'],pdf_bytes('scenario evidence')).json();source=attachment['source']
  evidence=Evidence(id='scenario-cross-dataset-evidence',source_id=source['id'],locator_kind='pdf',pdf_page=1,excerpt='scenario evidence',sha256=source['sha256'])
  with self.app.state.repository.connect() as db:db.execute('INSERT INTO evidence VALUES (?,?,?)',(evidence.id,evidence.source_id,evidence.model_dump_json()))
  body=self.scenario_body();body['assumptions']['evidence_ids']=[evidence.id]
  self.check_error(self.client.post('/api/v1/scenarios',json=body,headers={'Idempotency-Key':'scenario-evidence-scope'}),409,'SCOPE_MISMATCH')
  with self.app.state.repository.connect() as db:
   self.assertEqual(db.execute('SELECT COUNT(*) FROM scenarios').fetchone()[0],1);self.assertEqual(db.execute('SELECT COUNT(*) FROM calculations').fetchone()[0],9)
 def test_scenario_rejects_cross_period_and_group_baselines_without_writes(self):
  body=self.scenario_body();body['cost_fact_id']='f-2024-power_battery-cost_of_sales'
  self.check_error(self.client.post('/api/v1/scenarios',json=body,headers={'Idempotency-Key':'scenario-period'}),409,'SCOPE_MISMATCH')
  body=self.scenario_body();body.update(revenue_fact_id='f-2025-group-revenue',cost_fact_id='f-2025-group-cost_of_sales')
  self.check_error(self.client.post('/api/v1/scenarios',json=body,headers={'Idempotency-Key':'scenario-group'}),409,'INVALID_BASELINE')
  with self.app.state.repository.connect() as db:
   self.assertEqual(db.execute('SELECT COUNT(*) FROM scenarios').fetchone()[0],0);self.assertEqual(db.execute('SELECT COUNT(*) FROM calculations').fetchone()[0],0)
 def test_scenario_snapshot_is_immutable_after_fact_correction(self):
  body=self.scenario_body();first=self.client.post('/api/v1/scenarios',json=body,headers={'Idempotency-Key':'scenario-before'});self.assertEqual(first.status_code,201)
  old=first.json();old_calculation=self.client.get(f"/api/v1/calculations/{old['calculation_ids'][0]}").json()
  correction={'expected_revision':1,'value':'316506370000','status':'verified','evidence_ids':['e-2025-power_battery-revenue'],'reason':'scenario snapshot test'}
  self.assertEqual(self.client.patch('/api/v1/facts/f-2025-power_battery-revenue',json=correction).status_code,200)
  self.assertEqual(self.client.get(f"/api/v1/calculations/{old['calculation_ids'][0]}").json(),old_calculation)
  body.update(dataset_version=2,revenue_revision=2)
  second=self.client.post('/api/v1/scenarios',json=body,headers={'Idempotency-Key':'scenario-after'});self.assertEqual(second.status_code,201)
  self.assertNotEqual(second.json()['scenario_id'],old['scenario_id']);self.assertEqual(second.json()['input_revisions']['f-2025-power_battery-revenue'],2)
 def test_scenario_requires_verified_baseline(self):
  correction={'expected_revision':1,'value':'316506369000','status':'needs_review','evidence_ids':['e-2025-power_battery-revenue'],'reason':'requires another review'}
  self.assertEqual(self.client.patch('/api/v1/facts/f-2025-power_battery-revenue',json=correction).status_code,200)
  body=self.scenario_body();body.update(dataset_version=2,revenue_revision=2)
  self.check_error(self.client.post('/api/v1/scenarios',json=body,headers={'Idempotency-Key':'scenario-unverified'}),409,'FACT_NOT_VERIFIED')
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
