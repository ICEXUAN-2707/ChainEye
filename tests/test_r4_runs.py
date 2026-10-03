import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from chain_eye.adapters.deepseek import ClaimGeneration,DeepSeekAdapter,ModelInvalidResponse,ModelRateLimited,ModelUnavailable
from chain_eye.adapters.sqlite import SQLiteRepository
from chain_eye.api.app import create_app
from chain_eye.api.dto import RunCreate
from chain_eye.application.errors import AppError
from chain_eye.application.run_tools import RunTools,TOOL_NAMES,ToolFailure
from chain_eye.application.runs import RunExecutionService

ROOT=Path(__file__).resolve().parents[1]


class FakeLLM:
    provider='fake';model='fake-r4'
    public_config={'provider':'fake','model':'fake-r4','response_format':'json_object'}
    def __init__(self,failures=None,unsupported=False):
        self.failures=list(failures or []);self.unsupported=unsupported;self.calls=[]
    def generate_claims(self,question,context):
        self.calls.append((question,context))
        if self.failures:raise self.failures.pop(0)
        evidence=context['allowed_evidence_ids'][:1];calculations=context['allowed_calculation_ids'][:1]
        claim={
            'id':f'claim-{len(self.calls)}','kind':'calculation','text':'毛利计算结果为 1。',
            'evidence_ids':[] if self.unsupported else evidence,
            'calculation_ids':[] if self.unsupported else calculations,'assumption_ids':[],
            'counter_evidence_ids':[],'limitations':['仅基于绑定的数据快照'],'review_status':'pending',
        }
        return ClaimGeneration([claim],self.provider,self.model,{'total_tokens':10})


class InvalidLLM(FakeLLM):
    def generate_claims(self,question,context):
        self.calls.append((question,context));raise ModelInvalidResponse('bad json')


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
        _,run,record=self.execute()
        self.assertEqual(run.status,'completed');self.assertFalse(run.report_ready);self.assertEqual(run.current_node,'verify')
        self.assertEqual(len(record['calculation_ids']),6);self.assertEqual(record['claims'][0]['review_status'],'pending')
        events,after,more=self.repo.list_run_events(run.id,0,200)
        self.assertEqual([event.seq for event in events],list(range(1,len(events)+1)));self.assertEqual(after,len(events));self.assertFalse(more)
        tools={event.payload['tool_name'] for event in events if event.type=='tool_call'}
        self.assertEqual(tools,TOOL_NAMES-{'compute_scenario'})
        self.assertTrue(all(event.payload.get('input_sha256') for event in events if event.type=='tool_call'))

    def test_numeric_claim_without_references_is_downgraded(self):
        _,run,record=self.execute(FakeLLM(unsupported=True))
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
        resume=ResumeRequest.model_validate({'expected_run_status':'waiting_review','dataset_version':1,'assumptions':{'cost_exposure':'0.1','effective_price_shock':'-0.2','customer_pass_through':'0.5','basis':'user_assumption','acknowledged':True}})
        service.resume(run.id,resume);self.repo.claim_next_run();service.execute(run.id)
        record=self.repo.get_run_record(run.id);self.assertEqual(record['status'],'completed');self.assertEqual(len(record['scenario_ids']),1);self.assertEqual(len(record['calculation_ids']),15)

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
                report=client.get(f'/api/v1/runs/{run_id}/report');self.assertEqual(report.status_code,501);self.assertEqual(report.json()['error']['code'],'NOT_IMPLEMENTED')


class DeepSeekBoundary(unittest.TestCase):
    class Response:
        def __init__(self,status_code,body=None):self.status_code=status_code;self.body=body
        def json(self):return self.body

    def test_timeout_maps_to_retryable_unavailable(self):
        adapter=DeepSeekAdapter(api_key='test-only')
        with patch('chain_eye.adapters.deepseek.httpx.post',side_effect=TimeoutError()):
            with self.assertRaises(ModelUnavailable) as caught:adapter.generate_claims('q',{})
        self.assertTrue(caught.exception.retryable)

    def test_429_maps_to_rate_limit(self):
        adapter=DeepSeekAdapter(api_key='test-only')
        with patch('chain_eye.adapters.deepseek.httpx.post',return_value=self.Response(429)):
            with self.assertRaises(ModelRateLimited):adapter.generate_claims('q',{})

    def test_invalid_json_is_rejected(self):
        adapter=DeepSeekAdapter(api_key='test-only')
        response=self.Response(200,{'choices':[{'message':{'content':'not-json'}}]})
        with patch('chain_eye.adapters.deepseek.httpx.post',return_value=response):
            with self.assertRaises(ModelInvalidResponse):adapter.generate_claims('q',{})

    def test_api_key_is_not_in_public_configuration(self):
        adapter=DeepSeekAdapter(api_key='do-not-persist')
        self.assertNotIn('do-not-persist',str(adapter.public_config))
