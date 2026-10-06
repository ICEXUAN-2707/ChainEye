import json
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import fitz
from fastapi.testclient import TestClient

from chain_eye.adapters.sqlite import SQLiteRepository
from chain_eye.api.app import create_app
from chain_eye.api.dto import RunCreate
from chain_eye.application.errors import AppError
from chain_eye.application.reports import ReportService
from chain_eye.application.runs import RunExecutionService
from chain_eye.ports.services import LLMResponse
from chain_eye.reporting.markdown import _external_link


ROOT=Path(__file__).resolve().parents[1]


class ReportLLM:
    provider='fake';model='fake-r5'
    public_config={'provider':'fake','model':'fake-r5','response_format':'json_object'}

    def generate(self,task_name,prompt_version,messages,response_schema,budget):
        context=json.loads(messages[-1]['content'])['context']
        calculation=next(item for item in context['calculations'] if item and item.get('value') is not None)
        claim={
            'id':'report-claim','kind':'calculation',
            'text':f"计算结果为 {calculation['value']}。",
            'evidence_ids':context['allowed_evidence_ids'][:1],
            'calculation_ids':[calculation['id']],
            'assumption_ids':[],'counter_evidence_ids':[],
            'limitations':['仅基于绑定的数据快照'],'review_status':'pending',
        }
        return LLMResponse({'claims':[claim]},self.provider,self.model,{'total_tokens':10},1,'r5-request',None)


class R5Reports(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'db.sqlite'
        self.repo=SQLiteRepository(self.db,ROOT,Path(self.tmp.name)/'sources');self.repo.seed()

    def tearDown(self):self.tmp.cleanup()

    @staticmethod
    def request():
        return RunCreate(
            dataset_id='demo-catl-2025',dataset_version=1,
            question='分析动力电池收入和毛利',segment='power_battery',mode='live',
        )

    def execute(self,key='r5-report',request=None):
        service=RunExecutionService(self.repo,ReportLLM())
        run,_=service.create_with_status(request or self.request(),key)
        self.assertEqual(self.repo.claim_next_run(),run.id);service.execute(run.id)
        return run.id

    def test_completed_run_persists_one_traceable_report_and_event(self):
        run_id=self.execute();run=self.repo.get_run(run_id);report=self.repo.get_report(run_id)
        self.assertEqual(run.status,'completed');self.assertTrue(run.report_ready);self.assertEqual(run.current_node,'report')
        self.assertIsNotNone(report);self.assertEqual(report.run_id,run_id);self.assertTrue(report.claims)
        facts={(item.id,item.revision) for item in report.facts}
        calculation_ids={item.id for item in report.calculations};evidence_ids={item.id for item in report.evidence}
        assumption_ids={item.id for item in report.assumptions}
        for calculation in report.calculations:
            self.assertTrue(set(zip(calculation.input_fact_ids,(calculation.input_revisions[item] for item in calculation.input_fact_ids)))<=facts)
        for claim in report.claims:
            self.assertTrue(set(claim.evidence_ids+claim.counter_evidence_ids)<=evidence_ids)
            self.assertTrue(set(claim.calculation_ids)<=calculation_ids);self.assertTrue(set(claim.assumption_ids)<=assumption_ids)
        first=ReportService(self.repo).get_or_build(run_id);second=ReportService(self.repo).get_or_build(run_id)
        self.assertEqual(first,second)
        events,_,_=self.repo.list_run_events(run_id,0,200)
        generated=[item for item in events if item.type=='report_generated']
        self.assertEqual(len(generated),1);self.assertEqual(generated[0].payload['formats'],['json','markdown','pdf'])

    def test_non_completed_run_has_no_report(self):
        service=RunExecutionService(self.repo,ReportLLM());run,_=service.create_with_status(self.request(),'queued-report')
        with self.assertRaises(AppError) as caught:ReportService(self.repo).get_or_build(run.id)
        self.assertEqual(caught.exception.code,'REPORT_NOT_READY');self.assertEqual(caught.exception.status,409)

    def test_markdown_external_links_only_allow_http_schemes(self):
        self.assertEqual(_external_link('javascript:alert(1)'),'原文链接不可用')
        self.assertIn('https://example.com/',_external_link('https://example.com/report?q=1'))

    def test_scenario_report_contains_assumption_and_exact_calculations(self):
        request=RunCreate.model_validate({
            **self.request().model_dump(mode='json'),'question':'分析原材料价格变化对毛利的影响',
            'assumptions':{
                'cost_exposure':'0.1','effective_price_shock':'-0.2',
                'customer_pass_through':'0.5','basis':'user_assumption','acknowledged':True,
            },
        })
        run_id=self.execute('scenario-report',request);report=self.repo.get_report(run_id)
        self.assertEqual(len(report.scenarios),1);self.assertEqual(len(report.assumptions),1)
        scenario=report.scenarios[0]
        self.assertEqual(report.assumptions[0].id,scenario.assumption_id)
        self.assertEqual(set(scenario.calculation_ids),{item.id for item in report.calculations[-9:]})
        self.assertTrue(any(scenario.assumption_id in item.assumption_ids for item in report.claims))

    def test_replay_report_uses_artifact_segment_even_if_request_label_differs(self):
        source_id=self.execute('replay-source')
        service=RunExecutionService(self.repo,ReportLLM())
        replay=RunCreate.model_validate({
            **self.request().model_dump(mode='json'),'question':'回放既有结果',
            'segment':'energy_storage','mode':'replay','replay_run_id':source_id,
        })
        run,_=service.create_with_status(replay,'replay-report');self.repo.claim_next_run();service.execute(run.id)
        report=self.repo.get_report(run.id)
        self.assertEqual(report.mode,'replay');self.assertIn('动力电池研究简报',report.title)
        self.assertTrue(any('回放 Run' in item for item in report.limitations))

    def test_insufficient_and_rejected_claims_are_excluded_and_disclosed(self):
        run_id=self.execute('excluded-claims');record=self.repo.get_run_record(run_id)
        with self.repo.connect() as db:
            db.execute('DELETE FROM reports WHERE run_id=?',(run_id,))
            db.execute("DELETE FROM run_events WHERE run_id=? AND body LIKE '%report_generated%'",(run_id,))
        insufficient={**record['claims'][0],'id':'insufficient','review_status':'insufficient'}
        rejected={**record['claims'][0],'id':'rejected','review_status':'rejected'}
        self.repo.update_run(run_id,claims=[record['claims'][0],insufficient,rejected],report_ready=False,current_node='verify')
        report=ReportService(self.repo).get_or_build(run_id)
        self.assertEqual([item.id for item in report.claims],['report-claim'])
        self.assertTrue(any('排除 1 条证据不足' in item for item in report.limitations))
        self.assertTrue(any('排除 1 条引用不合法' in item for item in report.limitations))

    def test_tampered_claim_reference_is_rejected_without_persisting(self):
        run_id=self.execute('tampered-report')
        with self.repo.connect() as db:
            db.execute('DELETE FROM reports WHERE run_id=?',(run_id,))
            db.execute("DELETE FROM run_events WHERE run_id=? AND body LIKE '%report_generated%'",(run_id,))
        record=self.repo.get_run_record(run_id);record['claims'][0]['evidence_ids']=['not-in-snapshot']
        self.repo.update_run(run_id,claims=record['claims'],report_ready=False,current_node='verify')
        with self.assertRaises(AppError) as caught:ReportService(self.repo).get_or_build(run_id)
        self.assertEqual(caught.exception.code,'REPORT_INVALID_REFERENCE');self.assertIsNone(self.repo.get_report(run_id))

    def test_corrupt_artifact_contract_and_scenario_fact_set_are_rejected(self):
        run_id=self.execute('corrupt-calculation');record=self.repo.get_run_record(run_id)
        calculation_id=record['calculation_ids'][0]
        calculation=self.repo.get('calculations',calculation_id);calculation.pop('formula_version')
        with self.repo.connect() as db:
            db.execute('DELETE FROM reports WHERE run_id=?',(run_id,))
            db.execute('UPDATE calculations SET body=? WHERE id=?',(json.dumps(calculation),calculation_id))
        with self.assertRaises(AppError) as caught:ReportService(self.repo).get_or_build(run_id)
        self.assertEqual(caught.exception.details['kind'],'calculation_contract')

        request=RunCreate.model_validate({
            **self.request().model_dump(mode='json'),'question':'分析原材料价格变化对毛利的影响',
            'assumptions':{
                'cost_exposure':'0.1','effective_price_shock':'-0.2',
                'customer_pass_through':'0.5','basis':'user_assumption','acknowledged':True,
            },
        })
        scenario_run=self.execute('corrupt-scenario',request);scenario_record=self.repo.get_run_record(scenario_run)
        scenario_id=scenario_record['scenario_ids'][0];scenario=self.repo.get('scenarios',scenario_id)
        scenario['input_revisions'].pop(scenario['cost_fact_id'])
        with self.repo.connect() as db:
            db.execute('DELETE FROM reports WHERE run_id=?',(scenario_run,))
            db.execute('UPDATE scenarios SET body=? WHERE id=?',(json.dumps(scenario),scenario_id))
        with self.assertRaises(AppError) as caught:ReportService(self.repo).get_or_build(scenario_run)
        self.assertEqual(caught.exception.details['kind'],'scenario_fact_set')

    def test_concurrent_lazy_build_is_idempotent(self):
        run_id=self.execute('concurrent-report')
        with self.repo.connect() as db:
            db.execute('DELETE FROM reports WHERE run_id=?',(run_id,))
            db.execute("DELETE FROM run_events WHERE run_id=? AND body LIKE '%report_generated%'",(run_id,))
        with ThreadPoolExecutor(max_workers=6) as pool:
            reports=list(pool.map(lambda _:ReportService(self.repo).get_or_build(run_id),range(12)))
        self.assertEqual(len({item.generated_at for item in reports}),1)
        events,_,_=self.repo.list_run_events(run_id,0,200)
        self.assertEqual(sum(item.type=='report_generated' for item in events),1)

    def test_interrupted_report_node_is_recovered_idempotently(self):
        service=RunExecutionService(self.repo,ReportLLM());run,_=service.create_with_status(self.request(),'report-recovery')
        self.repo.claim_next_run()
        with patch.object(service.reports,'complete',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):service.execute(run.id)
        interrupted=self.repo.get_run_record(run.id)
        self.assertEqual(interrupted['status'],'running');self.assertEqual(interrupted['current_node'],'report')
        self.assertEqual(self.repo.recover_interrupted_runs(),[run.id]);self.assertEqual(self.repo.claim_next_run(),run.id)
        RunExecutionService(self.repo,ReportLLM()).execute(run.id)
        recovered=self.repo.get_run(run.id)
        self.assertEqual(recovered.status,'completed');self.assertTrue(recovered.report_ready)
        events,_,_=self.repo.list_run_events(run.id,0,200)
        self.assertEqual(sum(item.type=='report_generated' for item in events),1)


class R5ReportHTTP(unittest.TestCase):
    def test_json_markdown_and_pdf_share_one_persisted_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=create_app(Path(tmp)/'db.sqlite',upload_dir=Path(tmp)/'sources',llm=ReportLLM())
            with TestClient(app,base_url='http://localhost',client=('127.0.0.1',50000)) as client:
                body={
                    'dataset_id':'demo-catl-2025','dataset_version':1,
                    'question':'分析动力电池收入和毛利','segment':'power_battery','mode':'live',
                }
                created=client.post('/api/v1/runs',json=body,headers={'Idempotency-Key':'r5-http-report'})
                self.assertEqual(created.status_code,202);run_id=created.json()['id']
                for _ in range(200):
                    run=client.get(f'/api/v1/runs/{run_id}').json()
                    if run['status'] not in ('queued','running'):break
                    time.sleep(0.01)
                self.assertEqual(run['status'],'completed');self.assertTrue(run['report_ready'])

                json_response=client.get(f'/api/v1/runs/{run_id}/report?format=json')
                markdown=client.get(f'/api/v1/runs/{run_id}/report?format=markdown')
                pdf=client.get(f'/api/v1/runs/{run_id}/report?format=pdf')
                self.assertEqual(json_response.status_code,200);self.assertEqual(json_response.json()['run_id'],run_id)
                self.assertTrue(markdown.headers['content-type'].startswith('text/markdown'))
                self.assertIn(f'chain-eye-{run_id}.md',markdown.headers['content-disposition'])
                self.assertIn(f'Run：`{run_id}`',markdown.text);self.assertIn('/api/v1/evidence/',markdown.text)
                self.assertEqual(pdf.headers['content-type'],'application/pdf');self.assertTrue(pdf.content.startswith(b'%PDF-'))
                self.assertIn(f'chain-eye-{run_id}.pdf',pdf.headers['content-disposition'])
                with fitz.open(stream=pdf.content,filetype='pdf') as document:
                    self.assertGreaterEqual(document.page_count,1)
                    text=''.join(page.get_text() for page in document)
                    self.assertIn(run_id,text);self.assertIn('限制与风险边界',text)
                repeated=client.get(f'/api/v1/runs/{run_id}/report').json()
                self.assertEqual(repeated['generated_at'],json_response.json()['generated_at'])


if __name__=='__main__':unittest.main()
