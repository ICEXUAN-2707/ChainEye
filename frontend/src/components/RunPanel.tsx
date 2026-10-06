import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import type {Assumptions,AssumptionRecord,Calculation,Claim,Dataset,Event,Evidence,Report,Run} from '../api/generated';
import {api,BASE_URL,errorMessage} from '../api/client';
import {buildResumeRequest,buildRunCreate,claimsFromEvents,isRunActive,mergeEvents,runIdempotencyKey} from '../lib/run';
import {calculationApiUrl,evidenceApiUrl,loadCurrentReport,reportExportUrl,reportRequestRunId,resolveClaimReferences,resolveEvidenceReferences,shouldAcceptReportResponse,sourcePageUrl,type ResolvedReference} from '../lib/report';
import {fmtAmount,fmtPp,metrics,periodOf,fmtFormula,fmtNode,fmtAssumptionKey,fmtBasis,fmtFactRevisions} from '../lib/format';

const runStatusLabels:Record<string,string>={queued:'排队中',running:'运行中',waiting_review:'待复核',completed:'已完成',partial:'部分完成',failed:'失败',cancelled:'已取消'};
const eventTypeLabels:Record<string,string>={file_access:'文件访问',tool_call:'工具调用',calculation:'计算',llm_call:'模型调用',node_status:'节点状态',report_generated:'报告生成',error:'错误'};
const claimStatusLabels:Record<string,string>={pending:'待核验',supported:'有支持',insufficient:'证据不足',rejected:'已拒绝'};
const claimKindLabels:Record<string,string>={fact:'事实',calculation:'计算',inference:'推论',opinion:'观点',hypothesis:'假设'};
const runStatusClass=(status:string)=>status==='completed'?'s-verified':status==='failed'||status==='cancelled'?'s-missing':status==='waiting_review'||status==='partial'?'s-needs-review':'s-extracted';

function calculationValue(calculation:Calculation):string{
  if(calculation.value===null)return `不可计算：${calculation.reason??'原因未提供'}`;
  if(calculation.unit==='pp')return fmtPp(calculation.value);
  return fmtAmount(calculation.value,calculation.unit);
}

function EvidenceReferences({title,references}:{title:string;references:ResolvedReference<Evidence>[]}):React.ReactNode{
  if(references.length===0)return null;
  return <div className="claim-reference"><strong>{title}</strong><ul>{references.map(reference=><li key={reference.id}>
    {!reference.value?<span className="error">证据 <span className="mono">{reference.id}</span> 缺失</span>:<>
      <a target="_blank" rel="noreferrer" href={`${BASE_URL}${evidenceApiUrl(reference.id)}`}>查看证据</a> · <span className="mono">{reference.id}</span>
      {reference.value.locator_kind==='pdf'&&<> · <a target="_blank" rel="noreferrer" href={`${BASE_URL}${sourcePageUrl(reference.value.source_id,reference.value.pdf_page)}`}>原文 PDF{reference.value.pdf_page?` 第 ${reference.value.pdf_page} 页`:''}</a></>}
      <span className="muted mono">Source {reference.value.source_id} · SHA256 {reference.value.sha256}</span>
      <span className="muted">{reference.value.excerpt}</span>
    </>}
  </li>)}</ul></div>;
}

function CalculationReferences({references}:{references:ResolvedReference<Calculation>[]}):React.ReactNode{
  if(references.length===0)return null;
  return <div className="claim-reference"><strong>计算</strong><ul>{references.map(reference=><li key={reference.id}>
    {!reference.value?<span className="error">计算 <span className="mono">{reference.id}</span> 缺失</span>:<>
      <a target="_blank" rel="noreferrer" href={`${BASE_URL}${calculationApiUrl(reference.id)}`}>查看计算</a> · <span className="mono">{reference.id}</span>
      <span className="muted">{fmtFormula(reference.value.formula_id)} · <span className="mono">{reference.value.formula_id} v{reference.value.formula_version}</span> · {calculationValue(reference.value)}</span>
      <span className="muted mono">输入：{fmtFactRevisions(reference.value.input_fact_ids,reference.value.input_revisions)}</span>
    </>}
  </li>)}</ul></div>;
}

function AssumptionReferences({references}:{references:ResolvedReference<AssumptionRecord>[]}):React.ReactNode{
  if(references.length===0)return null;
  return <div className="claim-reference"><strong>假设</strong><ul>{references.map(reference=><li key={reference.id}>
    {!reference.value?<span className="error">假设 <span className="mono">{reference.id}</span> 缺失</span>:<>
      <span className="mono">{reference.id}</span>
      <span className="muted">{Object.entries(reference.value.values).filter(([key])=>['cost_exposure','effective_price_shock','customer_pass_through'].includes(key)).map(([key,value])=>`${fmtAssumptionKey(key)} ${value}`).join('，')} · {fmtBasis(reference.value.values.basis)}</span>
    </>}
  </li>)}</ul></div>;
}

function ClaimReferences({report,claim}:{report:Report;claim:Claim}):React.ReactNode{
  const references=resolveClaimReferences(report,claim);
  const total=references.evidence.length+references.counterEvidence.length+references.calculations.length+references.assumptions.length;
  return <details className="claim-trace"><summary>支持证据 {references.evidence.length} · 反证 {references.counterEvidence.length} · 计算 {references.calculations.length} · 假设 {references.assumptions.length}</summary>
    {total===0&&<p className="muted">该结论没有引用对象。</p>}
    <EvidenceReferences title="支持证据" references={references.evidence}/>
    <EvidenceReferences title="反证" references={references.counterEvidence}/>
    <CalculationReferences references={references.calculations}/>
    <AssumptionReferences references={references.assumptions}/>
    {claim.limitations.length>0&&<p className="muted">限制：{claim.limitations.join('；')}</p>}
  </details>;
}

export function RunPanel({dataset}:{dataset:Dataset}){
  const [question,setQuestion]=useState('');
  const [segment,setSegment]=useState<'power_battery'|'energy_storage'>('power_battery');
  const [mode,setMode]=useState<'live'|'replay'>('live');
  const [replayId,setReplayId]=useState('');
  const [run,setRun]=useState<Run|null>(null);
  const [events,setEvents]=useState<Event[]>([]);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [report,setReport]=useState<Report|null>(null);
  const [reportError,setReportError]=useState('');
  const [reportBusy,setReportBusy]=useState(false);
  const [reportReload,setReportReload]=useState(0);
  const [costExposure,setCostExposure]=useState('');
  const [priceShock,setPriceShock]=useState('');
  const [passThrough,setPassThrough]=useState('');
  const [basis,setBasis]=useState<'user_assumption'|'research_assumption'>('user_assumption');
  const [acknowledged,setAcknowledged]=useState(false);
  const afterSeq=useRef(0);
  const currentRunId=useRef('');
  const actionController=useRef<AbortController|null>(null);

  const needsAssumptions=run?.missing_requirements.includes('scenario_assumptions')??false;
  const assumptionsReady=costExposure.trim()!==''&&priceShock.trim()!==''&&passThrough.trim()!==''&&acknowledged;
  const canCreate=question.trim()!==''&&!busy&&!(run&&isRunActive(run.status))&&(mode==='live'||replayId.trim()!=='');
  const canResume=!!run&&run.status==='waiting_review'&&!busy&&(!needsAssumptions||assumptionsReady);
  const claims=useMemo(()=>claimsFromEvents(events),[events]);

  useEffect(()=>{
    actionController.current?.abort();afterSeq.current=0;currentRunId.current='';
    setRun(null);setEvents([]);setBusy(false);setError('');setReport(null);setReportError('');setReportBusy(false);setReportReload(0);
    return()=>actionController.current?.abort();
  },[dataset.id,dataset.version]);

  useEffect(()=>{
    setReport(null);setReportError('');setReportBusy(false);
    const runId=reportRequestRunId(run);if(!runId||currentRunId.current!==runId)return;
    const controller=new AbortController();setReportBusy(true);
    loadCurrentReport(run,controller.signal,()=>currentRunId.current,api.report)
      .then(result=>{
        if(result.status==='loaded')setReport(result.report);
        if(result.status==='failed')setReportError(errorMessage(result.error));
      })
      .finally(()=>{if(shouldAcceptReportResponse(runId,currentRunId.current,controller.signal.aborted))setReportBusy(false);});
    return()=>controller.abort();
  },[run?.id,run?.report_ready,reportReload]);

  const sync=useCallback(async(runId:string,signal?:AbortSignal)=>{
    let cursor=afterSeq.current;const [nextRun,firstPage]=await Promise.all([api.run(runId,signal),api.runEvents(runId,{afterSeq:cursor,limit:200,signal})]);
    const incoming=[...firstPage.items];cursor=firstPage.next_after_seq;let hasMore=firstPage.has_more;
    while(hasMore&&!signal?.aborted){
      const page=await api.runEvents(runId,{afterSeq:cursor,limit:200,signal});
      incoming.push(...page.items);cursor=page.next_after_seq;hasMore=page.has_more;
    }
    if(signal?.aborted||currentRunId.current!==runId)return;
    setRun(nextRun);setEvents(previous=>mergeEvents(previous,incoming));afterSeq.current=cursor;
  },[]);

  useEffect(()=>{
    if(!run||!isRunActive(run.status))return;
    const runId=run.id;currentRunId.current=runId;
    let stopped=false;let timer:number|undefined;let controller:AbortController|undefined;
    const poll=async()=>{
      controller=new AbortController();
      try{await sync(runId,controller.signal);}
      catch(value){if(!controller.signal.aborted)setError(errorMessage(value));}
      if(!stopped)timer=window.setTimeout(()=>void poll(),750);
    };
    void poll();
    return()=>{stopped=true;controller?.abort();if(timer!==undefined)window.clearTimeout(timer);};
  },[run?.id,run?.status,sync]);

  const create=async()=>{
    const body=buildRunCreate(dataset,question,segment,mode,replayId);
    actionController.current?.abort();const controller=new AbortController();actionController.current=controller;
    setBusy(true);setError('');
    try{
      const created=await api.createRun(body,runIdempotencyKey(body),controller.signal);
      if(controller.signal.aborted)return;
      afterSeq.current=0;currentRunId.current=created.id;setEvents([]);setRun(created);
    }catch(value){if(!controller.signal.aborted)setError(errorMessage(value));}
    finally{if(!controller.signal.aborted)setBusy(false);}
  };

  const refresh=async()=>{
    if(!run)return;
    actionController.current?.abort();const controller=new AbortController();actionController.current=controller;
    currentRunId.current=run.id;setBusy(true);setError('');
    try{
      await sync(run.id,controller.signal);
      if(!controller.signal.aborted&&run.report_ready&&!report)setReportReload(value=>value+1);
    }
    catch(value){if(!controller.signal.aborted)setError(errorMessage(value));}
    finally{if(!controller.signal.aborted)setBusy(false);}
  };

  const resume=async()=>{
    if(!run||!canResume)return;
    let assumptions:Assumptions|undefined;
    if(needsAssumptions)assumptions={cost_exposure:costExposure.trim(),effective_price_shock:priceShock.trim(),customer_pass_through:passThrough.trim(),basis,acknowledged:true};
    actionController.current?.abort();const controller=new AbortController();actionController.current=controller;
    setBusy(true);setError('');
    try{
      const resumed=await api.resumeRun(run.id,buildResumeRequest(run,assumptions),controller.signal);
      if(!controller.signal.aborted)setRun(resumed);
    }catch(value){if(!controller.signal.aborted)setError(errorMessage(value));}
    finally{if(!controller.signal.aborted)setBusy(false);}
  };

  return <section className="panel">
    <h2>研究任务</h2>
    <p className="hint">输入研究问题后，后端只在当前数据快照内执行白名单检索、确定性计算、受控模型调用与Claim核验，最终生成可追溯简报。实时与回放会明确标识。</p>
    <div className="run-form">
      <label>研究问题<textarea value={question} onChange={event=>setQuestion(event.target.value)} rows={3} maxLength={4000} placeholder="例如：分析 2025 年动力电池业务收入和毛利变化"/></label>
      <div className="assumption-grid">
        <label>业务<select value={segment} onChange={event=>setSegment(event.target.value as typeof segment)}><option value="power_battery">动力电池</option><option value="energy_storage">储能电池</option></select></label>
        <label>模式<select value={mode} onChange={event=>setMode(event.target.value as typeof mode)}><option value="live">实时</option><option value="replay">回放</option></select></label>
        {mode==='replay'&&<label>回放 Run ID<input type="text" value={replayId} onChange={event=>setReplayId(event.target.value)} placeholder="指定同一数据快照的已结束 Run ID"/></label>}
      </div>
      <div className="review-actions"><button onClick={()=>void create()} disabled={!canCreate}>{busy?'提交中…':'创建研究任务'}</button></div>
    </div>
    {error&&<p role="alert" className="error">{error}</p>}
    {run&&<div className="run-status">
      <p className="run-head">Run <span className="mono">{run.id}</span> · <span className={`badge ${runStatusClass(run.status)}`}>{runStatusLabels[run.status]}</span> · 模式 {run.mode==='live'?'实时':'回放'}{run.stale?' · 已过期':''}</p>
      <p className="muted mono">数据快照：{run.dataset_id}@v{run.dataset_version}</p>
      {run.current_node&&<p className="muted">当前节点：{fmtNode(run.current_node)}（<span className="mono">{run.current_node}</span>）</p>}
      {run.missing_requirements.length>0&&<p className="error">缺少前置：{run.missing_requirements.join('；')}</p>}
      {run.error&&<p className="error">运行错误：{run.error.message}（{run.error.code}）</p>}
      {needsAssumptions&&<div className="resume-box">
        <p className="hint">该问题包含条件情景。请明确填写并确认假设后继续；这些数值不会被当作已披露事实。</p>
        <div className="assumption-grid">
          <label>成本暴露 s ∈ [0,1]<input value={costExposure} onChange={event=>setCostExposure(event.target.value)} inputMode="decimal"/></label>
          <label>价格冲击 x ∈ [-0.5,0.5]<input value={priceShock} onChange={event=>setPriceShock(event.target.value)} inputMode="decimal"/></label>
          <label>客户传导 k ∈ [0,1]<input value={passThrough} onChange={event=>setPassThrough(event.target.value)} inputMode="decimal"/></label>
          <label>假设来源<select value={basis} onChange={event=>setBasis(event.target.value as typeof basis)}><option value="user_assumption">用户假设</option><option value="research_assumption">研究假设</option></select></label>
        </div>
        <label className="check"><input type="checkbox" checked={acknowledged} onChange={event=>setAcknowledged(event.target.checked)}/>我确认以上是条件假设，而非已披露事实</label>
      </div>}
      <div className="review-actions">
        <button onClick={()=>void refresh()} disabled={busy}>刷新状态与事件</button>
        {run.status==='waiting_review'&&<button onClick={()=>void resume()} disabled={!canResume}>继续运行</button>}
      </div>
      {claims.length>0&&<div className="claims"><h3>引用已校验 Claim</h3><ul>{claims.map(claim=><li key={claim.id}><span className={`badge ${claim.review_status==='supported'?'s-verified':claim.review_status==='rejected'?'s-missing':'s-needs-review'}`}>{claimStatusLabels[claim.review_status]}</span> {claim.text}<span className="muted mono">Claim {claim.id}</span><span className="muted">证据 {claim.evidence_ids.length} · 计算 {claim.calculation_ids.length} · 假设 {claim.assumption_ids.length}{claim.limitations.length?` · 限制：${claim.limitations.join('；')}`:''}</span></li>)}</ul></div>}
      {events.length>0&&<div className="events"><h3>事件时间线</h3><ol className="trace">{events.map(event=><li key={event.seq}><strong>{eventTypeLabels[event.type]??event.type}</strong>（{event.node}）<span className="muted">#{event.seq} · {event.at}</span><details><summary>查看事件详情</summary><pre>{JSON.stringify(event.payload,null,2)}</pre></details></li>)}</ol></div>}
      {reportBusy&&<p className="muted">正在加载报告…</p>}
      {reportError&&<div className="report-error"><p role="alert" className="error">报告加载失败：{reportError}</p><button onClick={()=>setReportReload(value=>value+1)} disabled={reportBusy}>重试加载报告</button></div>}
      {report&&<div className="report"><h3>报告 · {report.title}</h3>
        <p className="muted mono">Run {report.run_id} · 数据快照 {report.dataset_id}@v{report.dataset_version} · 模式 {report.mode}</p>
        <div className="review-actions">
          <a className="button-link" target="_blank" rel="noreferrer" href={`${BASE_URL}${reportExportUrl(run.id,'markdown')}`}>导出 Markdown</a>
          <a className="button-link" target="_blank" rel="noreferrer" href={`${BASE_URL}${reportExportUrl(run.id,'pdf')}`}>导出 PDF</a>
        </div>
        {report.claims.length>0&&<div className="table"><table><thead><tr><th>类型</th><th>结论</th><th>状态</th><th>引用与限制</th></tr></thead><tbody>{report.claims.map((claim:Claim)=><tr key={claim.id}><td><span className="badge s-extracted">{claimKindLabels[claim.kind]??claim.kind}</span><span className="muted mono">{claim.id}</span></td><td>{claim.text}</td><td><span className={`badge ${claim.review_status==='supported'?'s-verified':claim.review_status==='rejected'?'s-missing':'s-needs-review'}`}>{claimStatusLabels[claim.review_status]}</span></td><td><ClaimReferences report={report} claim={claim}/></td></tr>)}</tbody></table></div>}
        {report.limitations.length>0&&<p className="muted">限制：{report.limitations.join('；')}</p>}
        <details><summary>报告详情（事实 {report.facts.length} · 计算 {report.calculations.length} · 假设 {report.assumptions.length} · 证据 {report.evidence.length}）</summary>
          {report.facts.length>0&&<><h4>事实（ID 与 revision）</h4><ul className="report-detail">{report.facts.map(f=><li key={f.id}><span className="mono">{f.id}@rev{f.revision??'—'}</span> · {metrics[f.metric]??f.metric} · {periodOf(f)} · {fmtAmount(f.value,f.unit)}<EvidenceReferences title="事实证据" references={resolveEvidenceReferences(report,f.evidence_ids)}/></li>)}</ul></>}
          {report.calculations.length>0&&<><h4>计算（公式与输入快照）</h4><ul className="report-detail">{report.calculations.map(calculation=><li key={calculation.id}><a target="_blank" rel="noreferrer" href={`${BASE_URL}${calculationApiUrl(calculation.id)}`}>查看计算</a> · <span className="mono">{calculation.id}</span> · {fmtFormula(calculation.formula_id)} · <span className="mono">{calculation.formula_id} v{calculation.formula_version}</span> · {calculationValue(calculation)}<span className="muted mono">输入：{fmtFactRevisions(calculation.input_fact_ids,calculation.input_revisions)}</span>{Object.keys(calculation.assumption_snapshot).length?<span className="muted">参数：{Object.entries(calculation.assumption_snapshot).map(([key,value])=>`${fmtAssumptionKey(key)} ${value}`).join('，')}</span>:null}</li>)}</ul></>}
          {report.assumptions.length>0&&<><h4>假设（ID 与参数）</h4><ul className="report-detail">{report.assumptions.map(assumption=><li key={assumption.id}><span className="mono">{assumption.id}</span> · {Object.entries(assumption.values).filter(([key])=>['cost_exposure','effective_price_shock','customer_pass_through'].includes(key)).map(([key,value])=>`${fmtAssumptionKey(key)} ${value}`).join('，')} · {fmtBasis(assumption.values.basis)}</li>)}</ul></>}
          {report.evidence.length>0&&<><h4>证据</h4><EvidenceReferences title="报告引用证据" references={resolveEvidenceReferences(report,report.evidence.map(evidence=>evidence.id))}/></>}
        </details>
      </div>}
    </div>}
  </section>;
}
