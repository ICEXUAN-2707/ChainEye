import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import type {Assumptions,Dataset,Event,Run} from '../api/generated';
import {api,ApiError} from '../api/client';
import {buildRunCreate,claimsFromEvents,isRunActive,mergeEvents,runIdempotencyKey} from '../lib/run';

const runStatusLabels:Record<string,string>={queued:'排队中',running:'运行中',waiting_review:'待复核',completed:'已完成',partial:'部分完成',failed:'失败',cancelled:'已取消'};
const eventTypeLabels:Record<string,string>={file_access:'文件访问',tool_call:'工具调用',calculation:'计算',llm_call:'模型调用',node_status:'节点状态',report_generated:'报告生成',error:'错误'};
const claimStatusLabels:Record<string,string>={pending:'待核验',supported:'有支持',insufficient:'证据不足',rejected:'已拒绝'};
const runStatusClass=(status:string)=>status==='completed'?'s-verified':status==='failed'||status==='cancelled'?'s-missing':status==='waiting_review'||status==='partial'?'s-needs-review':'s-extracted';

function message(error:unknown):string{
  if(error instanceof ApiError)return `${error.message}（${error.code}，${error.requestId}）`;
  return error instanceof Error?error.message:'操作失败';
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
    setRun(null);setEvents([]);setBusy(false);setError('');
    return()=>actionController.current?.abort();
  },[dataset.id,dataset.version]);

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
      catch(value){if(!controller.signal.aborted)setError(message(value));}
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
    }catch(value){if(!controller.signal.aborted)setError(message(value));}
    finally{if(!controller.signal.aborted)setBusy(false);}
  };

  const refresh=async()=>{
    if(!run)return;
    actionController.current?.abort();const controller=new AbortController();actionController.current=controller;
    currentRunId.current=run.id;setBusy(true);setError('');
    try{await sync(run.id,controller.signal);}
    catch(value){if(!controller.signal.aborted)setError(message(value));}
    finally{if(!controller.signal.aborted)setBusy(false);}
  };

  const resume=async()=>{
    if(!run||!canResume)return;
    let assumptions:Assumptions|undefined;
    if(needsAssumptions)assumptions={cost_exposure:costExposure.trim(),effective_price_shock:priceShock.trim(),customer_pass_through:passThrough.trim(),basis,acknowledged:true};
    actionController.current?.abort();const controller=new AbortController();actionController.current=controller;
    setBusy(true);setError('');
    try{
      const resumed=await api.resumeRun(run.id,{expected_run_status:'waiting_review',dataset_version:run.dataset_version,...(assumptions?{assumptions}:{})},controller.signal);
      if(!controller.signal.aborted)setRun(resumed);
    }catch(value){if(!controller.signal.aborted)setError(message(value));}
    finally{if(!controller.signal.aborted)setBusy(false);}
  };

  return <section className="panel">
    <h2>研究任务</h2>
    <p className="hint">输入研究问题后，后端只在当前数据快照内执行白名单检索、确定性计算、受控模型调用与Claim核验。实时与回放会明确标识；R4只形成已核验Claim，尚不生成R5报告。</p>
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
      {run.current_node&&<p className="muted">当前节点：{run.current_node}</p>}
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
      {claims.length>0&&<div className="claims"><h3>引用已校验 Claim</h3><ul>{claims.map(claim=><li key={claim.id}><span className={`badge ${claim.review_status==='supported'?'s-verified':claim.review_status==='rejected'?'s-missing':'s-needs-review'}`}>{claimStatusLabels[claim.review_status]}</span> {claim.text}<span className="muted">证据 {claim.evidence_ids.length} · 计算 {claim.calculation_ids.length} · 假设 {claim.assumption_ids.length}{claim.limitations.length?` · 限制：${claim.limitations.join('；')}`:''}</span></li>)}</ul></div>}
      {events.length>0&&<div className="events"><h3>事件时间线</h3><ol className="trace">{events.map(event=><li key={event.seq}><strong>{eventTypeLabels[event.type]??event.type}</strong>（{event.node}）<span className="muted">#{event.seq} · {event.at}</span><details><summary>查看事件详情</summary><pre>{JSON.stringify(event.payload,null,2)}</pre></details></li>)}</ol></div>}
    </div>}
  </section>;
}
