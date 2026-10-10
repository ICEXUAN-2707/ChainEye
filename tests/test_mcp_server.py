import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp import Client
from mcp.shared.exceptions import MCPError

from chain_eye.adapters.sqlite import SQLiteRepository
from chain_eye.mcp.server import MCP_TOOL_NAMES,create_server
from tests.mcp_support import create_completed_run

ROOT=Path(__file__).resolve().parents[1]


class MCPServerSurface(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'mcp.sqlite'
        self.repo=SQLiteRepository(self.path,ROOT,Path(self.tmp.name)/'sources');self.repo.seed()
        self.server=create_server(self.repo)

    def tearDown(self):self.tmp.cleanup()

    def test_default_server_does_not_seed_demo_data(self):
        with patch('chain_eye.mcp.server.build_repository',return_value=object()) as builder:
            create_server(db_path='read-only.sqlite')
        builder.assert_called_once_with('read-only.sqlite',False)

    async def test_catalog_exposes_only_read_tools_resources_and_prompt(self):
        async with Client(self.server,mode='legacy') as client:
            tools=await client.list_tools();names={item.name for item in tools.tools}
            self.assertEqual(names,MCP_TOOL_NAMES)
            self.assertNotIn('compute_financials',names);self.assertNotIn('compute_scenario',names)
            self.assertTrue(all(item.annotations.read_only_hint for item in tools.tools))
            resources=await client.list_resources()
            self.assertEqual([str(item.uri) for item in resources.resources],['chain-eye://about'])
            templates=await client.list_resource_templates()
            self.assertEqual(len(templates.resource_templates),5)
            prompts=await client.list_prompts()
            self.assertEqual([item.name for item in prompts.prompts],['evidence_bound_research'])

    async def test_snapshot_tools_and_resources_use_real_repository_data(self):
        facts=self.repo.facts('demo-catl-2025',1);evidence_id=facts[0].evidence_ids[0]
        before=self.repo.list_run_events('not-a-run',0,200)
        async with Client(self.server,mode='legacy') as client:
            result=await client.call_tool('get_facts',{
                'dataset_id':'demo-catl-2025','dataset_version':1,'metric_ids':[facts[0].metric],
            })
            self.assertFalse(result.is_error);self.assertTrue(result.structured_content['items'])
            evidence=await client.call_tool('get_evidence',{
                'dataset_id':'demo-catl-2025','dataset_version':1,'evidence_ids':[evidence_id],
            })
            self.assertEqual(evidence.structured_content['items'][0]['id'],evidence_id)
            searched=await client.call_tool('search_documents',{
                'dataset_id':'demo-catl-2025','dataset_version':1,'query':evidence.structured_content['items'][0]['excerpt'][:12],
            })
            self.assertFalse(searched.is_error);self.assertTrue(searched.structured_content['items'])
            resource=await client.read_resource('chain-eye://datasets/demo-catl-2025/versions/1')
            self.assertEqual(json.loads(resource.contents[0].text)['version'],1)
            evidence_resource=await client.read_resource(
                f'chain-eye://datasets/demo-catl-2025/versions/1/evidence/{evidence_id}',
            )
            self.assertEqual(json.loads(evidence_resource.contents[0].text)['id'],evidence_id)
            prompt=await client.get_prompt('evidence_bound_research',{
                'question':'分析动力电池收入','segment':'power_battery',
            })
            self.assertIn('prompt_sha256=',prompt.messages[0].content.text)
        self.assertEqual(self.repo.list_run_events('not-a-run',0,200),before)

    async def test_scope_and_argument_failures_are_explicit(self):
        facts=self.repo.facts('demo-catl-2025',1);evidence_id=facts[0].evidence_ids[0]
        async with Client(self.server,mode='legacy') as client:
            missing=await client.call_tool('get_facts',{
                'dataset_id':'demo-catl-2025','dataset_version':999,
            })
            self.assertTrue(missing.is_error);self.assertIn('snapshot does not exist',missing.content[0].text)
            bad_limit=await client.call_tool('search_documents',{
                'dataset_id':'demo-catl-2025','dataset_version':1,'query':'收入','top_k':9,
            })
            self.assertTrue(bad_limit.is_error);self.assertIn('top_k',bad_limit.content[0].text)
            oversized=await client.call_tool('search_documents',{
                'dataset_id':'demo-catl-2025','dataset_version':1,'query':'x'*501,
            })
            self.assertTrue(oversized.is_error);self.assertIn('500',oversized.content[0].text)
            internal=await client.call_tool('compute_financials',{})
            self.assertTrue(internal.is_error);self.assertIn('Unknown tool',internal.content[0].text)
            missing_report=await client.call_tool('get_report',{'run_id':'missing-run'})
            self.assertTrue(missing_report.is_error);self.assertIn('run does not exist',missing_report.content[0].text)
            with self.assertRaises(MCPError) as wrong_snapshot:
                await client.read_resource(
                    f'chain-eye://datasets/demo-catl-2025/versions/999/evidence/{evidence_id}',
                )
            self.assertIn('snapshot does not exist',str(wrong_snapshot.exception))

    async def test_catalog_and_static_resource_do_not_leak_environment_secrets(self):
        async with Client(self.server,mode='legacy') as client:
            tools=await client.list_tools();about=await client.read_resource('chain-eye://about')
            value=json.dumps(tools.model_dump(mode='json'),ensure_ascii=False)+about.contents[0].text
            lowered=value.casefold()
            self.assertNotIn('deepseek_api_key',lowered);self.assertNotIn('authorization',lowered)

    async def test_trace_and_report_reads_do_not_mutate_run(self):
        run_id=create_completed_run(self.repo)
        before=self.repo.list_run_events(run_id,0,200)[0]
        async with Client(self.server,mode='legacy') as client:
            trace=await client.call_tool('get_run_trace',{'run_id':run_id,'limit':20})
            self.assertFalse(trace.is_error);self.assertTrue(trace.structured_content['items'])
            report=await client.call_tool('get_report',{'run_id':run_id})
            self.assertFalse(report.is_error);self.assertEqual(report.structured_content['run_id'],run_id)
            trace_resource=await client.read_resource(f'chain-eye://runs/{run_id}/trace')
            self.assertEqual(json.loads(trace_resource.contents[0].text)['run_id'],run_id)
            report_resource=await client.read_resource(f'chain-eye://runs/{run_id}/report')
            self.assertEqual(json.loads(report_resource.contents[0].text)['run_id'],run_id)
        after=self.repo.list_run_events(run_id,0,200)[0]
        self.assertEqual([item.model_dump() for item in after],[item.model_dump() for item in before])


if __name__=='__main__':unittest.main()
