import test from 'node:test';
import assert from 'node:assert/strict';
import type {Fact} from '../src/api/generated.ts';
import {diagnosticComparison,metricMatchesQuery} from '../src/lib/diagnostic.ts';
import {datasetLabel} from '../src/lib/format.ts';
import {shortcutView} from '../src/lib/navigation.ts';

function fact(id:string,year:number,value:string|null,overrides:Partial<Fact>={}):Fact{
  return {
    id,revision:1,company:'CATL',metric:'revenue',segment:'group',statement_scope:'consolidated',
    period_kind:'annual_flow',period_start:`${year}-01-01`,period_end:`${year}-12-31`,currency:'CNY',
    value,unit:'CNY',raw_value:value,raw_unit:'CNY_thousand',status:value===null?'missing':'verified',
    evidence_ids:value===null?[]:[`e-${id}`],missing_reason:value===null?'not disclosed':null,
    ...overrides,
  };
}

test('diagnostic comparison requires exactly one verified comparable fact per year',()=>{
  const facts=[fact('r24',2024,'100'),fact('r25',2025,'120')];
  assert.deepEqual(diagnosticComparison(facts,'group','revenue')?.direction,'up');
  assert.equal(diagnosticComparison([...facts,fact('duplicate',2025,'121')],'group','revenue'),null);
  assert.equal(diagnosticComparison([facts[0],fact('missing',2025,null)],'group','revenue'),null);
  assert.equal(diagnosticComparison([facts[0],fact('bad',2025,'NaN')],'group','revenue'),null);
});

test('diagnostic comparison rejects period and unit mismatches without treating zero as missing',()=>{
  const zero=[fact('r24',2024,'0'),fact('r25',2025,'1')];
  assert.equal(diagnosticComparison(zero,'group','revenue')?.direction,'up');
  assert.equal(diagnosticComparison([zero[0],fact('date',2025,'1',{period_end:'2025-06-30'})],'group','revenue'),null);
  assert.equal(diagnosticComparison([zero[0],fact('unit',2025,'1',{unit:'ratio'})],'group','revenue'),null);
});

test('diagnostic search, dataset identity and shortcuts preserve user context',()=>{
  assert.equal(metricMatchesQuery('营业收入',' 收入 '),true);
  assert.equal(metricMatchesQuery('营业收入','存货'),false);
  assert.equal(datasetLabel({id:'dataset-1',name:'复核包A',company:'CATL',year:2025}),'复核包A · 宁德时代 2025 年报 · dataset-1');
  assert.equal(shortcutView('2',false),'diagnostic');
  assert.equal(shortcutView('2',true),null);
  assert.equal(shortcutView('9',false),null);
});
