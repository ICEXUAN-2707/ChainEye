"""Launch the real stdio MCP server and exercise its read-only protocol surface."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import Client,StdioServerParameters

from chain_eye.mcp.context import build_repository

ROOT=Path(__file__).resolve().parents[1]


async def smoke(db_path,run_id=None):
    build_repository(db_path,seed=True)
    env={
        'PYTHONPATH':str(ROOT/'backend/src'),'CHAIN_EYE_DB':str(Path(db_path).resolve()),
        'CHAIN_EYE_MODE':'local','PYTHONUTF8':'1',
    }
    params=StdioServerParameters(
        command=sys.executable,args=['-m','chain_eye.mcp.server'],env=env,cwd=ROOT,encoding='utf-8',
    )
    async with Client(params,mode='legacy',read_timeout_seconds=30) as client:
        tools=await client.list_tools();tool_names=sorted(item.name for item in tools.tools)
        expected=['get_evidence','get_facts','get_report','get_run_trace','search_documents']
        if tool_names!=expected:raise AssertionError(f'unexpected MCP tools: {tool_names}')
        resources=await client.list_resources();templates=await client.list_resource_templates()
        prompts=await client.list_prompts()
        if [item.name for item in prompts.prompts]!=['evidence_bound_research']:
            raise AssertionError('unexpected MCP prompts')
        facts=await client.call_tool('get_facts',{
            'dataset_id':'demo-catl-2025','dataset_version':1,'segment':'power_battery',
        })
        if facts.is_error or not facts.structured_content['items']:raise AssertionError('get_facts failed')
        fact=next(item for item in facts.structured_content['items'] if item['evidence_ids'])
        evidence=await client.call_tool('get_evidence',{
            'dataset_id':'demo-catl-2025','dataset_version':1,'evidence_ids':[fact['evidence_ids'][0]],
        })
        if evidence.is_error or len(evidence.structured_content['items'])!=1:
            raise AssertionError('get_evidence failed')
        excerpt=evidence.structured_content['items'][0]['excerpt']
        search=await client.call_tool('search_documents',{
            'dataset_id':'demo-catl-2025','dataset_version':1,'query':excerpt[:12],'top_k':2,
        })
        if search.is_error or not search.structured_content['items']:
            raise AssertionError('search_documents failed')
        dataset=await client.read_resource('chain-eye://datasets/demo-catl-2025/versions/1')
        skill=await client.read_resource('chain-eye://skills/evidence_bound_research/1')
        prompt=await client.get_prompt('evidence_bound_research',{
            'question':'MCP smoke：分析动力电池收入','segment':'power_battery',
        })
        run_checks='skipped: pass --run-id for a persisted completed Run'
        if run_id:
            trace=await client.call_tool('get_run_trace',{'run_id':run_id,'limit':200})
            report=await client.call_tool('get_report',{'run_id':run_id})
            if trace.is_error or not trace.structured_content['items']:raise AssertionError('get_run_trace failed')
            if report.is_error or report.structured_content['run_id']!=run_id:raise AssertionError('get_report failed')
            run_checks='passed'
        result={
            'status':'passed','transport':'stdio','tool_names':tool_names,
            'resources':len(resources.resources),'resource_templates':len(templates.resource_templates),
            'prompts':len(prompts.prompts),'facts':len(facts.structured_content['items']),
            'evidence_id':fact['evidence_ids'][0],'search_results':len(search.structured_content['items']),
            'dataset_resource_id':json.loads(dataset.contents[0].text)['id'],
            'skill_spec_sha256':json.loads(skill.contents[0].text)['spec_sha256'],
            'prompt_contains_hash':'prompt_sha256=' in prompt.messages[0].content.text,
            'run_checks':run_checks,'paid_model_calls':False,
        }
        serialized=json.dumps(result,ensure_ascii=False,sort_keys=True)
        if any(marker in serialized.casefold() for marker in ('authorization','api_key','password','secret')):
            raise AssertionError('sensitive marker leaked into MCP smoke output')
        return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',default=str(ROOT/'.runtime/mcp-smoke.sqlite'))
    parser.add_argument('--run-id')
    args=parser.parse_args()
    print(json.dumps(asyncio.run(smoke(args.db,args.run_id)),ensure_ascii=False,sort_keys=True))


if __name__=='__main__':main()
