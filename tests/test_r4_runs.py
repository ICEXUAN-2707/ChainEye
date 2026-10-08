import json
import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from chain_eye.adapters.deepseek import DeepSeekAdapter,ModelInvalidResponse,ModelRateLimited,ModelUnavailable
from chain_eye.adapters.sqlite import SQLiteRepository
from chain_eye.api.app import create_app
from chain_eye.api.dto import RunCreate
from chain_eye.application.errors import AppError
from chain_eye.application.run_tools import RunTools,TOOL_NAMES,ToolFailure
from chain_eye.application.runs import PROMPT_VERSION,RunExecutionService
from chain_eye.ports.services import LLMResponse

ROOT=Path(__file__).resolve().parents[1]


class FakeLLM:
    provider='fake';model='fake-r4'
    public_config={'provider':'fake','model':'fake-r4','response_format':'json_object'}
    def __init__(self,failures=None,unsupported=False,empty=False,counter_evidence_id=None,evidence_id=None,text_override=None,claim_kind='calculation',use_calculation=True):
        self.failures=list(failures or []);self.unsupported=unsupported;self.empty=empty
        self.counter_evidence_id=counter_evidence_id;self.evidence_id=evidence_id;self.text_override=text_override
        self.claim_kind=claim_kind;self.use_calculation=use_calculation;self.calls=[];self.prompt_versions=[];self.system_prompts=[]
    def generate(self,task_name,prompt_version,messages,response_schema,budget):
        payload=json.loads(messages[-1]['content']);question=payload['question'];context=payload['context']
        self.calls.append((question,context));self.prompt_versions.append(prompt_version);self.system_prompts.append(messages[0]['content'])
        if self.failures:raise self.failures.pop(0)
        if self.empty:return LLMResponse({'claims':[]},self.provider,self.model,{'total_tokens':1},1,'fake-empty',None)
        evidence=[self.evidence_id] if self.evidence_id else context['allowed_evidence_ids'][:1]
        calculations=context['allowed_calculation_ids'][:1] if self.use_calculation else []
        calculation=next((item for item in context['calculations'] if item and calculations and item['id']==calculations[0]),None)
        claim={
            'id':f'claim-{len(self.calls)}','kind':self.claim_kind,'text':self.text_override or f"计算结果为 {calculation['value']}。",
            'evidence_ids':[] if self.unsupported else evidence,
            'calculation_ids':[] if self.unsupported else calculations,'assumption_ids':[],
            'counter_evidence_ids':[self.counter_evidence_id] if self.counter_evidence_id else [],
            'limitations':['仅基于绑定的数据快照'],'review_status':'pending',
        }
        return LLMResponse({'claims':[claim]},self.provider,self.model,{'total_tokens':10},2,'fake-request',None)


class InvalidLLM(FakeLLM):
    def generate(self,task_name,prompt_version,messages,response_schema,budget):
        self.calls.append((task_name,messages));raise ModelInvalidResponse('bad json')


class Clock:
    def __init__(self):self.calls=0
    def __call__(self):
        self.calls+=1
        return 0 if self.calls==1 else 601


class R4Runs(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'db.sqlite'
        self.repo=SQLiteRepository(self.path,ROOT,Path(self.tmp.name)/'sources');self.repo.seed()
    def tearDown(self):self.tmp.cleanup()

    def request(self,question='分析动力电池收入和毛利',mode='live',**updates):
        body=dict(dataset_id='demo-catl-2025',dataset_version=1,question=question,segment='power_battery',mode=mode)
        body.update(updates);return RunCreate.model_validate(body)

    def execute(self,llm=None,key='r4-run-key',request=None,clock=time.monotonic):
        service=RunExecutionService(self.repo,llm or FakeLLM(),clock=clock)
        run,created=service.create_with_status(request or self.request(),key);self.assertTrue(created)
        self.assertEqual(self.repo.claim_next_run(),run.id);service.execute(run.id)
        return service,self.repo.get_run(run.id),self.repo.get_run_record(run.id)

    def test_live_run_persists_supported_claims_calculations_and_events(self):
        llm=FakeLLM();_,run,record=self.execute(llm)
        self.assertEqual(run.status,'completed');self.assertTrue(run.report_ready);self.assertEqual(run.current_node,'report')
        self.assertEqual(len(record['calculation_ids']),6);self.assertEqual(record['claims'][0]['review_status'],'pending')
        self.assertEqual(record['prompt_version'],PROMPT_VERSION);self.assertEqual(llm.prompt_versions,[PROMPT_VERSION])
        self.assertEqual(record['prompt_id'],'claims');self.assertEqual(len(record['prompt_sha256']),64)
        self.assertEqual(set(record['skill_versions']),{'financial_diagnosis','evidence_bound_research','scenario_impact'})
        self.assertIn('verified Fact.value',llm.system_prompts[0])
        events,after,more=self.repo.list_run_events(run.id,0,200)
        self.assertEqual([event.seq for event in events],list(range(1,len(events)+1)));self.assertEqual(after,len(events));self.assertFalse(more)
        tools={event.payload['tool_name'] for event in events if event.type=='tool_call'}
        self.assertEqual(tools,TOOL_NAMES-{'compute_scenario'})
        self.assertTrue(all(event.payload.get('input_sha256') for event in events if event.type=='tool_call'))
        skills={event.payload['skill_id'] for event in events if event.type=='tool_call'}
        self.assertEqual(skills,{'financial_diagnosis','evidence_bound_research'})
        llm_event=next(event for event in events if event.type=='llm_call' and event.payload['status']=='completed')
        self.assertEqual(llm_event.payload['skill_id'],'evidence_bound_research')
        self.assertEqual(llm_event.payload['prompt_sha256'],record['prompt_sha256'])

    def test_numeric_claim_without_references_is_downgraded(self):
        _,run,record=self.execute(FakeLLM(unsupported=True))
        self.assertEqual(run.status,'completed');self.assertEqual(record['claims'][0]['review_status'],'insufficient')

    def test_numeric_claim_not_supported_by_its_references_is_downgraded(self):
        _,run,record=self.execute(FakeLLM(text_override='计算结果为 999999999999。'),key='unsupported-number')
        self.assertEqual(run.status,'completed');self.assertEqual(record['claims'][0]['review_status'],'insufficient')

    def test_fact_claim_accepts_normalized_value_and_year_from_cited_fact(self):
        llm=FakeLLM(
            evidence_id='e-2025-power_battery-revenue',claim_kind='fact',use_calculation=False,
            text_override='2025 年动力电池收入为 316506369000 CNY。',
        )
        _,run,record=self.execute(llm,key='normalized-fact-value')
        self.assertEqual(run.status,'completed');self.assertEqual(record['claims'][0]['review_status'],'pending')
        self.assertEqual(record['claims'][0]['calculation_ids'],[])

    def test_fact_claim_cannot_borrow_normalized_value_from_uncited_fact(self):
        llm=FakeLLM(
            evidence_id='e-2025-power_battery-revenue',claim_kind='fact',use_calculation=False,
            text_override='2025 年动力电池营业成本为 241064397000 CNY。',
        )
        _,run,record=self.execute(llm,key='uncited-fact-value')
        self.assertEqual(run.status,'completed');self.assertEqual(record['claims'][0]['review_status'],'insufficient')

    def test_document_injection_is_delimited_as_untrusted_data(self):
        llm=FakeLLM();self.execute(llm)
        documents=llm.calls[0][1]['documents'];self.assertTrue(documents)
        self.assertTrue(all(item['content'].startswith('<document>') and item['content'].endswith('</document>') for item in documents))

    def test_idempotency_reuses_run_and_rejects_changed_body(self):
        service=RunExecutionService(self.repo,FakeLLM());first,created=service.create_with_status(self.request(),'same-key')
        second,created_again=service.create_with_status(self.request(),'same-key')
        self.assertFalse(created_again);self.assertEqual(first.id,second.id)
        with self.assertRaises(AppError) as caught:service.create_with_status(self.request(question='不同问题'),'same-key')
        self.assertEqual(caught.exception.status,409)

    def test_scenario_waits_for_assumptions_then_resumes(self):
        service=RunExecutionService(self.repo,FakeLLM());run,_=service.create_with_status(self.request(question='分析原材料价格变化对毛利的影响'),'scenario-run')
        self.repo.claim_next_run();service.execute(run.id)
        waiting=self.repo.get_run(run.id);self.assertEqual(waiting.status,'waiting_review');self.assertEqual(waiting.missing_requirements,['scenario_assumptions'])
        from chain_eye.api.dto import ResumeRequest
        without_assumptions=ResumeRequest.model_validate({'expected_run_status':'waiting_review','dataset_version':1})
        with self.assertRaises(AppError) as caught:service.resume(run.id,without_assumptions)
        self.assertEqual(caught.exception.code,'INVALID_INPUT');self.assertEqual(self.repo.get_run(run.id).status,'waiting_review')
        resume=ResumeRequest.model_validate({'expected_run_status':'waiting_review','dataset_version':1,'assumptions':{'cost_exposure':'0.1','effective_price_shock':'-0.2','customer_pass_through':'0.5','basis':'user_assumption','acknowledged':True}})
        service.resume(run.id,resume);self.repo.claim_next_run();service.execute(run.id)
        record=self.repo.get_run_record(run.id);self.assertEqual(record['status'],'completed');self.assertEqual(len(record['scenario_ids']),1);self.assertEqual(len(record['calculation_ids']),15)
        events,_,_=self.repo.list_run_events(run.id,0,200)
        scenario_call=next(event for event in events if event.type=='tool_call' and event.payload['tool_name']=='compute_scenario')
        self.assertEqual(scenario_call.payload['skill_id'],'scenario_impact')
        scenario_claim=next(item for item in record['claims'] if item['id'].startswith('scenario-'))
        self.assertEqual(set(scenario_claim['calculation_ids']),set(record['calculation_ids'][-9:]))
        self.assertEqual(scenario_claim['assumption_ids'],record['assumption_ids']);self.assertEqual(scenario_claim['review_status'],'pending')

    def test_missing_verified_baseline_fails_and_requires_a_new_snapshot_run(self):
        original=self.repo.facts
        def missing_current_revenue(dataset_id,version):
            return [fact for fact in original(dataset_id,version) if not (fact.segment=='power_battery' and fact.metric=='revenue' and fact.period_end=='2025-12-31')]
        with patch.object(self.repo,'facts',side_effect=missing_current_revenue):
            _,run,record=self.execute(key='missing-baseline')
        self.assertEqual(run.status,'failed');self.assertEqual(run.error.code,'FACT_NOT_VERIFIED')
        self.assertEqual(run.error.details['action'],'create_new_run_after_fact_review')
        self.assertNotEqual(run.status,'waiting_review');self.assertEqual(record['calculation_ids'],[])

    def test_counter_evidence_must_be_in_the_model_context(self):
        _,run,record=self.execute(FakeLLM(counter_evidence_id='not-in-snapshot'),key='bad-counter')
        self.assertEqual(run.status,'completed');self.assertEqual(record['claims'][0]['review_status'],'rejected')

    def test_existing_but_unprovided_evidence_is_rejected(self):
        segment_ids={item for fact in self.repo.facts('demo-catl-2025',1) if fact.segment=='power_battery' for item in fact.evidence_ids}
        outside=next(item.id for item in self.repo.evidence_for_snapshot('demo-catl-2025',1) if item.id not in segment_ids)
        _,run,record=self.execute(FakeLLM(evidence_id=outside),key='unprovided-evidence',request=self.request(question='zzzz-no-match'))
        self.assertEqual(run.status,'completed');self.assertEqual(record['claims'][0]['review_status'],'rejected')

    def test_empty_model_claims_do_not_complete_the_run(self):
        _,run,_=self.execute(FakeLLM(empty=True),key='empty-claims')
        self.assertEqual(run.status,'partial');self.assertEqual(run.error.code,'MODEL_INVALID_RESPONSE')

    def test_replay_copies_validated_artifacts_without_model_call(self):
        llm=FakeLLM();service,source,source_record=self.execute(llm,key='source-run')
        replay=self.request(question='回放',mode='replay',replay_run_id=source.id)
        created,_=service.create_with_status(replay,'replay-key');self.repo.claim_next_run();service.execute(created.id)
        record=self.repo.get_run_record(created.id)
        self.assertEqual(record['status'],'completed');self.assertEqual(record['model_calls'],0);self.assertEqual(record['claims'],source_record['claims']);self.assertEqual(len(llm.calls),1)
        events,_,_=self.repo.list_run_events(created.id,0,100);self.assertFalse(any(event.type=='llm_call' for event in events))

    def test_replay_rejects_other_snapshot(self):
        service,source,_=self.execute(key='source-snapshot')
        request=self.request(mode='replay',replay_run_id=source.id,dataset_version=2)
        with self.assertRaises(AppError) as caught:service.create_with_status(request,'bad-replay')
        self.assertIn(caught.exception.code,('NOT_FOUND','SCOPE_MISMATCH'))

    def test_rate_limit_retries_twice_then_marks_partial(self):
        failure=lambda:ModelRateLimited('limited')
        llm=FakeLLM([failure(),failure(),failure()]);_,run,record=self.execute(llm)
        self.assertEqual(len(llm.calls),3);self.assertEqual(run.status,'partial');self.assertEqual(run.error.code,'MODEL_RATE_LIMITED');self.assertEqual(record['node_retries']['research'],2)

    def test_invalid_model_json_marks_partial(self):
        _,run,_=self.execute(InvalidLLM())
        self.assertEqual(run.status,'partial');self.assertEqual(run.error.code,'MODEL_INVALID_RESPONSE')

    def test_total_budget_exhaustion_is_failed_before_side_effects(self):
        _,run,record=self.execute(FakeLLM(),clock=Clock())
        self.assertEqual(run.status,'failed');self.assertEqual(run.error.code,'BUDGET_EXCEEDED');self.assertEqual(record['calculation_ids'],[])

    def test_recovery_does_not_retry_interrupted_model_node(self):
        service=RunExecutionService(self.repo,FakeLLM());run,_=service.create_with_status(self.request(),'interrupted')
        self.repo.update_run(run.id,status='running',current_node='research',claims=[])
        self.assertEqual(self.repo.recover_interrupted_runs(),[])
        recovered=self.repo.get_run(run.id);self.assertEqual(recovered.status,'failed');self.assertEqual(recovered.error.code,'RUN_INTERRUPTED')

    def test_event_sequence_is_atomic_and_cursor_is_stable(self):
        service=RunExecutionService(self.repo,FakeLLM());run,_=service.create_with_status(self.request(),'event-run')
        with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(lambda index:self.repo.append_event(run.id,'node_status','plan',{'index':index}),range(40)))
        first,next_seq,more=self.repo.list_run_events(run.id,0,13);self.assertEqual(len(first),13);self.assertEqual(next_seq,13);self.assertTrue(more)
        rest,last,more=self.repo.list_run_events(run.id,next_seq,100);self.assertEqual([item.seq for item in [*first,*rest]],list(range(1,41)));self.assertEqual(last,40);self.assertFalse(more)

    def test_run_becomes_stale_when_dataset_advances(self):
        _,run,_=self.execute(key='stale-run');self.assertFalse(run.stale)
        current=self.repo.get_run_record(run.id)
        with self.repo.connect() as db:
            body=self.repo.get_dataset('demo-catl-2025').model_copy(update={'version':2}).model_dump_json()
            db.execute('UPDATE datasets SET current_version=2,body=? WHERE id=?',(body,'demo-catl-2025'))
            db.execute('INSERT INTO dataset_snapshots VALUES (?,?,?)',('demo-catl-2025',2,body))
        self.assertTrue(self.repo.get_run(run.id).stale);self.assertEqual(current['dataset_version'],1)

    def test_unknown_tool_is_rejected(self):
        tools=RunTools(self.repo,None,None,'run','demo-catl-2025',1)
        with self.assertRaises(ToolFailure):tools.call('open_url',{})

    def test_tool_contract_rejects_cross_snapshot_and_top_k_over_eight(self):
        tools=RunTools(self.repo,None,None,'run','demo-catl-2025',1)
        with self.assertRaises(ToolFailure):
            tools.call('get_facts',{'dataset_id':'other','dataset_version':1,'metric_ids':[],'segment':None,'period':None})
        with self.assertRaises(ToolFailure):
            tools.call('search_documents',{'dataset_id':'demo-catl-2025','dataset_version':1,'query':'收入','filters':{},'top_k':9})

    def test_chinese_query_searches_within_the_snapshot(self):
        tools=RunTools(self.repo,None,None,'run','demo-catl-2025',1)
        items=tools.call('search_documents',{
            'dataset_id':'demo-catl-2025','dataset_version':1,
            'query':'分析动力电池收入和毛利','filters':{},'top_k':8,
        })
        self.assertTrue(items);self.assertLessEqual(len(items),8)

    def test_financial_tool_requires_exact_fact_revisions(self):
        tools=RunTools(self.repo,RunExecutionService(self.repo,FakeLLM()).financials,None,'run','demo-catl-2025',1)
        fact=next(item for item in self.repo.facts('demo-catl-2025',1) if item.segment=='power_battery')
        with self.assertRaises(ToolFailure):
            tools.call('compute_financials',{'fact_ids':[fact.id],'revisions':{fact.id:fact.revision+1},'metric_ids':['gross_profit']})

    def test_tool_budget_is_checked_before_side_effecting_service_call(self):
        calls=[]
        class Financial:
            def compute(self,*args):calls.append(args);return []
        ticks=iter((0,91,91))
        tools=RunTools(self.repo,Financial(),None,'run','demo-catl-2025',1,clock=lambda:next(ticks))
        with self.assertRaises(ToolFailure):
            tools.call('compute_financials',{'fact_ids':[],'revisions':{},'metric_ids':[]})
        self.assertEqual(calls,[])


class R4HTTPIntegration(unittest.TestCase):
    def test_create_poll_events_cursor_and_report_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=create_app(Path(tmp)/'db.sqlite',upload_dir=Path(tmp)/'sources',llm=FakeLLM())
            with TestClient(app,base_url='http://localhost',client=('127.0.0.1',50000)) as client:
                body={'dataset_id':'demo-catl-2025','dataset_version':1,'question':'分析动力电池收入和毛利','segment':'power_battery','mode':'live'}
                created=client.post('/api/v1/runs',json=body,headers={'Idempotency-Key':'http-run-key'});self.assertEqual(created.status_code,202)
                run_id=created.json()['id'];run=None
                for _ in range(100):
                    run=client.get(f'/api/v1/runs/{run_id}').json()
                    if run['status'] not in ('queued','running'):break
                    time.sleep(0.01)
                self.assertEqual(run['status'],'completed')
                first=client.get(f'/api/v1/runs/{run_id}/events?limit=3').json();self.assertEqual(len(first['items']),3);self.assertTrue(first['has_more'])
                second=client.get(f"/api/v1/runs/{run_id}/events?after_seq={first['next_after_seq']}&limit=200").json()
                self.assertEqual(second['items'][0]['seq'],first['next_after_seq']+1)
                report=client.get(f'/api/v1/runs/{run_id}/report');self.assertEqual(report.status_code,200);self.assertEqual(report.json()['run_id'],run_id)


class DeepSeekBoundary(unittest.TestCase):
    class Response:
        def __init__(self,status_code,body=None):self.status_code=status_code;self.body=body
        def json(self):return self.body

    @staticmethod
    def generate(adapter):
        return adapter.generate('claims','r4-test',[{'role':'user','content':'{}'}],{'type':'object'},{'timeout_seconds':1,'max_output_tokens':100})

    def test_default_model_is_flash_and_environment_can_override_it(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(DeepSeekAdapter(api_key='test-only').model,'deepseek-flash')
        with patch.dict(os.environ,{'DEEPSEEK_MODEL':'configured-model'},clear=True):
            self.assertEqual(DeepSeekAdapter(api_key='test-only').model,'configured-model')

    def test_timeout_maps_to_retryable_unavailable(self):
        adapter=DeepSeekAdapter(api_key='test-only')
        with patch('chain_eye.adapters.deepseek.httpx.post',side_effect=TimeoutError()):
            with self.assertRaises(ModelUnavailable) as caught:self.generate(adapter)
        self.assertTrue(caught.exception.retryable)

    def test_429_maps_to_rate_limit(self):
        adapter=DeepSeekAdapter(api_key='test-only')
        with patch('chain_eye.adapters.deepseek.httpx.post',return_value=self.Response(429)):
            with self.assertRaises(ModelRateLimited):self.generate(adapter)

    def test_invalid_json_is_rejected(self):
        adapter=DeepSeekAdapter(api_key='test-only')
        response=self.Response(200,{'choices':[{'message':{'content':'not-json'}}]})
        with patch('chain_eye.adapters.deepseek.httpx.post',return_value=response):
            with self.assertRaises(ModelInvalidResponse):self.generate(adapter)

    def test_empty_claim_list_is_rejected(self):
        adapter=DeepSeekAdapter(api_key='test-only')
        response=self.Response(200,{'id':'req-1','model':'deepseek-flash','choices':[{'message':{'content':'{"claims":[]}'}}]})
        with patch('chain_eye.adapters.deepseek.httpx.post',return_value=response):
            with self.assertRaises(ModelInvalidResponse):self.generate(adapter)

    def test_response_records_provider_metadata(self):
        adapter=DeepSeekAdapter(api_key='test-only')
        claim={'id':'c','kind':'fact','text':'x','evidence_ids':[],'calculation_ids':[],'assumption_ids':[],'counter_evidence_ids':[],'limitations':[],'review_status':'pending'}
        response=self.Response(200,{'id':'req-1','model':'deepseek-flash','usage':{'total_tokens':3},'choices':[{'message':{'content':json.dumps({'claims':[claim]})}}]})
        with patch('chain_eye.adapters.deepseek.httpx.post',return_value=response) as posted:result=self.generate(adapter)
        self.assertEqual(result.request_id,'req-1');self.assertGreaterEqual(result.latency_ms,0);self.assertEqual(result.usage['total_tokens'],3)
        payload=posted.call_args.kwargs['json'];self.assertEqual(payload['max_tokens'],100);self.assertEqual(payload['model'],'deepseek-flash')
        self.assertIn('JSON Schema',payload['messages'][0]['content'])

    def test_api_key_is_not_in_public_configuration(self):
        adapter=DeepSeekAdapter(api_key='do-not-persist')
        self.assertNotIn('do-not-persist',str(adapter.public_config))
