// 开发用 mock：仅当页面 URL 带 ?mock=1 时启用。
// 用于本地预览 R2 的上传与复核界面——真实后端的 uploadSource / correctFact 尚未合并到 main，会返回 501。
// 验收/联调必须去掉 ?mock=1 走真实后端；mock 结果不落库、不持久化，且绝不伪装成自动提取结果。
import type {SourceAttachment, Source, Dataset, Fact, FactCorrection} from './generated';

export const MOCK_ENABLED=new URLSearchParams(window.location.search).has('mock');

function sleep(ms:number){return new Promise<void>(r=>setTimeout(r,ms));}

export async function mockUploadSource(datasetId:string,file:File):Promise<SourceAttachment>{
  await sleep(400);
  const source:Source={
    id:`mock-src-${Math.random().toString(36).slice(2,10)}`,
    filename:file.name,
    sha256:'0'.repeat(64),
    media_type:'application/pdf',
    page_count:null,
    url:null,
    published_date:null,
    parse_status:'queued',
    data_basis:'user_uploaded',
  };
  const dataset:Dataset={
    id:datasetId,name:'Mock 数据包',company:'CATL',year:2025,version:2,
    source_ids:[source.id],created_at:new Date().toISOString(),data_basis:'user_uploaded',
  };
  return {dataset,source};
}

export async function mockCorrectFact(id:string,body:FactCorrection):Promise<Fact>{
  await sleep(400);
  return {
    id,revision:body.expected_revision+1,company:'CATL',
    metric:'revenue',segment:'group',statement_scope:'consolidated',period_kind:'annual_flow',
    period_start:'2025-01-01',period_end:'2025-12-31',currency:'CNY',
    value:body.value,unit:'CNY',raw_value:body.raw_value??null,
    raw_unit:'CNY_thousand',status:body.status,evidence_ids:body.evidence_ids,
    missing_reason:body.missing_reason??null,restatement_status:'not_restated',
  };
}
