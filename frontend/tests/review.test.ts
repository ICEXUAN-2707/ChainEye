import test from 'node:test';
import assert from 'node:assert/strict';
import type {Fact} from '../src/api/generated.ts';
import {buildFactCorrection,canSubmitReview} from '../src/lib/review.ts';

const fact={
  id:'fact-1',revision:3,company:'CATL',metric:'revenue',segment:'power_battery',statement_scope:'consolidated',
  period_kind:'annual_flow',period_start:'2025-01-01',period_end:'2025-12-31',currency:'CNY',value:'1000000',unit:'CNY',
  raw_value:'1000',raw_unit:'CNY_thousand',status:'extracted',evidence_ids:['evidence-1'],missing_reason:null,restatement_status:'not_restated',
} as Fact;

test('missing correction always sends null values and a reason',()=>{
  assert.deepEqual(buildFactCorrection(fact,'missing','1000000','1000','not disclosed','manual review'),{
    expected_revision:3,value:null,raw_value:null,status:'missing',evidence_ids:['evidence-1'],reason:'manual review',missing_reason:'not disclosed',
  });
});

test('missing correction cannot submit without missing reason',()=>{
  assert.equal(canSubmitReview({busy:false,status:'missing',value:'',missingReason:'',reason:'manual review',evidenceCount:1,evidenceReady:true}),false);
  assert.equal(canSubmitReview({busy:false,status:'missing',value:'',missingReason:'not disclosed',reason:'manual review',evidenceCount:1,evidenceReady:true}),true);
});

test('verified correction waits for loaded evidence',()=>{
  const input={busy:false,status:'verified' as const,value:'1000000',missingReason:'',reason:'manual review',evidenceCount:1,evidenceReady:false};
  assert.equal(canSubmitReview(input),false);
  assert.equal(canSubmitReview({...input,evidenceReady:true}),true);
  assert.equal(canSubmitReview({...input,evidenceCount:0,evidenceReady:true}),false);
});
