"""Start isolated local processes and exercise the real HTTP boundary."""
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

import httpx2 as httpx


ROOT=Path(__file__).resolve().parents[1]
BACKEND_PORT=8000
FRONTEND_PORT=5173
UPLOAD_TIMEOUT_SECONDS=120
STARTUP_TIMEOUT_SECONDS=30
RUN_TIMEOUT_SECONDS=30


def get(url,origin=None):
    request=urllib.request.Request(url,headers={'Origin':origin} if origin else {})
    with urllib.request.urlopen(request,timeout=5) as response:
        return response.status,dict(response.headers),response.read()


def require_free_port(port):
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
        try:probe.bind(('127.0.0.1',port))
        except OSError as exc:raise RuntimeError(f'smoke requires unused port {port}') from exc


def process_failure(name,process,log_path):
    if process.poll() is None:return None
    try:log=log_path.read_text(encoding='utf-8',errors='replace')[-4000:]
    except OSError:log='log unavailable'
    return RuntimeError(f'{name} exited before smoke completed (code={process.returncode}):\n{log}')


def stop_process(process):
    if process.poll() is None:
        if os.name=='posix':os.killpg(process.pid,signal.SIGTERM)
        else:subprocess.run(
            ['taskkill','/PID',str(process.pid),'/T','/F'],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False,
        )
    try:process.wait(timeout=5)
    except subprocess.TimeoutExpired:process.kill()


def main():
    require_free_port(BACKEND_PORT);require_free_port(FRONTEND_PORT)
    processes=[];log_handles=[]
    with tempfile.TemporaryDirectory(prefix='chain-eye-http-smoke-') as temporary:
        isolated=Path(temporary);nonce=str(uuid.uuid4())
        backend_env=os.environ.copy();backend_env.pop('DEEPSEEK_API_KEY',None)
        backend_env.update({
            'PYTHON_DOTENV_DISABLED':'1','CHAIN_EYE_DISABLE_MODEL':'1',
            'CHAIN_EYE_DB':str(isolated/'chain_eye.sqlite'),
            'CHAIN_EYE_UPLOAD_DIR':str(isolated/'sources'),
            'CHAIN_EYE_INSTANCE_NONCE':nonce,
        })
        npm='npm.cmd' if os.name=='nt' else 'npm'
        specs=[
            ('backend',[sys.executable,'tools/start_backend.py'],ROOT,backend_env),
            ('frontend',[npm,'run','dev'],ROOT/'frontend',os.environ.copy()),
        ]
        try:
            for name,args,cwd,environment in specs:
                log_path=isolated/f'{name}.log';handle=log_path.open('w',encoding='utf-8')
                log_handles.append(handle)
                process=subprocess.Popen(
                    args,cwd=cwd,env=environment,stdout=handle,stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                processes.append((name,process,log_path))
            deadline=time.monotonic()+STARTUP_TIMEOUT_SECONDS
            while time.monotonic()<deadline:
                for name,process,log_path in processes:
                    failure=process_failure(name,process,log_path)
                    if failure:raise failure
                try:
                    backend=get(f'http://127.0.0.1:{BACKEND_PORT}/health')
                    frontend=get(f'http://127.0.0.1:{FRONTEND_PORT}/')
                    health=json.loads(backend[2])
                    if (
                        backend[0]==200 and frontend[0]==200
                        and health.get('instance_nonce')==nonce
                        and all(process.poll() is None for _,process,_ in processes)
                    ):break
                except Exception:pass
                time.sleep(.1)
            else:raise RuntimeError('isolated local startup timeout')

            origin=f'http://127.0.0.1:{FRONTEND_PORT}';api=f'http://127.0.0.1:{BACKEND_PORT}'
            _,headers,body=get(f'{api}/api/v1/datasets/demo-catl-2025/facts?version=1',origin)
            facts=json.loads(body);assert len(facts['items'])==30
            assert headers.get('access-control-allow-origin',headers.get('Access-Control-Allow-Origin'))==origin
            _,_,body=get(f'{api}/api/v1/evidence/e-2025-power_battery-revenue')
            assert json.loads(body)['pdf_page']==25
            _,_,body=get(f'{api}/api/v1/sources/catl-2025/content');assert body.startswith(b'%PDF')
            with httpx.Client(base_url=api,headers={'Origin':origin},timeout=30) as client:
                created=client.post('/api/v1/datasets',json={
                    'name':f'HTTP smoke {uuid.uuid4()}','company':'CATL','year':2025,
                });created.raise_for_status()
                with (ROOT/'data/raw/catl_2025.pdf').open('rb') as source:
                    uploaded=client.post(
                        f"/api/v1/datasets/{created.json()['id']}/sources",
                        files={'file':('catl_2025.pdf',source,'application/pdf')},
                        data={'url':'https://www.catl.com/','published_date':'2026-03-01'},
                        timeout=UPLOAD_TIMEOUT_SECONDS,
                    )
                uploaded.raise_for_status();attachment=uploaded.json()
                assert attachment['dataset']['version']==3
                assert attachment['source']['id']=='catl-2025'
                assert attachment['source']['parse_status']=='parsed'
                extracted=client.get(f"/api/v1/datasets/{created.json()['id']}/facts?version=3")
                extracted.raise_for_status();candidates=extracted.json()['items']
                assert len(candidates)==15 and all(item['status']=='extracted' for item in candidates)
                candidate=next(
                    item for item in candidates
                    if item['segment']=='power_battery' and item['metric']=='revenue'
                )
                corrected=client.patch(f"/api/v1/facts/{candidate['id']}",json={
                    'expected_revision':1,'value':candidate['value'],'status':'verified',
                    'evidence_ids':candidate['evidence_ids'],'reason':'HTTP smoke review',
                })
                corrected.raise_for_status();assert corrected.json()['revision']==2
                latest=client.get(f"/api/v1/datasets/{created.json()['id']}")
                latest.raise_for_status();assert latest.json()['version']==4
                downloaded=client.get(f"/api/v1/sources/{attachment['source']['id']}/content")
                downloaded.raise_for_status();assert downloaded.content.startswith(b'%PDF')
                scenario=client.post('/api/v1/scenarios',headers={'Idempotency-Key':f'smoke-{uuid.uuid4()}'},json={
                    'dataset_id':'demo-catl-2025','dataset_version':1,
                    'revenue_fact_id':'f-2025-power_battery-revenue',
                    'cost_fact_id':'f-2025-power_battery-cost_of_sales',
                    'revenue_revision':1,'cost_revision':1,'model_version':'static-gross-profit-v1',
                    'assumptions':{
                        'cost_exposure':'0.1','effective_price_shock':'-0.2',
                        'customer_pass_through':'0.5','basis':'user_assumption','acknowledged':True,
                    },
                })
                scenario.raise_for_status();scenario_body=scenario.json()
                assert len(scenario_body['calculation_ids'])==9
                calculation=client.get(f"/api/v1/calculations/{scenario_body['calculation_ids'][0]}")
                calculation.raise_for_status()
                assert calculation.json()['input_revisions']['f-2025-power_battery-revenue']==1
                run_key=f'run-smoke-{uuid.uuid4()}'
                run_request={
                    'dataset_id':'demo-catl-2025','dataset_version':1,
                    'question':'分析动力电池收入和毛利','segment':'power_battery','mode':'live',
                }
                run_response=client.post('/api/v1/runs',headers={'Idempotency-Key':run_key},json=run_request)
                run_response.raise_for_status();run_id=run_response.json()['id']
                repeated=client.post('/api/v1/runs',headers={'Idempotency-Key':run_key},json=run_request)
                repeated.raise_for_status();assert repeated.json()['id']==run_id
                run_deadline=time.monotonic()+RUN_TIMEOUT_SECONDS
                while time.monotonic()<run_deadline:
                    run=client.get(f'/api/v1/runs/{run_id}');run.raise_for_status();run_body=run.json()
                    if run_body['status'] not in ('queued','running'):break
                    time.sleep(.05)
                else:raise RuntimeError('smoke Run did not reach a terminal state')
                assert run_body['status']=='partial'
                assert run_body['error']['code']=='MODEL_UNAVAILABLE'
                assert run_body['report_ready'] is False
                first_events=client.get(f'/api/v1/runs/{run_id}/events',params={'limit':3})
                first_events.raise_for_status();first_page=first_events.json();assert first_page['has_more']
                remaining=client.get(
                    f'/api/v1/runs/{run_id}/events',
                    params={'after_seq':first_page['next_after_seq'],'limit':200},
                )
                remaining.raise_for_status();second_page=remaining.json()
                assert second_page['items'][0]['seq']==first_page['next_after_seq']+1
                report=client.get(f'/api/v1/runs/{run_id}/report')
                assert report.status_code==409 and report.json()['error']['code']=='REPORT_NOT_READY'
            result={
                'status':'passed','isolated_runtime':True,'startup_nonce_verified':True,
                'paid_model_calls':False,'real_http':True,'frontend_html':True,'cors':True,
                'fixture_facts':30,'evidence_page':25,'pdf':True,'upload':True,
                'upload_version':3,'extracted_candidates':15,'correction_revision':2,
                'reviewed_dataset_version':4,'duplicate_source_reused':True,'scenario':True,
                'scenario_calculations':9,'run':True,'run_status_without_key':'partial',
                'run_error_without_key':'MODEL_UNAVAILABLE','run_event_cursor':True,
                'partial_report_error':'REPORT_NOT_READY',
                'visual_browser_check':'separate check; see R1-browser-check.json',
            }
            (ROOT/'validation/R5-http-smoke.json').write_text(
                json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8',newline='\n',
            )
            print(json.dumps(result,ensure_ascii=False))
        finally:
            for _,process,_ in reversed(processes):stop_process(process)
            for handle in log_handles:handle.close()


if __name__=='__main__':main()
