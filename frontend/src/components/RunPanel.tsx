import {useState} from 'react';
import type {Dataset,Run,Event,RunCreate,Report,Claim} from '../api/generated';
import {api,ApiError,BASE_URL} from '../api/client';
import {stableKey} from '../lib/scenario';

const runStatusLabels:Record<string,string>={queued:'排队中',running:'运行中',waiting_review:'待复核',completed:'已完成',partial:'部分完成',failed:'失败',cancelled:'已取消'};
const eventTypeLabels:Record<string,string>={file_access:'文件访问',tool_call:'工具调用',calculation:'计算',llm_call:'模型调用',node_status:'节点状态',report_generated:'报告生成',error:'错误'};
const claimKindLabels:Record<string,string>={fact:'事实',calculation:'计算',inference:'推论',opinion:'观点',hypothesis:'假设'};
const runStatusClass=(s:string)=>s==='completed'?'s-verified':s==='failed'||s==='cancelled'?'s-missing':s==='waiting_review'?'s-needs-review':'s-extracted';

function message(e:unknown):string{
  if(e instanceof ApiError){
    if(e.code==='NOT_IMPLEMENTED')return '该接口尚待实现（后端 R4 未完成）。';
    return `${e.message}（${e.code}，${e.requestId}）`;
  }
  return e instanceof Error?e.message:'操作失败';
}

export function RunPanel({dataset}:{dataset:Dataset}){
  const [question,setQuestion]=useState('');
  const [segment,setSegment]=useState<'power_battery'|'energy_storage'>('power_battery');
  const [mode,setMode]=useState<'live'|'replay'>('live');
  const [replayId,setReplayId]=useState('');
  const [run,setRun]=useState<Run|null>(null);
  const [events,setEvents]=useState<Event[]>([]);
  const [report,setReport]=useState<Report|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');

  const canCreate=question.trim()!==''&&!busy&&(mode==='live'||replayId.trim()!=='');
  const runKey=`run:${dataset.id}:${dataset.version}:${question.trim()}:${segment}:${mode}:${replayId.trim()}`;

  const create=async()=>{
    const body:RunCreate={dataset_id:dataset.id,dataset_version:dataset.version,question:question.trim(),segment,mode,replay_run_id:mode==='replay'?replayId.trim():null};
    setBusy(true);setError('');
    try{
      const r=await api.createRun(body,stableKey(runKey));
      setRun(r);setEvents([]);setReport(null);
    }catch(e){setError(message(e));}
    finally{setBusy(false);}
  };
  const refresh=async()=>{
    if(!run)return;
    setBusy(true);setError('');
    try{
      const [r,ev]=await Promise.all([api.run(run.id),api.runEvents(run.id)]);
      setRun(r);setEvents(ev.items);
      if(r.report_ready){try{setReport(await api.report(run.id));}catch{}}
    }catch(e){setError(message(e));}
    finally{setBusy(false);}
  };
  const resume=async()=>{
    if(!run)return;
    setBusy(true);setError('');
    try{setRun(await api.resumeRun(run.id,{expected_run_status:'waiting_review',dataset_version:dataset.version}));}
    catch(e){setError(message(e));}
    finally{setBusy(false);}
  };

  return <section className="panel">
    <h2>研究任务</h2>
    <p className="hint">输入一条研究问题，系统编排多 Agent 在受控数据环境内检索、计算、核验并生成可追溯简报。Agent 编排依赖后端 DeepSeek，尚未启用时提交会提示尚待实现。</p>
    <div className="run-form">
      <label>研究问题<textarea value={question} onChange={e=>setQuestion(e.target.value)} rows={3} placeholder="例如：分析宁德时代 2025 年动力电池业务毛利率，并判断碳酸锂价格波动对其的影响"/></label>
      <div className="assumption-grid">
        <label>业务<select value={segment} onChange={e=>setSegment(e.target.value as 'power_battery'|'energy_storage')}><option value="power_battery">动力电池</option><option value="energy_storage">储能电池</option></select></label>
        <label>模式<select value={mode} onChange={e=>setMode(e.target.value as 'live'|'replay')}><option value="live">实时</option><option value="replay">回放</option></select></label>
        {mode==='replay'&&<label>回放 Run ID<input type="text" value={replayId} onChange={e=>setReplayId(e.target.value)} placeholder="指定已完成的 Run ID"/></label>}
      </div>
      <div className="review-actions"><button onClick={create} disabled={!canCreate}>{busy?'提交中…':'创建研究任务'}</button></div>
    </div>
    {error&&<p role="alert" className="error">{error}</p>}
    {run&&<div className="run-status">
      <p className="run-head">Run <span className="mono">{run.id}</span> · <span className={`badge ${runStatusClass(run.status)}`}>{runStatusLabels[run.status]}</span> · 模式 {run.mode==='live'?'实时':'回放'}{run.stale?' · 已过期':''}</p>
      {run.current_node&&<p className="muted">当前节点：{run.current_node}</p>}
      {run.missing_requirements.length>0&&<p className="error">缺少前置：{run.missing_requirements.join('；')}</p>}
      {run.error&&<p className="error">运行错误：{run.error.message}</p>}
      <div className="review-actions">
        <button onClick={refresh} disabled={busy}>刷新状态与事件</button>
        {run.status==='waiting_review'&&<button onClick={resume} disabled={busy}>继续运行</button>}
      </div>
      {events.length>0&&<div className="events"><h3>事件时间线</h3><ol className="trace">{events.map(e=><li key={e.seq}><strong>{eventTypeLabels[e.type]??e.type}</strong>（{e.node}）<span className="muted">{e.at}</span></li>)}</ol></div>}
      {report&&<div className="report"><h3>报告 · {report.title}</h3>
        <div className="review-actions">
          <a className="button-link" target="_blank" rel="noreferrer" href={`${BASE_URL}/api/v1/runs/${encodeURIComponent(run.id)}/report?format=markdown`}>导出 Markdown</a>
          <a className="button-link" target="_blank" rel="noreferrer" href={`${BASE_URL}/api/v1/runs/${encodeURIComponent(run.id)}/report?format=pdf`}>导出 PDF</a>
        </div>
        {report.claims.length>0&&<div className="table"><table><thead><tr><th>类型</th><th>结论</th><th>状态</th></tr></thead><tbody>{report.claims.map((c:Claim)=><tr key={c.id}><td><span className="badge s-extracted">{claimKindLabels[c.kind]??c.kind}</span></td><td>{c.text}</td><td>{c.review_status}</td></tr>)}</tbody></table></div>}
        {report.limitations.length>0&&<p className="muted">限制：{report.limitations.join('；')}</p>}
      </div>}
    </div>}
  </section>;
}
