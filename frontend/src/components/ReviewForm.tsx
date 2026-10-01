import {useState} from 'react';
import type {Fact, Evidence, FactCorrection} from '../api/generated';
import {api, ApiError, BASE_URL} from '../api/client';
import {names,metrics,periodOf,fmtRaw,fmtAmount,statusLabels} from '../lib/format';

function message(e:unknown):string{
  if(e instanceof ApiError){
    if(e.code==='REVISION_CONFLICT')return '该事实已被其他复核更新，请重新读取后再复核。';
    if(e.code==='NOT_IMPLEMENTED')return '复核接口尚待实现（后端 R2 尚未合并到 main）。';
    return `${e.message}（${e.code}，${e.requestId}）`;
  }
  return e instanceof Error?e.message:'复核提交失败';
}

export function ReviewForm({fact,evidence,onClose,onSaved,onReload}:{
  fact:Fact;evidence:Evidence|null;onClose:()=>void;onSaved:(f:Fact)=>void;onReload:()=>void;
}){
  const [status,setStatus]=useState<'verified'|'missing'|'needs_review'>(fact.status==='verified'||fact.status==='missing'||fact.status==='needs_review'?fact.status:'verified');
  const [value,setValue]=useState(fact.value??'');
  const [rawValue,setRawValue]=useState(fact.raw_value??'');
  const [missingReason,setMissingReason]=useState(fact.missing_reason??'');
  const [reason,setReason]=useState('');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const isMissing=status==='missing';
  const needEvidence=status==='verified'&&fact.evidence_ids.length===0;
  const canSubmit=!busy&&reason.trim().length>0&&(isMissing?true:value.trim().length>0)&&!needEvidence;
  const submit=async()=>{
    const body:FactCorrection={
      expected_revision:fact.revision??1,
      value:isMissing?null:value.trim(),
      raw_value:rawValue.trim()||null,
      status,
      evidence_ids:fact.evidence_ids,
      reason:reason.trim(),
      missing_reason:isMissing?(missingReason.trim()||null):null,
    };
    setBusy(true);setError('');
    try{onSaved(await api.correctFact(fact.id,body));}
    catch(e){setError(message(e));}
    finally{setBusy(false);}
  };
  return <section className="panel review">
    <div className="review-head"><h2>人工复核</h2><button onClick={onClose}>关闭</button></div>
    <p className="hint">{names[fact.segment]} · {metrics[fact.metric]} · {periodOf(fact)} · 当前 revision {fact.revision??1}（原状态 {statusLabels[fact.status]}）</p>
    <div className="review-grid">
      <div>
        <label>状态
          <select value={status} onChange={e=>setStatus(e.target.value as 'verified'|'missing'|'needs_review')}>
            <option value="verified">已复核</option>
            <option value="needs_review">需复核</option>
            <option value="missing">缺失</option>
          </select>
        </label>
        <label>规范值（人民币元，十进制字符串）
          <input type="text" value={value} disabled={isMissing} onChange={e=>setValue(e.target.value)} placeholder={isMissing?'缺失时无需填写':'例如 423701834000'}/>
          {!isMissing&&<span className="muted">≈ {fmtAmount(value||null,'CNY')}</span>}
        </label>
        <label>原值（千元 / 百分数，可留空由后端按规范值反算）
          <input type="text" value={rawValue} disabled={isMissing} onChange={e=>setRawValue(e.target.value)} placeholder="留空自动反算"/>
        </label>
        {isMissing&&<label>缺失原因
          <input type="text" value={missingReason} onChange={e=>setMissingReason(e.target.value)} placeholder="例如：目标字段未在报表中披露"/>
        </label>}
        <label>复核理由（必填）
          <input type="text" value={reason} onChange={e=>setReason(e.target.value)} placeholder="说明本次更正的依据"/>
        </label>
        {needEvidence&&<p className="error">状态为「已复核」需至少一条证据，但该事实暂无关联证据。</p>}
        {error&&<p role="alert" className="error">{error}{error.includes('其他复核更新')&&<button className="inline" onClick={onReload}>重新读取</button>}</p>}
        <div className="review-actions"><button onClick={submit} disabled={!canSubmit}>{busy?'提交中…':'提交复核'}</button></div>
      </div>
      <div className="evidence">
        <h3>原文证据</h3>
        {evidence?<>
          <p>PDF 第 {evidence.pdf_page} 页 · 印刷页码 {evidence.printed_page}</p>
          <pre>{evidence.excerpt}</pre>
          <a target="_blank" rel="noreferrer" href={`${BASE_URL}/api/v1/sources/${encodeURIComponent(evidence.source_id)}/content#page=${evidence.pdf_page}`}>打开原始 PDF</a>
          <p className="muted">当前原值 {fmtRaw(fact.raw_value,fact.raw_unit)}，规范值 {fmtAmount(fact.value,fact.unit)}</p>
        </>:<p>该事实暂无关联证据，无法对照原文。</p>}
      </div>
    </div>
  </section>;
}
