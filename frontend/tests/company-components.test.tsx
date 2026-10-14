import test from 'node:test';
import assert from 'node:assert/strict';
import {renderToStaticMarkup} from 'react-dom/server';
import type {CapabilityCollection,CompanyProfile,Dataset,IdentityCandidate} from '../src/api/generated.ts';
import {DatasetPanel} from '../src/components/DatasetPanel.tsx';
import {IdentityPanel} from '../src/components/IdentityPanel.tsx';
import {CapabilityMatrix} from '../src/components/CapabilityMatrix.tsx';

const company:CompanyProfile={id:'eve-energy',company_code:'EVE',legal_name:'惠州亿纬锂能股份有限公司',aliases:['亿纬锂能'],security_ids:[],industry_profile_id:'battery-manufacturing-cn-v1',industry_profile_version:1,profile_version:1,supported_report_years:[2024,2025],report_name_patterns:[],segment_aliases:{},source_policy:'official_public_disclosure_attribution_required'};
const dataset:Dataset={id:'dataset-1',name:'EVE 2025',company:'EVE',year:2025,version:3,source_ids:['source-1'],created_at:'2026-10-15T00:00:00Z',data_basis:'user_uploaded',company_id:'eve-energy',company_profile_version:1,industry_profile_id:'battery-manufacturing-cn-v1',industry_profile_version:1,report_type:'annual_report',identity_status:'conflict',identity_confirmation_reason:null};
const conflict:IdentityCandidate={source_id:'source-1',company_id:'catl',company_code:'CATL',legal_name:'宁德时代新能源科技股份有限公司',report_year:2025,report_type:'annual_report',status:'conflict',evidence_pages:[1,3],warnings:['company_mismatch']};
const capabilities:CapabilityCollection={dataset_id:'dataset-1',dataset_version:3,company_id:'eve-energy',industry_profile_id:'battery-manufacturing-cn-v1',industry_profile_version:1,items:[{module_id:'M1',status:'failed',reason_code:'IDENTITY_CONFLICT',required_inputs:['revenue'],missing_inputs:['revenue'],evidence_gaps:['请先确认企业身份'],supported_actions:['confirm_identity']}]};

test('Dataset component renders creation fields from company profiles',()=>{
  const html=renderToStaticMarkup(<DatasetPanel datasets={[dataset]} companies={[company]} selectedId={dataset.id} creating={false} onSelect={()=>{}} onCreate={async()=>{}}/>);
  assert.match(html,/创建 Dataset/);assert.match(html,/惠州亿纬锂能股份有限公司/);assert.match(html,/2024/);assert.match(html,/2025/);
});

test('identity component exposes conflict evidence and the manual confirmation action',()=>{
  const html=renderToStaticMarkup(<IdentityPanel dataset={dataset} candidates={[conflict]} companies={[company]} loading={false} onConfirm={async()=>dataset} onRefresh={async()=>{}}/>);
  assert.match(html,/企业身份尚未闭合/);assert.match(html,/宁德时代新能源科技股份有限公司/);assert.match(html,/证据页：1、3/);assert.match(html,/company_mismatch/);assert.match(html,/确认身份并发布新版本/);
});

test('capability component renders module status, reason, evidence gap and supported action',()=>{
  const html=renderToStaticMarkup(<CapabilityMatrix capabilities={capabilities} loading={false}/>);
  assert.match(html,/M1 · 盈利增长/);assert.match(html,/IDENTITY_CONFLICT/);assert.match(html,/revenue/);assert.match(html,/请先确认企业身份/);assert.match(html,/confirm_identity/);
});
