import test from 'node:test';
import assert from 'node:assert/strict';
import type {Fact} from '../src/api/generated.ts';
import {buildFactCorrection,canSubmitReview,isDecimalValue,normalizedValueFromRaw,rawValueFromNormalized} from '../src/lib/review.ts';

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
  assert.equal(canSubmitReview({busy:false,status:'missing',value:'',missingReason:'',reason:'manual review',evidenceCount:1,evidenceReady:true,valuesValid:true}),false);
  assert.equal(canSubmitReview({busy:false,status:'missing',value:'',missingReason:'not disclosed',reason:'manual review',evidenceCount:1,evidenceReady:true,valuesValid:true}),true);
});

test('verified correction waits for loaded evidence',()=>{
  const input={busy:false,status:'verified' as const,value:'1000000',missingReason:'',reason:'manual review',evidenceCount:1,evidenceReady:false,valuesValid:true};
  assert.equal(canSubmitReview(input),false);
  assert.equal(canSubmitReview({...input,evidenceReady:true}),true);
  assert.equal(canSubmitReview({...input,evidenceCount:0,evidenceReady:true}),false);
});

test('correction blocks invalid decimal text before calling the API',()=>{
  assert.equal(isDecimalValue('900719925474099312345678.9'),true);
  assert.equal(isDecimalValue('-0.005'),true);
  assert.equal(isDecimalValue('1e3'),false);
  assert.equal(isDecimalValue('1,000'),false);
  assert.equal(isDecimalValue('01'),false);
  assert.equal(canSubmitReview({busy:false,status:'verified',value:'1000',missingReason:'',reason:'manual review',evidenceCount:1,evidenceReady:true,valuesValid:false}),false);
});

test('CNY_yuan correction round trip never scales the amount',()=>{
  const yuanFact={...fact,company:'EVE',value:'900719925474099312345678.9',raw_value:'900719925474099312345678.9',raw_unit:'CNY_yuan'} as Fact;
  assert.equal(rawValueFromNormalized(yuanFact.value??'',yuanFact.raw_unit),yuanFact.raw_value);
  assert.equal(normalizedValueFromRaw(yuanFact.raw_value??'',yuanFact.raw_unit),yuanFact.value);
  assert.equal(buildFactCorrection(yuanFact,'verified',yuanFact.value??'','','','checked against source').raw_value,yuanFact.raw_value);
});

test('thousand and percent correction conversions remain exact',()=>{
  assert.equal(rawValueFromNormalized('316506370000','CNY_thousand'),'316506370');
  assert.equal(normalizedValueFromRaw('316506370','CNY_thousand'),'316506370000');
  assert.equal(rawValueFromNormalized('900719925474099312345678.9','CNY_thousand'),'900719925474099312345.6789');
  assert.equal(normalizedValueFromRaw('0.0005','CNY_thousand'),'0.5');
  assert.equal(rawValueFromNormalized('0.2385','percent'),'23.85');
  assert.equal(normalizedValueFromRaw('23.85','percent'),'0.2385');
  assert.equal(rawValueFromNormalized('-0.005','percent'),'-0.5');
  assert.equal(normalizedValueFromRaw('-0.5','percent'),'-0.005');
  assert.equal(rawValueFromNormalized('1e3','CNY_yuan'),null);
  assert.equal(normalizedValueFromRaw('01','CNY_yuan'),null);
});
