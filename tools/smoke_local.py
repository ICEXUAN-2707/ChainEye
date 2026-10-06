"""Start both processes together; check real local HTTP, not browser visual rendering."""
import subprocess,os,sys,time,json,signal,urllib.request,uuid
import httpx2 as httpx
from pathlib import Path
root=Path(__file__).resolve().parents[1];procs=[]
def get(url,origin=None):
 r=urllib.request.Request(url,headers={'Origin':origin} if origin else {})
 with urllib.request.urlopen(r,timeout=5) as response:return response.status,dict(response.headers),response.read()
try:
 npm='npm.cmd' if os.name=='nt' else 'npm'
 backend_env=os.environ.copy();backend_env.pop('DEEPSEEK_API_KEY',None)
 backend_env['PYTHON_DOTENV_DISABLED']='1'
 for args,cwd,env in [([sys.executable,'tools/start_backend.py'],root,backend_env),([npm,'run','dev'],root/'frontend',None)]:
  procs.append(subprocess.Popen(args,cwd=cwd,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True))
 for i in range(100):
  try:
   a=get('http://127.0.0.1:8000/health');b=get('http://127.0.0.1:5173/')
   if a[0]==200 and b[0]==200:break
  except Exception:pass
  if i==99:raise RuntimeError('local startup timeout')
  time.sleep(.1)
 _,headers,body=get('http://127.0.0.1:8000/api/v1/datasets/demo-catl-2025/facts?version=1','http://127.0.0.1:5173');f=json.loads(body);assert len(f['items'])==30
 assert headers.get('access-control-allow-origin',headers.get('Access-Control-Allow-Origin'))=='http://127.0.0.1:5173'
 _,_,body=get('http://127.0.0.1:8000/api/v1/evidence/e-2025-power_battery-revenue');assert json.loads(body)['pdf_page']==25
 _,headers,body=get('http://127.0.0.1:8000/api/v1/sources/catl-2025/content');assert body.startswith(b'%PDF')
 with httpx.Client(base_url='http://127.0.0.1:8000',headers={'Origin':'http://127.0.0.1:5173'},timeout=30) as client:
  created=client.post('/api/v1/datasets',json={'name':f'HTTP smoke {uuid.uuid4()}','company':'CATL','year':2025});created.raise_for_status()
  with (root/'data/raw/catl_2025.pdf').open('rb') as source:
   uploaded=client.post(f"/api/v1/datasets/{created.json()['id']}/sources",files={'file':('catl_2025.pdf',source,'application/pdf')},data={'url':'https://www.catl.com/','published_date':'2026-03-01'})
  uploaded.raise_for_status();attachment=uploaded.json();assert attachment['dataset']['version']==3;assert attachment['source']['id']=='catl-2025';assert attachment['source']['parse_status']=='parsed'
  extracted=client.get(f"/api/v1/datasets/{created.json()['id']}/facts?version=3");extracted.raise_for_status();candidates=extracted.json()['items'];assert len(candidates)==15;assert all(item['status']=='extracted' for item in candidates)
  candidate=next(item for item in candidates if item['segment']=='power_battery' and item['metric']=='revenue')
  corrected=client.patch(f"/api/v1/facts/{candidate['id']}",json={'expected_revision':1,'value':candidate['value'],'status':'verified','evidence_ids':candidate['evidence_ids'],'reason':'HTTP smoke review'});corrected.raise_for_status();assert corrected.json()['revision']==2
  latest=client.get(f"/api/v1/datasets/{created.json()['id']}");latest.raise_for_status();assert latest.json()['version']==4
  downloaded=client.get(f"/api/v1/sources/{attachment['source']['id']}/content");downloaded.raise_for_status();assert downloaded.content.startswith(b'%PDF')
  scenario=client.post('/api/v1/scenarios',headers={'Idempotency-Key':f'smoke-{uuid.uuid4()}'},json={'dataset_id':'demo-catl-2025','dataset_version':1,'revenue_fact_id':'f-2025-power_battery-revenue','cost_fact_id':'f-2025-power_battery-cost_of_sales','revenue_revision':1,'cost_revision':1,'model_version':'static-gross-profit-v1','assumptions':{'cost_exposure':'0.1','effective_price_shock':'-0.2','customer_pass_through':'0.5','basis':'user_assumption','acknowledged':True}})
  scenario.raise_for_status();scenario_body=scenario.json();assert len(scenario_body['calculation_ids'])==9
  calculation=client.get(f"/api/v1/calculations/{scenario_body['calculation_ids'][0]}");calculation.raise_for_status();assert calculation.json()['input_revisions']['f-2025-power_battery-revenue']==1
  run_key=f'run-smoke-{uuid.uuid4()}'
  run_response=client.post('/api/v1/runs',headers={'Idempotency-Key':run_key},json={'dataset_id':'demo-catl-2025','dataset_version':1,'question':'分析动力电池收入和毛利','segment':'power_battery','mode':'live'})
  run_response.raise_for_status();run_id=run_response.json()['id']
  repeated=client.post('/api/v1/runs',headers={'Idempotency-Key':run_key},json={'dataset_id':'demo-catl-2025','dataset_version':1,'question':'分析动力电池收入和毛利','segment':'power_battery','mode':'live'})
  repeated.raise_for_status();assert repeated.json()['id']==run_id
  for _ in range(100):
   run=client.get(f'/api/v1/runs/{run_id}');run.raise_for_status();run_body=run.json()
   if run_body['status'] not in ('queued','running'):break
   time.sleep(.05)
  assert run_body['status']=='partial';assert run_body['error']['code']=='MODEL_UNAVAILABLE';assert run_body['report_ready'] is False
  first_events=client.get(f'/api/v1/runs/{run_id}/events',params={'limit':3});first_events.raise_for_status();first_page=first_events.json();assert first_page['has_more']
  remaining=client.get(f'/api/v1/runs/{run_id}/events',params={'after_seq':first_page['next_after_seq'],'limit':200});remaining.raise_for_status();second_page=remaining.json();assert second_page['items'][0]['seq']==first_page['next_after_seq']+1
  report=client.get(f'/api/v1/runs/{run_id}/report');assert report.status_code==409;assert report.json()['error']['code']=='REPORT_NOT_READY'
 result={'status':'passed','real_http':True,'frontend_html':True,'cors':True,'fixture_facts':30,'evidence_page':25,'pdf':True,'upload':True,'upload_version':3,'extracted_candidates':15,'correction_revision':2,'reviewed_dataset_version':4,'duplicate_source_reused':True,'scenario':True,'scenario_calculations':9,'run':True,'run_status_without_key':'partial','run_error_without_key':'MODEL_UNAVAILABLE','run_event_cursor':True,'partial_report_error':'REPORT_NOT_READY','visual_browser_check':'separate check; see R1-browser-check.json'}
 (root/'validation/R5-http-smoke.json').write_text(json.dumps(result,indent=2),encoding='utf-8',newline='\n');print(json.dumps(result))
finally:
 for p in procs:
  if p.poll() is None:
   if os.name=='posix':os.killpg(p.pid,signal.SIGTERM)
   else:subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
 for p in procs:
  try:p.wait(timeout=5)
  except subprocess.TimeoutExpired:p.kill()
