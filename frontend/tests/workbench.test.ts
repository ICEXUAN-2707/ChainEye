import test from 'node:test';
import assert from 'node:assert/strict';
import type {CapabilityCollection,Dataset,FactCollection,IdentityCandidate,IdentityCandidateCollection} from '../src/api/generated.ts';
import {candidateMatchesDataset,hasIdentityBlocker,loadWorkbenchSnapshot,snapshotKey} from '../src/lib/workbench.ts';

function dataset(id='dataset-a',version=3):Dataset{return {id,name:'EVE 2025',company:'EVE',year:2025,version,source_ids:[],created_at:'2026-10-15T00:00:00Z',data_basis:'user_uploaded',company_id:'eve-energy',company_profile_version:1,industry_profile_id:'battery-manufacturing-cn-v1',industry_profile_version:2,report_type:'annual_report',identity_status:'confirmed',identity_confirmation_reason:'人工核对'};}
function candidate(values:Partial<IdentityCandidate>={}):IdentityCandidate{return {source_id:'source-1',company_id:'eve-energy',company_code:'EVE',legal_name:'惠州亿纬锂能股份有限公司',report_year:2025,report_type:'annual_report',status:'identified',evidence_pages:[1],warnings:[],...values};}

const facts:FactCollection={dataset_id:'dataset-a',dataset_version:3,items:[]};
const candidates:IdentityCandidateCollection={dataset_id:'dataset-a',dataset_version:3,items:[candidate()]};
const capabilities:CapabilityCollection={dataset_id:'dataset-a',dataset_version:3,company_id:'eve-energy',industry_profile_id:'battery-manufacturing-cn-v1',industry_profile_version:2,items:[]};

test('snapshot loader binds facts, candidates and capabilities to the exact version',async()=>{
  const target=dataset();const controller=new AbortController();const calls:string[]=[];
  const result=await loadWorkbenchSnapshot(target,4,controller.signal,()=>({key:snapshotKey(target),requestId:4}),{
    facts:async(id,version,signal)=>{calls.push(`facts:${id}:${version}:${signal===controller.signal}`);return facts;},
    candidates:async(id,version,signal)=>{calls.push(`candidates:${id}:${version}:${signal===controller.signal}`);return candidates;},
    capabilities:async(id,version,profileVersion,signal)=>{calls.push(`capabilities:${id}:${version}:${profileVersion}:${signal===controller.signal}`);return capabilities;},
  });
  assert.equal(result.status,'loaded');
  assert.deepEqual(calls.sort(),['candidates:dataset-a:3:true','capabilities:dataset-a:3:2:true','facts:dataset-a:3:true']);
});

test('late Dataset A response cannot overwrite Dataset B',async()=>{
  const target=dataset('dataset-a');let release!:()=>void;const wait=new Promise<void>(resolve=>{release=resolve;});
  let current={key:snapshotKey(target),requestId:1};
  const request=loadWorkbenchSnapshot(target,1,new AbortController().signal,()=>current,{
    facts:async()=>{await wait;return facts;},candidates:async()=>{await wait;return candidates;},capabilities:async()=>{await wait;return capabilities;},
  });
  current={key:snapshotKey(dataset('dataset-b')),requestId:2};release();
  assert.deepEqual(await request,{status:'stale'});
});

test('an older refresh of the same snapshot cannot overwrite a newer request',async()=>{
  const target=dataset();let release!:()=>void;const wait=new Promise<void>(resolve=>{release=resolve;});
  let current={key:snapshotKey(target),requestId:1};
  const request=loadWorkbenchSnapshot(target,1,new AbortController().signal,()=>current,{
    facts:async()=>{await wait;return facts;},candidates:async()=>{await wait;return candidates;},capabilities:async()=>{await wait;return capabilities;},
  });
  current={key:snapshotKey(target),requestId:2};release();
  assert.deepEqual(await request,{status:'stale'});
});

test('an aborted snapshot request is stale even if all transports resolve',async()=>{
  const target=dataset();const controller=new AbortController();controller.abort();
  const result=await loadWorkbenchSnapshot(target,1,controller.signal,()=>({key:snapshotKey(target),requestId:1}),{
    facts:async()=>facts,candidates:async()=>candidates,capabilities:async()=>capabilities,
  });
  assert.deepEqual(result,{status:'stale'});
});

test('identity gate blocks unconfirmed, conflict, ambiguous and mismatched company candidates',()=>{
  const confirmed=dataset();
  assert.equal(hasIdentityBlocker(confirmed,[candidate()]),false);
  assert.equal(hasIdentityBlocker({...confirmed,identity_status:'unconfirmed'},[candidate()]),true);
  assert.equal(hasIdentityBlocker(confirmed,[candidate({status:'conflict'})]),true);
  assert.equal(hasIdentityBlocker(confirmed,[candidate({status:'ambiguous'})]),true);
  const foreign=candidate({company_id:'catl',company_code:'CATL',legal_name:'宁德时代新能源科技股份有限公司'});
  assert.equal(candidateMatchesDataset(foreign,confirmed),false);
  assert.equal(hasIdentityBlocker(confirmed,[foreign]),true);
});
