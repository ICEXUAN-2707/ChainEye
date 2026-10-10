"""Repository and snapshot context assembly for MCP calls."""
import os
import time
from pathlib import Path

from chain_eye.adapters.sqlite import SQLiteRepository
from chain_eye.tools.spec import ToolContext,ToolFailure

ROOT=Path(__file__).resolve().parents[4]


def build_repository(db_path=None,seed=True):
    if os.getenv('CHAIN_EYE_MODE','local')!='local':
        raise RuntimeError('ChainEye MCP supports local mode only')
    repository=SQLiteRepository(
        db_path or os.getenv('CHAIN_EYE_DB',str(ROOT/'.runtime/chain-eye.sqlite')),ROOT,
    )
    if seed:repository.seed()
    return repository


def snapshot_context(repository,dataset_id,dataset_version):
    if not isinstance(dataset_id,str) or not dataset_id or len(dataset_id)>128:
        raise ToolFailure('dataset_id must be a non-empty string')
    if not isinstance(dataset_version,int) or isinstance(dataset_version,bool) or dataset_version<1:
        raise ToolFailure('dataset_version must be a positive integer')
    if repository.get_dataset(dataset_id,dataset_version) is None:
        raise ToolFailure('dataset snapshot does not exist')
    return ToolContext(
        repository,None,None,None,dataset_id,dataset_version,time.monotonic,
    )


def run_context(repository,run_id):
    if not isinstance(run_id,str) or not run_id or len(run_id)>128:raise ToolFailure('run_id must be a non-empty string')
    record=repository.get_run_record(run_id)
    if record is None or record.get('owner_id')!='local':raise ToolFailure('run does not exist')
    return snapshot_context(repository,record['dataset_id'],record['dataset_version'])
