"""Start both processes together; check real local HTTP, not browser visual rendering."""
import subprocess,os,sys,time,json,signal,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1];procs=[]
def get(url,origin=None):
 r=urllib.request.Request(url,headers={'Origin':origin} if origin else {})
 with urllib.request.urlopen(r,timeout=5) as response:return response.status,dict(response.headers),response.read()
try:
 npm='npm.cmd' if os.name=='nt' else 'npm'
 for args,cwd in [([sys.executable,'tools/start_backend.py'],root),([npm,'run','dev'],root/'frontend')]:
  procs.append(subprocess.Popen(args,cwd=cwd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True))
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
 result={'status':'passed','real_http':True,'frontend_html':True,'cors':True,'facts':30,'evidence_page':25,'pdf':True,'visual_browser_check':'separate check; see R1-browser-check.json'}
 (root/'validation/R1-http-smoke.json').write_text(json.dumps(result,indent=2),encoding='utf-8',newline='\n');print(json.dumps(result))
finally:
 for p in procs:
  if p.poll() is None:
   if os.name=='posix':os.killpg(p.pid,signal.SIGTERM)
   else:p.terminate()
 for p in procs:
  try:p.wait(timeout=5)
  except subprocess.TimeoutExpired:p.kill()
