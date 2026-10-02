import {useState} from 'react';
import type {Fact, Evidence, FactCorrection} from '../api/generated';
import {api, ApiError, BASE_URL} from '../api/client';
import {names,metrics,periodOf,fmtRaw,fmtAmount,statusLabels} from '../lib/format';
import {buildFactCorrection,canSubmitReview,type ReviewStatus} from '../lib/review';

function message(e:unknown):string{
  if(e instanceof ApiError){
    if(e.code==='REVISION_CONFLICT')return '该事实已被其他复核更新，请重新读取后再复核。';
    return `${e.message}（${e.code}，${e.requestId}）`;
  }
  return e instanceof Error?e.message:'复核提交失败';
}

export function ReviewForm({fact,evidence,evidenceLoading,evidenceError,onClose,onSaved,onReload}:{
  fact:Fact;evidence:Evidence|null;evidenceLoading:boolean;evidenceError:string;onClose:()=>void;onSaved:(f:Fact)=>Promise<void>;onReload:()=>Promise<void>;
}){
  const [status,setStatus]=useState<ReviewStatus>(fact.status==='verified'||fact.status==='missing'||fact.status==='needs_review'?fact.status:'verified');
  const [value,setValue]=useState(fact.value??'');
  const [rawValue,setRawValue]=useState(fact.raw_value??'');
  const [missingReason,setMissingReason]=useState(fact.missing_reason??'');
  const [reason,setReason]=useState('');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const isMissing=status==='missing';
  const isRatio=fact.unit==='ratio';
  const needEvidence=status==='verified'&&fact.evidence_ids.length===0;
  const evidenceMatches=!!evidence&&evidence.id===fact.evidence_ids[0];
  const evidenceUnavailable=status==='verified'&&fact.evidence_ids.length>0&&(evidenceLoading||!!evidenceError||!evidenceMatches);
  const canSubmit=canSubmitReview({busy,status,value,missingReason,reason,evidenceCount:fact.evidence_ids.length,evidenceReady:!evidenceUnavailable&&!needEvidence});
  const submit=async()=>{
    const body:FactCorrection=buildFactCorrection(fact,status,value,rawValue,missingReason,reason);
    setBusy(true);setError('');
    try{await onSaved(await api.correctFact(fact.id,body));}
    catch(e){setError(message(e));}
    finally{setBusy(false);}
  };
  return <section className="panel review">
    <div className="review-head"><h2>人工复核</h2><button onClick={onClose}>关闭</button></div>
    <p className="hint">{names[fact.segment]} · {metrics[fact.metric]} · {periodOf(fact)} · 当前 revision {fact.revision??1}（原状态 {statusLabels[fact.status]}）</p>
    <div className="review-grid">
      <div>
        <label>状态
          <select value={status} onChange={e=>setStatus(e.target.value as ReviewStatus)}>
            <option value="verified">已复核</option>
            <option value="needs_review">需复核</option>
            <option value="missing">缺失</option>
          </select>
        </label>
        <label>规范值（{isRatio?'比率十进制字符串':'人民币元，十进制字符串'}）
          <input type="text" value={value} disabled={isMissing} onChange={e=>setValue(e.target.value)} placeholder={isMissing?'缺失时无需填写':isRatio?'例如 0.2385':'例如 423701834000'}/>
          {!isMissing&&<span className="muted">≈ {fmtAmount(value||null,fact.unit)}</span>}
        </label>
        <label>原值（{fact.raw_unit==='percent'?'百分数':'千元'}，可留空由后端按规范值反算）
          <input type="text" value={rawValue} disabled={isMissing} onChange={e=>setRawValue(e.target.value)} placeholder="留空自动反算"/>
        </label>
        {isMissing&&<label>缺失原因
          <input type="text" value={missingReason} onChange={e=>setMissingReason(e.target.value)} placeholder="例如：目标字段未在报表中披露"/>
        </label>}
        <label>复核理由（必填）
          <input type="text" value={reason} onChange={e=>setReason(e.target.value)} placeholder="说明本次更正的依据"/>
        </label>
        {needEvidence&&<p className="error">状态为「已复核」需至少一条证据，但该事实暂无关联证据。</p>}
        {status==='verified'&&evidenceLoading&&<p role="status">正在读取原文证据，读取完成后可提交复核。</p>}
        {status==='verified'&&evidenceError&&<p className="error">原文证据读取失败，不能提交「已复核」。</p>}
        {error&&<p role="alert" className="error">{error}{error.includes('其他复核更新')&&<button className="inline" onClick={onReload}>重新读取</button>}</p>}
        <div className="review-actions"><button onClick={submit} disabled={!canSubmit}>{busy?'提交中…':'提交复核'}</button></div>
      </div>
      <div className="evidence">
        <h3>原文证据 · 溯源链</h3>
        {evidenceLoading?<p role="status">正在读取原文证据…</p>:evidenceError?<p role="alert" className="error">{evidenceError}<button className="inline" onClick={()=>void onReload()}>重新读取</button></p>:evidenceMatches?<>
          <ol className="trace">
            <li>事实：原值 {fmtRaw(fact.raw_value,fact.raw_unit)}，规范值 {fmtAmount(fact.value,fact.unit)}</li>
            <li>定位：PDF 第 {evidence.pdf_page} 页 · 印刷页码 {evidence.printed_page}{evidence.bbox?` · 坐标 [${evidence.bbox.map(n=>Math.round(n)).join(', ')}]`:''}</li>
            <li>原文：<pre>{evidence.excerpt}</pre><a target="_blank" rel="noreferrer" href={`${BASE_URL}/api/v1/sources/${encodeURIComponent(evidence.source_id)}/content#page=${evidence.pdf_page}`}>打开原始 PDF</a></li>
          </ol>
          <p className="muted mono">来源 {evidence.source_id} · SHA256 {evidence.sha256.slice(0,12)}…</p>
        </>:<p>该事实暂无关联证据，无法对照原文。</p>}
      </div>
    </div>
  </section>;
}
