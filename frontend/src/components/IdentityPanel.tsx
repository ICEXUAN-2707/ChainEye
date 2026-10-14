import {useEffect,useRef,useState,type FormEvent} from 'react';
import type {CompanyProfile,Dataset,IdentityCandidate,IdentityConfirmation} from '../api/generated';
import {ApiError,errorMessage} from '../api/client';
import {candidateMatchesDataset,hasIdentityBlocker,snapshotKey} from '../lib/workbench';

const identityLabels:Record<Dataset['identity_status'],string>={confirmed:'已确认',conflict:'冲突',unconfirmed:'待确认'};
const candidateLabels:Record<IdentityCandidate['status'],string>={identified:'已识别',unrecognized:'未识别',ambiguous:'有歧义',conflict:'冲突'};

export function IdentityPanel({dataset,candidates,companies,loading,onConfirm,onRefresh}:{
  dataset:Dataset;
  candidates:IdentityCandidate[];
  companies:CompanyProfile[];
  loading:boolean;
  onConfirm:(body:IdentityConfirmation)=>Promise<Dataset>;
  onRefresh:()=>Promise<void>;
}){
  const [companyId,setCompanyId]=useState<IdentityConfirmation['company_id']>(dataset.company_id);
  const [reportYear,setReportYear]=useState<number>(dataset.year);
  const [reason,setReason]=useState('人工核对年报标题、证券标识和证据页');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [success,setSuccess]=useState('');
  const [stale,setStale]=useState(false);
  const currentKey=useRef(snapshotKey(dataset));
  const profile=companies.find(item=>item.id===companyId);
  const years=profile?.supported_report_years??[dataset.year];

  useEffect(()=>{
    currentKey.current=snapshotKey(dataset);
    setCompanyId(dataset.company_id);setReportYear(dataset.year);setBusy(false);setError('');setSuccess('');setStale(false);
  },[dataset.id,dataset.version,dataset.company_id,dataset.year]);

  const submit=async(event:FormEvent)=>{
    event.preventDefault();
    const requestedKey=snapshotKey(dataset);
    setBusy(true);setError('');setSuccess('');setStale(false);
    try{
      const confirmed=await onConfirm({expected_version:dataset.version,company_id:companyId,report_year:reportYear,report_type:'annual_report',reason:reason.trim()});
      if(currentKey.current===requestedKey)setSuccess(`身份确认已保存，Dataset 将切换至 v${confirmed.version}。`);
    }catch(value){
      if(currentKey.current!==requestedKey)return;
      if(value instanceof ApiError&&value.status===409){
        setStale(true);setError(`Dataset 版本或身份候选已变化，请刷新后重新确认。（${value.code}，${value.requestId}）`);
      }else setError(errorMessage(value));
    }finally{if(currentKey.current===requestedKey)setBusy(false);}
  };

  const blocked=hasIdentityBlocker(dataset,candidates);
  return <section className="panel identity-panel">
    <div className="section-heading"><div><h2>企业身份</h2><p className="hint">当前快照：{dataset.company} {dataset.year} · v{dataset.version}</p></div><span className={`status-pill identity-${dataset.identity_status}`}>{identityLabels[dataset.identity_status]}</span></div>
    {blocked&&<p role="alert" className="identity-warning">企业身份尚未闭合，情景和研究任务已禁用。请核对候选后进行人工确认。</p>}
    {loading?<p role="status">正在读取身份候选…</p>:candidates.length?<div className="identity-candidates">
      {candidates.map(candidate=>{
        const compatible=candidateMatchesDataset(candidate,dataset);
        return <article key={candidate.source_id} className={`identity-candidate candidate-${candidate.status}`}>
          <div><strong>{candidate.legal_name??'未识别企业'}</strong><span className="status-pill">{candidateLabels[candidate.status]}</span>{!compatible&&<span className="status-pill danger">与当前 Dataset 不兼容</span>}</div>
          <p>来源：<code>{candidate.source_id}</code> · 企业：{candidate.company_code??'—'} · 年度：{candidate.report_year??'—'} · 类型：{candidate.report_type}</p>
          <p>证据页：{candidate.evidence_pages.length?candidate.evidence_pages.join('、'):'未提供'}</p>
          {!!candidate.warnings.length&&<ul>{candidate.warnings.map((warning,index)=><li key={`${warning}:${index}`}>{warning}</li>)}</ul>}
        </article>;
      })}
    </div>:<p className="muted">当前快照尚无文档身份候选；上传年报后会在这里显示识别结果。</p>}
    <form className="identity-confirm" onSubmit={submit}>
      <label>确认企业<select value={companyId} onChange={event=>{const id=event.target.value as IdentityConfirmation['company_id'];setCompanyId(id);const next=companies.find(item=>item.id===id);if(next&&!next.supported_report_years.includes(reportYear))setReportYear(next.supported_report_years[0] as IdentityConfirmation['report_year']);}}>
        {companies.map(item=><option key={item.id} value={item.id}>{item.legal_name}（{item.company_code}）</option>)}
      </select></label>
      <label>报告年度<select value={reportYear} onChange={event=>setReportYear(Number(event.target.value) as IdentityConfirmation['report_year'])}>{years.map(item=><option key={item} value={item}>{item}</option>)}</select></label>
      <label className="identity-reason">确认依据<input value={reason} onChange={event=>setReason(event.target.value)} placeholder="说明人工核对依据"/></label>
      <button type="submit" disabled={busy||loading||!candidates.length||!reason.trim()}>{busy?'确认中…':'确认身份并发布新版本'}</button>
    </form>
    {error&&<p role="alert" className="error">{error}</p>}
    {success&&<p role="status" className="success">{success}</p>}
    {stale&&<button type="button" className="secondary" onClick={()=>void onRefresh()}>刷新最新 Dataset</button>}
  </section>;
}
