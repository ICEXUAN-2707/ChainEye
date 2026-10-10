import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from mcp import Client,StdioServerParameters

from chain_eye.adapters.sqlite import SQLiteRepository
from tests.mcp_support import create_completed_run

ROOT=Path(__file__).resolve().parents[1]


class MCPStdioProtocol(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'protocol.sqlite'
        repo=SQLiteRepository(self.path,ROOT,Path(self.tmp.name)/'sources');repo.seed()
        self.run_id=create_completed_run(repo,'mcp-stdio-fixture')

    def tearDown(self):self.tmp.cleanup()

    async def test_real_stdio_process_initializes_lists_reads_and_exits(self):
        env={
            'PYTHONPATH':str(ROOT/'backend/src'),'CHAIN_EYE_DB':str(self.path),
            'CHAIN_EYE_MODE':'local','PYTHONUTF8':'1',
        }
        params=StdioServerParameters(
            command=sys.executable,args=['-m','chain_eye.mcp.server'],env=env,cwd=ROOT,encoding='utf-8',
        )
        async with Client(params,mode='legacy',read_timeout_seconds=15) as client:
            tools=await client.list_tools()
            self.assertEqual(len(tools.tools),5)
            resources=await client.list_resources()
            self.assertEqual(str(resources.resources[0].uri),'chain-eye://about')
            templates=await client.list_resource_templates()
            self.assertEqual(len(templates.resource_templates),5)
            prompts=await client.list_prompts()
            self.assertEqual(prompts.prompts[0].name,'evidence_bound_research')
            facts=await client.call_tool('get_facts',{
                'dataset_id':'demo-catl-2025','dataset_version':1,'segment':'power_battery',
            })
            self.assertFalse(facts.is_error);self.assertTrue(facts.structured_content['items'])
            trace=await client.call_tool('get_run_trace',{'run_id':self.run_id,'limit':200})
            self.assertFalse(trace.is_error);self.assertTrue(trace.structured_content['items'])
            report=await client.call_tool('get_report',{'run_id':self.run_id})
            self.assertFalse(report.is_error);self.assertEqual(report.structured_content['run_id'],self.run_id)
            about=await client.read_resource('chain-eye://about')
            self.assertEqual(json.loads(about.contents[0].text)['transport'],'stdio')


if __name__=='__main__':unittest.main()
