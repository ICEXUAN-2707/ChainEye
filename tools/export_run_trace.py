"""Export a bounded, redacted Run trace through the same read-only MCP boundary."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend/src'))

from chain_eye.mcp.context import build_repository,run_context
from chain_eye.mcp.serialization import bounded_value
from chain_eye.tools.registry import DEFAULT_TOOL_REGISTRY

MAX_TRACE_LINE_BYTES=65536


def _encoded_line(value):
    encoded=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    if len(encoded)<=MAX_TRACE_LINE_BYTES:return encoded
    digest=hashlib.sha256(encoded).hexdigest()
    reduced={
        key:value.get(key) for key in ('kind','seq','run_id','type','node','at') if key in value
    }
    reduced['payload']={'truncated':True,'size_bytes':len(encoded),'sha256':digest}
    return json.dumps(reduced,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')


def export_trace(db_path,run_id,output_path,overwrite=False):
    output=Path(output_path)
    if output.exists() and not overwrite:raise FileExistsError(f'trace output already exists: {output}')
    repository=build_repository(db_path,seed=False);context=run_context(repository,run_id)
    record=repository.get_run_record(run_id);lines=[]
    lines.append(bounded_value({
        'kind':'manifest','format':'chain-eye-run-trace-v1','run_created_at':record.get('created_at'),
        'run_id':run_id,'dataset_id':record['dataset_id'],'dataset_version':record['dataset_version'],
        'mode':record['mode'],'status':record['status'],'execution_manifest_sha256':record.get('execution_manifest_sha256'),
    }))
    after=0
    while True:
        page=DEFAULT_TOOL_REGISTRY.call(
            'get_run_trace',{'run_id':run_id,'after_seq':after,'limit':200},context,caller='mcp',
        )
        for item in page['items']:lines.append(bounded_value({'kind':'event',**item}))
        if not page['has_more']:break
        after=page['next_after_seq']
    payload=b'\n'.join(_encoded_line(line) for line in lines)+b'\n'
    output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(payload)
    return {
        'status':'passed','run_id':run_id,'events':len(lines)-1,'output':str(output),
        'sha256':hashlib.sha256(payload).hexdigest(),'size_bytes':len(payload),
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=ROOT/'.runtime/chain_eye.sqlite')
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--overwrite',action='store_true')
    args=parser.parse_args()
    output=args.output or ROOT/'.runtime/traces'/f'{args.run_id}.jsonl'
    print(json.dumps(export_trace(args.db,args.run_id,output,args.overwrite),ensure_ascii=False,sort_keys=True))


if __name__=='__main__':main()
