import test from 'node:test';
import assert from 'node:assert/strict';
import type {Dataset,Event,RunCreate} from '../src/api/generated.ts';
import {buildRunCreate,claimsFromEvents,isRunActive,mergeEvents,runIdempotencyKey,reportExportUrl} from '../src/lib/run.ts';

const dataset:Dataset={id:'dataset-1',name:'test',company:'CATL',year:2025,version:3,source_ids:[],created_at:'2026-10-04T00:00:00Z',data_basis:'reviewed_fixture'};

function event(seq:number,payload:Record<string,unknown>={}):Event{return {seq,run_id:'run-1',type:'node_status',node:'verify',at:'2026-10-04T00:00:00Z',payload};}

test('live request omits hidden replay id and uses the exact request identity',()=>{
  const first=buildRunCreate(dataset,'  question  ','power_battery','live','hidden-old-id');
  const second=buildRunCreate(dataset,'question','power_battery','live','different-hidden-id');
  assert.deepEqual(first,{dataset_id:'dataset-1',dataset_version:3,question:'question',segment:'power_battery',mode:'live'});
  assert.equal(runIdempotencyKey(first),runIdempotencyKey(second));
});

test('replay request and idempotency key include replay source',()=>{
  const first=buildRunCreate(dataset,'question','power_battery','replay',' source-1 ');
  const second=buildRunCreate(dataset,'question','power_battery','replay','source-2');
  assert.equal(first.replay_run_id,'source-1');assert.notEqual(runIdempotencyKey(first),runIdempotencyKey(second));
});

test('run key varies with every request field including assumptions',()=>{
  const base:RunCreate={dataset_id:'d',dataset_version:1,question:'q',segment:'power_battery',mode:'live'};
  const variants:RunCreate[]=[
    {...base,dataset_id:'d2'},{...base,dataset_version:2},{...base,question:'q2'},{...base,segment:'energy_storage'},
    {dataset_id:'d',dataset_version:1,question:'q',segment:'power_battery',mode:'replay',replay_run_id:'r'},
    {...base,assumptions:{cost_exposure:'0.1',effective_price_shock:'-0.2',customer_pass_through:'0.5',basis:'user_assumption',acknowledged:true}},
  ];
  for(const variant of variants)assert.notEqual(runIdempotencyKey(base),runIdempotencyKey(variant));
});

test('incremental events merge by seq without duplicates and stay ordered',()=>{
  assert.deepEqual(mergeEvents([event(1),event(3)],[event(2),event(3)]).map(item=>item.seq),[1,2,3]);
});

test('claims are read only from structurally valid event payloads',()=>{
  const claim={id:'c1',kind:'calculation',text:'value 1',evidence_ids:['e1'],calculation_ids:['x1'],assumption_ids:[],counter_evidence_ids:[],limitations:[],review_status:'supported'};
  const claims=claimsFromEvents([event(1,{claims:[{bad:true}]}),event(2,{claims:[claim]})]);
  assert.deepEqual(claims,[claim]);
});

test('only queued and running states are auto-polled',()=>{
  assert.equal(isRunActive('queued'),true);assert.equal(isRunActive('running'),true);
  for(const status of ['waiting_review','completed','partial','failed','cancelled'] as const)assert.equal(isRunActive(status),false);
});

test('report export URL encodes run id and keeps correct format',()=>{
  assert.equal(reportExportUrl('run 1/2','markdown'),'/api/v1/runs/run%201%2F2/report?format=markdown');
  assert.equal(reportExportUrl('abc','pdf'),'/api/v1/runs/abc/report?format=pdf');
});
