import test from 'node:test';
import assert from 'node:assert/strict';
import type {Fact} from '../src/api/generated.ts';
import {pairBaseline,stableKey,scenarioKey} from '../src/lib/scenario.ts';

function fact(id:string,metric:string,segment:string,periodEnd:string,status:string):Fact{
  return {
    id,revision:1,company:'CATL',metric,segment:segment as Fact['segment'],statement_scope:'consolidated',
    period_kind:'annual_flow',period_start:periodEnd.slice(0,4)+'-01-01',period_end:periodEnd,currency:'CNY',
    value:'100',unit:'CNY',raw_value:'0.1',raw_unit:'CNY_thousand',status:status as Fact['status'],
    evidence_ids:[],missing_reason:null,restatement_status:'not_restated',
  } as Fact;
}

test('pairBaseline pairs revenue+cost by same scope and orders latest first',()=>{
  const facts=[
    fact('r24','revenue','power_battery','2024-12-31','verified'),
    fact('c24','cost_of_sales','power_battery','2024-12-31','verified'),
    fact('r25','revenue','power_battery','2025-12-31','verified'),
    fact('c25','cost_of_sales','power_battery','2025-12-31','verified'),
  ];
  const pairs=pairBaseline(facts,'power_battery');
  assert.equal(pairs.length,2);
  assert.equal(pairs[0].periodEnd,'2025-12-31');
  assert.equal(pairs[0].revenue.id,'r25');
  assert.equal(pairs[0].cost.id,'c25');
});

test('pairBaseline does not pair mismatched years',()=>{
  const facts=[
    fact('r25','revenue','power_battery','2025-12-31','verified'),
    fact('c24','cost_of_sales','power_battery','2024-12-31','verified'),
  ];
  assert.equal(pairBaseline(facts,'power_battery').length,0);
});

test('pairBaseline only pairs verified revenue and cost',()=>{
  const facts=[
    fact('r25','revenue','power_battery','2025-12-31','verified'),
    fact('c25','cost_of_sales','power_battery','2025-12-31','needs_review'),
  ];
  assert.equal(pairBaseline(facts,'power_battery').length,0);
});

test('pairBaseline does not silently pair duplicate-scope facts',()=>{
  const facts=[
    fact('r25a','revenue','power_battery','2025-12-31','verified'),
    fact('r25b','revenue','power_battery','2025-12-31','verified'),
    fact('c25','cost_of_sales','power_battery','2025-12-31','verified'),
  ];
  assert.equal(pairBaseline(facts,'power_battery').length,0);
});

test('stableKey is deterministic and varies with input',()=>{
  assert.equal(stableKey('a|b|c'),stableKey('a|b|c'));
  assert.notEqual(stableKey('a|b|c'),stableKey('a|b|d'));
});

test('stableKey returns 8~128 chars (backend Idempotency-Key contract)',()=>{
  for(const input of ['','a','short','a longer input with many characters and symbols !@#']){
    const k=stableKey(input);
    assert.ok(k.length>=8&&k.length<=128,`key length ${k.length} out of range for "${input}"`);
  }
});

test('scenarioKey covers every variable request identity field',()=>{
  const base={dataset_id:'d',dataset_version:1,revenue_fact_id:'r',revenue_revision:1,cost_fact_id:'c',cost_revision:1,cost_exposure:'1',effective_price_shock:'-0.1',customer_pass_through:'0.5',basis:'research_assumption'};
  assert.equal(scenarioKey(base),scenarioKey(base));
  const variants=[
    {...base,dataset_id:'d2'},{...base,dataset_version:2},
    {...base,revenue_fact_id:'r2'},{...base,revenue_revision:2},
    {...base,cost_fact_id:'c2'},{...base,cost_revision:2},
    {...base,cost_exposure:'0.5'},{...base,effective_price_shock:'0.1'},
    {...base,customer_pass_through:'1'},{...base,basis:'user_assumption'},
  ];
  for(const variant of variants)assert.notEqual(scenarioKey(base),scenarioKey(variant));
});
