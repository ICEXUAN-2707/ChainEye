"""Validate the pinned native ChainEye toolchain without changing project state."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import socket
import subprocess
import sys
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
BACKEND_PORT=8000
FRONTEND_PORT=5173


def _command_version(command):
    try:
        completed=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=10,check=False)
    except (OSError,subprocess.SubprocessError) as exc:
        return None,exc.__class__.__name__
    value=(completed.stdout or completed.stderr).strip().splitlines()
    return (value[0] if completed.returncode==0 and value else None),f'exit={completed.returncode}'


def _port_is_free(port):
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
        if os.name=='posix':probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        try:probe.bind(('127.0.0.1',port))
        except OSError:return False
    return True


def collect_checks(skip_ports=False):
    checks=[]
    def add(name,passed,details,advisory=False):
        checks.append({'name':name,'status':'passed' if passed else ('warning' if advisory else 'failed'),'details':details})

    add('python_version',sys.version_info[:2]==(3,12),f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')
    encoding=(sys.stdout.encoding or '').casefold().replace('-','')
    add('utf8',sys.flags.utf8_mode==1 or encoding=='utf8',f'utf8_mode={sys.flags.utf8_mode}, stdout={sys.stdout.encoding}')
    node,node_detail=_command_version(['node','--version'])
    add('node_version',bool(node and node.lstrip('v').split('.')[0]=='24'),node or node_detail)
    npm='npm.cmd' if os.name=='nt' else 'npm'
    npm_version,npm_detail=_command_version([npm,'--version'])
    add('npm',bool(npm_version),npm_version or npm_detail)
    required=(
        ROOT/'backend/requirements.lock',ROOT/'frontend/package-lock.json',
        ROOT/'contracts/openapi.json',ROOT/'tools/start_backend.py',
    )
    missing=[str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    add('lockfiles_and_entrypoints',not missing,{'missing':missing})
    imports=('fastapi','pydantic','uvicorn','mcp','httpx2')
    missing_imports=[name for name in imports if importlib.util.find_spec(name) is None]
    add('backend_dependencies',not missing_imports,{'missing':missing_imports},advisory=True)
    add('frontend_dependencies',(ROOT/'frontend/node_modules/vite').is_dir(),'frontend/node_modules/vite',advisory=True)
    runtime=ROOT/'.runtime';writable_target=runtime if runtime.exists() else ROOT
    add('runtime_writable',os.access(writable_target,os.W_OK),str(writable_target.relative_to(ROOT) or '.'))
    if not skip_ports:
        add('backend_port',_port_is_free(BACKEND_PORT),f'127.0.0.1:{BACKEND_PORT}')
        add('frontend_port',_port_is_free(FRONTEND_PORT),f'127.0.0.1:{FRONTEND_PORT}')
    return {'status':'failed' if any(item['status']=='failed' for item in checks) else 'passed','checks':checks}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-ports',action='store_true',help='Skip the two listener checks when inspecting an already running stack.')
    args=parser.parse_args()
    result=collect_checks(skip_ports=args.skip_ports)
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    raise SystemExit(0 if result['status']=='passed' else 1)


if __name__=='__main__':main()
