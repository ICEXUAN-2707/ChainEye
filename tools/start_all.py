"""Start and supervise the native API and frontend with safe local defaults."""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

TOOLS_DIR=Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:sys.path.insert(0,str(TOOLS_DIR))
from preflight import BACKEND_PORT,FRONTEND_PORT,ROOT,_port_is_free


def _get_json(url):
    with urllib.request.urlopen(url,timeout=3) as response:
        return response.status,json.loads(response.read())


def _get_status(url):
    with urllib.request.urlopen(url,timeout=3) as response:return response.status


def stop_process(process):
    if process.poll() is None:
        if os.name=='posix':os.killpg(process.pid,signal.SIGTERM)
        else:subprocess.run(
            ['taskkill','/PID',str(process.pid),'/T','/F'],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False,
        )
    try:process.wait(timeout=5)
    except subprocess.TimeoutExpired:process.kill()


def wait_for_ports_free(timeout=10):
    deadline=time.monotonic()+timeout
    occupied=[port for port in (BACKEND_PORT,FRONTEND_PORT) if not _port_is_free(port)]
    while occupied and time.monotonic()<deadline:
        time.sleep(.05)
        occupied=[port for port in occupied if not _port_is_free(port)]
    if occupied:raise RuntimeError(f'ports remained in use after service shutdown: {occupied}')


def service_specs(runtime,nonce,live_model=False):
    backend_env=os.environ.copy();frontend_env=os.environ.copy()
    backend_env.update({
        'PYTHONUTF8':'1','CHAIN_EYE_INSTANCE_NONCE':nonce,
        'CHAIN_EYE_LOG_PATH':str(runtime/'chain-eye.jsonl'),
    })
    if not live_model:
        for environment in (backend_env,frontend_env):
            for name in tuple(environment):
                normalized=name.casefold().replace('-','_')
                if normalized in {'authorization','cookie'} or normalized.endswith(('_api_key','_token','_secret','_password')):
                    environment.pop(name,None)
        backend_env.update({'CHAIN_EYE_DISABLE_MODEL':'1','PYTHON_DOTENV_DISABLED':'1'})
    npm='npm.cmd' if os.name=='nt' else 'npm'
    return [
        ('backend',[sys.executable,'tools/start_backend.py'],ROOT,backend_env),
        ('frontend',[npm,'run','dev'],ROOT/'frontend',frontend_env),
    ]


def start_stack(runtime,timeout=30,live_model=False):
    if live_model and not os.getenv('DEEPSEEK_API_KEY'):
        raise RuntimeError('--live-model requires DEEPSEEK_API_KEY in the process environment')
    if not _port_is_free(BACKEND_PORT):raise RuntimeError(f'port {BACKEND_PORT} is already in use')
    if not _port_is_free(FRONTEND_PORT):raise RuntimeError(f'port {FRONTEND_PORT} is already in use')
    runtime.mkdir(parents=True,exist_ok=True);nonce=str(uuid.uuid4());processes=[];handles=[]
    try:
        for name,command,cwd,environment in service_specs(runtime,nonce,live_model):
            log_path=runtime/f'{name}.log';handle=log_path.open('w',encoding='utf-8')
            handles.append(handle)
            process=subprocess.Popen(
                command,cwd=cwd,env=environment,stdout=handle,stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            processes.append((name,process,log_path))
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            failed=[(name,process.returncode,log) for name,process,log in processes if process.poll() is not None]
            if failed:raise RuntimeError(f'service exited before readiness: {failed[0][0]} code={failed[0][1]} log={failed[0][2]}')
            try:
                api_status,health=_get_json(f'http://127.0.0.1:{BACKEND_PORT}/health')
                web_status=_get_status(f'http://127.0.0.1:{FRONTEND_PORT}/')
                if api_status==200 and web_status==200 and health.get('instance_nonce')==nonce:break
            except Exception:pass
            time.sleep(.1)
        else:raise RuntimeError('native stack startup timed out')
        manifest={
            'status':'ready','nonce':nonce,'paid_model_calls_allowed':bool(live_model),
            'api_url':f'http://127.0.0.1:{BACKEND_PORT}',
            'frontend_url':f'http://127.0.0.1:{FRONTEND_PORT}',
            'processes':{name:process.pid for name,process,_ in processes},
            'log_dir':str(runtime),
        }
        (runtime/'services.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')
        return manifest,processes,handles
    except Exception:
        for _,process,_ in reversed(processes):stop_process(process)
        for handle in handles:handle.close()
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-dir',type=Path,default=ROOT/'.runtime/native-stack')
    parser.add_argument('--startup-timeout',type=float,default=30)
    parser.add_argument('--verify-only',action='store_true',help='Verify startup and then cleanly stop both processes.')
    parser.add_argument('--live-model',action='store_true',help='Allow explicit .env/model credentials; never use this in ordinary CI.')
    args=parser.parse_args()
    manifest,processes,handles=start_stack(args.runtime_dir,args.startup_timeout,args.live_model)
    print(json.dumps(manifest,ensure_ascii=False,sort_keys=True),flush=True)
    try:
        if not args.verify_only:
            while all(process.poll() is None for _,process,_ in processes):time.sleep(.5)
            failed=next((item for item in processes if item[1].poll() is not None),None)
            raise RuntimeError(f'service stopped unexpectedly: {failed[0]} code={failed[1].returncode}')
    except KeyboardInterrupt:pass
    finally:
        for _,process,_ in reversed(processes):stop_process(process)
        for handle in handles:handle.close()
        cleanup_error=None
        try:wait_for_ports_free()
        except RuntimeError as exc:cleanup_error=exc
        stopped={**manifest,'status':'cleanup_failed' if cleanup_error else 'stopped','processes':{}}
        (args.runtime_dir/'services.json').write_text(
            json.dumps(stopped,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n',
        )
        print(json.dumps(stopped,ensure_ascii=False,sort_keys=True),flush=True)
        if cleanup_error:raise cleanup_error


if __name__=='__main__':main()
