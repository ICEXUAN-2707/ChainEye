"""Reproduce a persisted no-paid-model live failure and its explicitly labelled replay."""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime,timezone
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend/src'))
sys.path.insert(0,str(Path(__file__).resolve().parent))

from chain_eye.adapters.deepseek import DeepSeekAdapter
from chain_eye.adapters.sqlite import SQLiteRepository
from chain_eye.api.dto import RunCreate
from chain_eye.application.runs import RunExecutionService
from chain_eye.config import PROJECT_ROOT
from chain_eye.observability import JsonlLogger
from export_run_trace import export_trace


def _execute(service,repository,request,key):
    run,created=service.create_with_status(request,key)
    if not created:raise RuntimeError('reproduction idempotency key unexpectedly reused')
    claimed=repository.claim_next_run()
    if claimed!=run.id:raise RuntimeError('reproduction Run was not claimed')
    service.execute(run.id)
    return repository.get_run_record(run.id)


def reproduce(output_dir,db_path=None):
    output=Path(output_dir)
    if output.exists() and any(output.iterdir()):raise FileExistsError(f'reproduction output is not empty: {output}')
    output.mkdir(parents=True,exist_ok=True)
    database=Path(db_path) if db_path else output/'reproduction.sqlite'
    prior_disable=os.environ.get('CHAIN_EYE_DISABLE_MODEL');os.environ['CHAIN_EYE_DISABLE_MODEL']='1'
    try:
        logger=JsonlLogger(output/'chain-eye.jsonl')
        repository=SQLiteRepository(database,PROJECT_ROOT,output/'sources');repository.seed()
        service=RunExecutionService(repository,DeepSeekAdapter(),logger=logger)
        suffix=uuid.uuid4().hex
        source_request=RunCreate(
            dataset_id='demo-catl-2025',dataset_version=1,
            question='G5 无付费源 Run：分析动力电池收入和毛利',segment='power_battery',mode='live',
        )
        source=_execute(service,repository,source_request,f'g5-source-{suffix}')
        if source['status']!='partial' or (source.get('error') or {}).get('code')!='MODEL_UNAVAILABLE':
            raise AssertionError(f'no-paid source Run boundary changed: {source["status"]}')
        replay_request=RunCreate(
            dataset_id=source['dataset_id'],dataset_version=source['dataset_version'],
            question='G5 回放：明确复用已保存源 Run，不调用模型',segment='power_battery',
            mode='replay',replay_run_id=source['id'],
        )
        replay=_execute(service,repository,replay_request,f'g5-replay-{suffix}')
        if replay['status']!='partial' or replay.get('model_calls')!=0:
            raise AssertionError(f'replay did not preserve the source boundary: {replay["status"]}')
        if replay['request']['replay_run_id']!=source['id'] or replay.get('error')!=source.get('error'):
            raise AssertionError('replay source provenance was not preserved')
        source_trace=export_trace(database,source['id'],output/'source-trace.jsonl')
        replay_trace=export_trace(database,replay['id'],output/'replay-trace.jsonl')
        result={
            'status':'passed','mode':'replay','replay_disclosure':'saved_run_artifacts_only',
            'source_run_id':source['id'],'source_mode':'live','source_status':source['status'],
            'source_error_code':source['error']['code'],'replay_run_id':replay['id'],
            'replay_status':replay['status'],'replay_model_calls':replay['model_calls'],
            'dataset_id':source['dataset_id'],'dataset_version':source['dataset_version'],
            'execution_manifest_sha256':source['execution_manifest_sha256'],
            'source_trace_sha256':source_trace['sha256'],'replay_trace_sha256':replay_trace['sha256'],
            'structured_log':str(output/'chain-eye.jsonl'),'database':str(database),
            'paid_model_calls':False,'created_at':datetime.now(timezone.utc).isoformat(),
        }
        (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')
        logger.emit(
            'reproduction_finished',run_id=replay['id'],status='passed',
            error_code=None,source_run_id=source['id'],paid_model_calls=False,
        )
        return result
    finally:
        if prior_disable is None:os.environ.pop('CHAIN_EYE_DISABLE_MODEL',None)
        else:os.environ['CHAIN_EYE_DISABLE_MODEL']=prior_disable


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('replay',),default='replay')
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--db',type=Path)
    args=parser.parse_args()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output=args.output_dir or ROOT/'.runtime/reproductions'/f'{stamp}-{uuid.uuid4().hex[:8]}'
    print(json.dumps(reproduce(output,args.db),ensure_ascii=False,sort_keys=True))


if __name__=='__main__':main()
