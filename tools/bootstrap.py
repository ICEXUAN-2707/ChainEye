"""Install pinned native dependencies and initialize the local reviewed fixture."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend/src'))


def install_commands(check=False):
    npm='npm.cmd' if os.name=='nt' else 'npm'
    if check:
        return [[sys.executable,'-m','pip','check'],[npm,'run','typecheck','--prefix','frontend']]
    return [
        [sys.executable,'-m','pip','install','-r','backend/requirements.lock'],
        [npm,'ci','--prefix','frontend'],
    ]


def run_command(command):
    completed=subprocess.run(command,cwd=ROOT,check=False)
    if completed.returncode:
        raise RuntimeError(f'bootstrap command failed with exit {completed.returncode}: {command[0]}')


def initialize_database():
    from chain_eye.adapters.sqlite import SQLiteRepository
    from chain_eye.config import PROJECT_ROOT,database_path,upload_root
    repository=SQLiteRepository(database_path(),PROJECT_ROOT,upload_root())
    repository.seed()
    dataset=repository.get_dataset('demo-catl-2025',1)
    if dataset is None:raise RuntimeError('reviewed fixture dataset was not initialized')
    return {'dataset_id':dataset.id,'dataset_version':dataset.version,'data_basis':dataset.data_basis}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true',help='Verify installed dependencies without installing or initializing data.')
    parser.add_argument('--no-seed',action='store_true',help='Install dependencies without initializing the local fixture database.')
    args=parser.parse_args()
    for command in install_commands(check=args.check):run_command(command)
    fixture=None if args.check or args.no_seed else initialize_database()
    print(json.dumps({'status':'passed','mode':'check' if args.check else 'bootstrap','fixture':fixture},ensure_ascii=False,sort_keys=True))


if __name__=='__main__':main()
