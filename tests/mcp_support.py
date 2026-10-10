"""Deterministic persisted Run fixture for MCP protocol tests only."""
import json

from chain_eye.api.dto import RunCreate
from chain_eye.application.runs import RunExecutionService
from chain_eye.ports.services import LLMResponse


class MCPFixtureLLM:
    provider='fixture';model='mcp-fixture';adapter_version='mcp-fixture-v1'
    endpoint='fixture://tests';timeout_seconds=60
    public_config={
        'provider':provider,'model':model,'adapter_version':adapter_version,
        'endpoint':endpoint,'response_format':'json_object','timeout_seconds':timeout_seconds,
    }

    def generate(self,task_name,prompt_version,messages,response_schema,budget):
        context=json.loads(messages[-1]['content'])['context']
        calculation_id=context['allowed_calculation_ids'][0]
        calculation=next(item for item in context['calculations'] if item['id']==calculation_id)
        claim={
            'id':'mcp-fixture-claim','kind':'calculation',
            'text':f"测试计算结果为 {calculation['value']}。",
            'evidence_ids':context['allowed_evidence_ids'][:1],
            'calculation_ids':[calculation_id],'assumption_ids':[],
            'counter_evidence_ids':[],'limitations':['仅用于 MCP 自动化协议测试'],
            'review_status':'pending',
        }
        return LLMResponse(
            {'claims':[claim]},self.provider,self.model,{'total_tokens':1},1,'mcp-fixture-request',None,
        )


def create_completed_run(repository,key='mcp-fixture-run'):
    service=RunExecutionService(repository,MCPFixtureLLM())
    request=RunCreate(
        dataset_id='demo-catl-2025',dataset_version=1,question='MCP 协议测试',
        segment='power_battery',mode='live',
    )
    run,created=service.create_with_status(request,key)
    if created:
        claimed=repository.claim_next_run()
        if claimed!=run.id:raise AssertionError('fixture Run was not claimed')
        service.execute(run.id)
    record=repository.get_run_record(run.id)
    if record['status']!='completed' or repository.get_report(run.id) is None:
        raise AssertionError(f'fixture Run did not complete: {record["status"]}')
    return run.id
