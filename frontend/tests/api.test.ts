import test from 'node:test';
import assert from 'node:assert/strict';
import {api,ApiError,BASE_URL} from '../src/api/client.ts';
import type {IdentityConfirmation} from '../src/api/generated.ts';

test('company identity API methods preserve snapshot parameters, request bodies and AbortSignal',async()=>{
  const originalFetch=globalThis.fetch;
  const calls:Array<{url:string;init:RequestInit}>=[];
  globalThis.fetch=async(input,init={})=>{
    calls.push({url:String(input),init});
    return new Response('{}',{status:200,headers:{'Content-Type':'application/json'}});
  };
  const controller=new AbortController();
  const confirmation:IdentityConfirmation={expected_version:7,company_id:'eve-energy',report_year:2025,report_type:'annual_report',reason:'人工核对'};
  try{
    await api.companies({offset:10,limit:20,signal:controller.signal});
    await api.identityCandidates('dataset / 1',7,controller.signal);
    await api.datasetCapabilities('dataset / 1',7,3,controller.signal);
    await api.confirmDatasetIdentity('dataset / 1',confirmation,controller.signal);
    await api.createDataset({name:'EVE 2025',company:'EVE',year:2025},controller.signal);
  }finally{globalThis.fetch=originalFetch;}

  assert.equal(calls[0].url,`${BASE_URL}/api/v1/companies?offset=10&limit=20`);
  assert.equal(calls[1].url,`${BASE_URL}/api/v1/datasets/dataset%20%2F%201/identity-candidates?version=7`);
  assert.equal(calls[2].url,`${BASE_URL}/api/v1/datasets/dataset%20%2F%201/capabilities?version=7&industry_profile_version=3`);
  assert.equal(calls[3].url,`${BASE_URL}/api/v1/datasets/dataset%20%2F%201/identity-confirmations`);
  assert.equal(calls[3].init.method,'POST');
  assert.deepEqual(JSON.parse(String(calls[3].init.body)),confirmation);
  assert.deepEqual(JSON.parse(String(calls[4].init.body)),{name:'EVE 2025',company:'EVE',year:2025});
  for(const call of calls)assert.equal(call.init.signal,controller.signal);
});

test('identity confirmation keeps structured 409 details for the refresh prompt',async()=>{
  const originalFetch=globalThis.fetch;
  globalThis.fetch=async()=>new Response(JSON.stringify({error:{code:'IDENTITY_CONFLICT',message:'数据包版本已变化',details:{current_version:8},retryable:false,request_id:'req-1'}}),{status:409,headers:{'Content-Type':'application/json'}});
  try{
    await assert.rejects(
      api.confirmDatasetIdentity('dataset-1',{expected_version:7,company_id:'eve-energy',report_year:2025,report_type:'annual_report',reason:'人工核对'}),
      (error:unknown)=>error instanceof ApiError&&error.status===409&&error.code==='IDENTITY_CONFLICT'&&error.details.current_version===8,
    );
  }finally{globalThis.fetch=originalFetch;}
});
