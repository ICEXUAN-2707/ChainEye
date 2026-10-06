import test from 'node:test';
import assert from 'node:assert/strict';
import type {AssumptionRecord,Calculation,Claim,Evidence,Report,Run} from '../src/api/generated.ts';
import {ApiError,errorMessage} from '../src/api/client.ts';
import {calculationApiUrl,evidenceApiUrl,loadCurrentReport,reportExportUrl,reportRequestRunId,resolveClaimReferences,shouldAcceptReportResponse,sourcePageUrl} from '../src/lib/report.ts';

const evidence:Evidence={id:'e 1/2',source_id:'source 1/2',locator_kind:'pdf',pdf_page:12,excerpt:'收入证据',sha256:'0'.repeat(64)};
const counterEvidence:Evidence={id:'counter-1',source_id:'source-1',locator_kind:'pdf',pdf_page:13,excerpt:'反证',sha256:'1'.repeat(64)};
const calculation:Calculation={id:'calc 1/2',formula_id:'gross-margin',formula_version:'1',input_fact_ids:['fact-1'],input_revisions:{'fact-1':2},assumption_snapshot:{},value:'0.25',unit:'ratio',status:'computed'};
const assumption:AssumptionRecord={id:'assumption-1',values:{cost_exposure:'0.1',effective_price_shock:'-0.2',customer_pass_through:'0.5',basis:'user_assumption',acknowledged:true}};
const claim:Claim={id:'claim-1',kind:'inference',text:'结论',evidence_ids:[evidence.id,'missing-evidence'],calculation_ids:[calculation.id],assumption_ids:[assumption.id],counter_evidence_ids:[counterEvidence.id],limitations:['仅限当前快照'],review_status:'supported'};
const report:Report={run_id:'run-1',dataset_id:'dataset-1',dataset_version:3,mode:'live',title:'报告',facts:[],calculations:[calculation],claims:[claim],scenarios:[],assumptions:[assumption],evidence:[evidence,counterEvidence],limitations:[],generated_at:'2026-10-06T00:00:00Z'};

function run(reportReady:boolean,id='run-1'):Run{return {id,dataset_id:'dataset-1',dataset_version:3,status:reportReady?'completed':'running',mode:'live',current_node:'report',missing_requirements:[],stale:false,error:null,report_ready:reportReady};}

test('only a report-ready run produces a report request identity',()=>{
  assert.equal(reportRequestRunId(null),null);
  assert.equal(reportRequestRunId(run(false)),null);
  assert.equal(reportRequestRunId(run(true)),'run-1');
});

test('claim references preserve support, counter evidence, calculation and assumption identity',()=>{
  const references=resolveClaimReferences(report,claim);
  assert.deepEqual(references.evidence.map(item=>[item.id,item.value?.id??null]),[[evidence.id,evidence.id],['missing-evidence',null]]);
  assert.deepEqual(references.counterEvidence.map(item=>item.value?.id),[counterEvidence.id]);
  assert.deepEqual(references.calculations.map(item=>item.value?.id),[calculation.id]);
  assert.deepEqual(references.assumptions.map(item=>item.value?.id),[assumption.id]);
});

test('report and trace URLs encode external identifiers and retain the requested target',()=>{
  assert.equal(reportExportUrl('run 1/2','markdown'),'/api/v1/runs/run%201%2F2/report?format=markdown');
  assert.equal(reportExportUrl('abc','pdf'),'/api/v1/runs/abc/report?format=pdf');
  assert.equal(evidenceApiUrl(evidence.id),'/api/v1/evidence/e%201%2F2');
  assert.equal(calculationApiUrl(calculation.id),'/api/v1/calculations/calc%201%2F2');
  assert.equal(sourcePageUrl(evidence.source_id,evidence.pdf_page),'/api/v1/sources/source%201%2F2/content#page=12');
});

test('late or aborted report responses cannot replace the current run',()=>{
  assert.equal(shouldAcceptReportResponse('run-1','run-1',false),true);
  assert.equal(shouldAcceptReportResponse('run-1','run-2',false),false);
  assert.equal(shouldAcceptReportResponse('run-1','run-1',true),false);
});

test('report loader skips unready runs and rejects a late response after a run switch',async()=>{
  let calls=0;const controller=new AbortController();let current='run-1';
  const request=async()=>{calls+=1;current='run-2';return report;};
  assert.deepEqual(await loadCurrentReport(run(false),controller.signal,()=>current,request),{status:'idle'});
  assert.equal(calls,0);
  assert.deepEqual(await loadCurrentReport(run(true),controller.signal,()=>current,request),{status:'stale'});
  assert.equal(calls,1);
});

test('report loader exposes an error and allows the same current run to retry',async()=>{
  const controller=new AbortController();let calls=0;
  const request=async()=>{calls+=1;if(calls===1)throw new Error('temporary');return report;};
  const first=await loadCurrentReport(run(true),controller.signal,()=> 'run-1',request);
  assert.equal(first.status,'failed');
  const second=await loadCurrentReport(run(true),controller.signal,()=> 'run-1',request);
  assert.equal(second.status,'loaded');assert.equal(calls,2);
});

test('structured API errors remain visible with code and request id',()=>{
  const error=new ApiError(409,{error:{code:'REPORT_NOT_READY',message:'报告尚未就绪',details:{},retryable:true,request_id:'request-1'}});
  assert.equal(errorMessage(error),'报告尚未就绪（REPORT_NOT_READY，request-1）');
});
