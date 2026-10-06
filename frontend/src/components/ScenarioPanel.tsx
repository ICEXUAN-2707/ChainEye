import {useEffect,useMemo,useRef,useState} from 'react';
import type {Dataset,Fact,ScenarioRequest,ScenarioResult,Calculation} from '../api/generated';
import {api,ApiError} from '../api/client';
import {names,fmtAmount,fmtPp,fmtFormula,fmtAssumptionKey,fmtFactRevisions} from '../lib/format';
import {pairBaseline,scenarioKey} from '../lib/scenario';

const MODEL_VERSION='static-gross-profit-v1';
const GRID_S=['0.05','0.10','0.20'];
const GRID_X=['-0.20','0','0.20'];
const GRID_K=['0','0.5','1'];

function message(e:unknown):string{
  if(e instanceof ApiError){
    const reason=e.details&&typeof e.details==='object'&&'reason' in e.details?String((e.details as Record<string,unknown>).reason):'';
    if(e.code==='INVALID_INPUT'&&reason==='IDEMPOTENCY_KEY_REUSED')return '本次请求与该幂等键原先对应的参数不一致，请刷新数据后重试。';
    if(e.code==='NOT_IMPLEMENTED')return '当前后端未启用情景接口，请确认已启动 R3 版本。';
    return `${e.message}（${e.code}，${e.requestId}）`;
  }
  return e instanceof Error?e.message:'情景计算失败';
}

function fmtCalc(c:Calculation):string{
  if(c.status==='not_computable')return '不可计算'+(c.reason?`（${c.reason}）`:'');
  if(c.value===null)return '—';
  return c.unit==='CNY'?fmtAmount(c.value,'CNY'):c.unit==='ratio'?fmtAmount(c.value,'ratio'):fmtPp(c.value);
}

export function ScenarioPanel({dataset,facts}:{dataset:Dataset;facts:Fact[]}){
  const [segment,setSegment]=useState<'power_battery'|'energy_storage'>('power_battery');
  const [year,setYear]=useState('');
  const [s,setS]=useState('1');
  const [x,setX]=useState('-0.1');
  const [k,setK]=useState('0.5');
  const [basis,setBasis]=useState<'user_assumption'|'research_assumption'>('research_assumption');
  const [acknowledged,setAcknowledged]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [result,setResult]=useState<ScenarioResult|null>(null);
  const [grid,setGrid]=useState<Array<{s:string;x:string;k:string;r:ScenarioResult}>|null>(null);
  const [gridProgress,setGridProgress]=useState<{completed:number;total:number}|null>(null);
  const [calcs,setCalcs]=useState<Record<string,Calculation>>({});
  const [staleNotice,setStaleNotice]=useState(false);

  // 同口径配对，最新年度在前
  const pairs=useMemo(()=>pairBaseline(facts,segment),[facts,segment]);
  const selected=pairs.find(p=>p.periodEnd===year)??pairs[0];
  const revenue=selected?.revenue;const cost=selected?.cost;
  const baselineReady=!!revenue&&!!cost;

  // 切业务时回退到最新年度
  useEffect(()=>{setYear('');},[segment]);

  const genRef=useRef(0);
  // 基线/参数/版本/basis 变化时清除旧结果并失效在途请求，避免旧结果或旧异步响应挂在新的输入下（spec：旧结果过期）
  useEffect(()=>{
    genRef.current++;
    setStaleNotice(result!==null||grid!==null);
    setResult(null);setGrid(null);setGridProgress(null);setCalcs({});setBusy(false);setError('');
  },[dataset.id,dataset.version,segment,revenue?.id,cost?.id,revenue?.revision,cost?.revision,s,x,k,basis]);

  const keyInput=(sv:string,xv:string,kv:string)=>({dataset_id:dataset.id,dataset_version:dataset.version,revenue_fact_id:revenue?.id??'',revenue_revision:revenue?.revision??1,cost_fact_id:cost?.id??'',cost_revision:cost?.revision??1,cost_exposure:sv,effective_price_shock:xv,customer_pass_through:kv,basis});
  const buildRequest=(sv:string,xv:string,kv:string):ScenarioRequest|null=>{
    if(!revenue||!cost)return null;
    return {dataset_id:dataset.id,dataset_version:dataset.version,revenue_fact_id:revenue.id,cost_fact_id:cost.id,revenue_revision:revenue.revision??1,cost_revision:cost.revision??1,model_version:MODEL_VERSION,assumptions:{cost_exposure:sv,effective_price_shock:xv,customer_pass_through:kv,basis,acknowledged:true}};
  };
  const canRun=baselineReady&&acknowledged&&s.trim()!==''&&x.trim()!==''&&k.trim()!==''&&!busy;

  const run=async()=>{
    const body=buildRequest(s.trim(),x.trim(),k.trim());
    if(!body)return;
    const gen=genRef.current;
    setBusy(true);setError('');
    try{
      const r=await api.createScenario(body,scenarioKey(keyInput(s.trim(),x.trim(),k.trim())));
      if(gen===genRef.current){setResult(r);setCalcs({});setStaleNotice(false);}
    }catch(e){if(gen===genRef.current)setError(message(e));}
    finally{if(gen===genRef.current)setBusy(false);}
  };
  const runGrid=async()=>{
    if(!canRun)return;
    const gen=genRef.current;
    setBusy(true);setError('');setGrid([]);setGridProgress({completed:0,total:27});
    try{
      const rows:Array<{s:string;x:string;k:string;r:ScenarioResult}>=[];
      for(const sv of GRID_S)for(const xv of GRID_X)for(const kv of GRID_K){
        if(gen!==genRef.current)return;
        const body=buildRequest(sv,xv,kv)!;
        const r=await api.createScenario(body,scenarioKey(keyInput(sv,xv,kv)));
        if(gen!==genRef.current)return;
        rows.push({s:sv,x:xv,k:kv,r});
        setGrid([...rows]);setGridProgress({completed:rows.length,total:27});
      }
      if(gen===genRef.current)setStaleNotice(false);
    }catch(e){if(gen===genRef.current)setError(message(e));}
    finally{if(gen===genRef.current)setBusy(false);}
  };
  const openCalc=async(id:string)=>{
    if(calcs[id])return;
    const gen=genRef.current;
    try{
      const c=await api.calculation(id);
      if(gen===genRef.current)setCalcs(prev=>({...prev,[id]:c}));
    }catch(e){if(gen===genRef.current)setError(message(e));}
  };

  return <section className="panel">
    <h2>情景研究</h2>
    <p className="hint">基于已复核的同口径「收入 + 营业成本」基线，设置成本暴露 s、价格冲击 x、客户传导 k 三个研究假设，运行静态情景。结果仅为条件情景，不构成预测或投资建议。</p>
    <section className="controls">
      <label>业务<select value={segment} onChange={e=>setSegment(e.target.value as 'power_battery'|'energy_storage')}>
        <option value="power_battery">动力电池</option>
        <option value="energy_storage">储能电池</option>
      </select></label>
      {pairs.length>1&&<label>基线年度<select value={year||pairs[0].periodEnd} onChange={e=>setYear(e.target.value)}>
        {pairs.map(p=><option key={p.periodEnd} value={p.periodEnd}>{p.periodEnd.slice(0,4)}</option>)}
      </select></label>}
    </section>
    {!baselineReady?<p className="error">「{names[segment]}」业务尚无已复核的「收入」与「营业成本」基线，无法运行情景。请先在「数据复核」页完成人工复核。</p>:<>
      <p className="muted baseline">基线（{selected.periodEnd.slice(0,4)} 年度）：收入 {fmtAmount(revenue.value,revenue.unit)}（revision {revenue.revision??1}）· 营业成本 {fmtAmount(cost.value,cost.unit)}（revision {cost.revision??1}）</p>
      <div className="assumption-grid">
        <label>成本暴露 s ∈ [0,1]<input type="text" value={s} onChange={e=>setS(e.target.value)} inputMode="decimal"/></label>
        <label>价格冲击 x ∈ [-0.5,0.5]<input type="text" value={x} onChange={e=>setX(e.target.value)} inputMode="decimal"/></label>
        <label>客户传导 k ∈ [0,1]<input type="text" value={k} onChange={e=>setK(e.target.value)} inputMode="decimal"/></label>
        <label>假设来源<select value={basis} onChange={e=>setBasis(e.target.value as 'user_assumption'|'research_assumption')}>
          <option value="research_assumption">研究假设</option>
          <option value="user_assumption">用户假设</option>
        </select></label>
      </div>
      <label className="check"><input type="checkbox" checked={acknowledged} onChange={e=>setAcknowledged(e.target.checked)}/> 我确认以上为研究假设，非宁德时代实测参数</label>
      <div className="review-actions">
        <button onClick={run} disabled={!canRun}>{busy?'计算中…':'运行情景'}</button>
        <button onClick={runGrid} disabled={!canRun}>运行 27 格点敏感性</button>
      </div>
      {staleNotice&&<p role="status" className="stale">基线或假设已经变化，上一结果已过期且不再展示，请重新运行。</p>}
      {error&&<p role="alert" className="error">{error}</p>}
      {result&&<div className="scenario-result">
        <p className="muted">模型 {result.model_version} · 假设编号 {result.assumption_id} · 数据包版本 v{result.dataset_version}</p>
        <div className="table"><table>
          <thead><tr><th>指标</th><th>基线</th><th>情景</th><th>变化</th></tr></thead>
          <tbody>
            <tr><td>收入</td><td>{fmtAmount(result.baseline.revenue,'CNY')}</td><td>{fmtAmount(result.outputs.revenue,'CNY')}</td><td>—</td></tr>
            <tr><td>营业成本</td><td>{fmtAmount(result.baseline.cost_of_sales,'CNY')}</td><td>{fmtAmount(result.outputs.cost_of_sales,'CNY')}</td><td>{fmtAmount(result.outputs.delta_cost,'CNY')}</td></tr>
            <tr><td>毛利润</td><td>{fmtAmount(result.baseline.gross_profit,'CNY')}</td><td>{fmtAmount(result.outputs.gross_profit,'CNY')}</td><td>{fmtAmount(result.outputs.delta_gross_profit,'CNY')}</td></tr>
            <tr><td>毛利率</td><td>{fmtAmount(result.baseline.gross_margin,'ratio')}</td><td>{fmtAmount(result.outputs.gross_margin,'ratio')}</td><td>{fmtPp(result.outputs.delta_gross_margin_pp)}</td></tr>
          </tbody>
        </table></div>
        {result.limitations.length>0&&<p className="muted">限制：{result.limitations.join('；')}</p>}
        <h3>计算溯源（{result.calculation_ids.length} 条）</h3>
        <ul className="calc-list">{result.calculation_ids.map(id=>{
          const c=calcs[id];
          return <li key={id}>{c?<div><strong>{fmtFormula(c.formula_id)}</strong> · <span className="mono">{c.formula_id} v{c.formula_version}</span> → {fmtCalc(c)}<span className="muted mono">Calculation {c.id}</span><span className="muted mono">输入：{fmtFactRevisions(c.input_fact_ids,c.input_revisions)}</span>{Object.entries(c.assumption_snapshot).length?<span className="muted">参数 {Object.entries(c.assumption_snapshot).map(([k,v])=>`${fmtAssumptionKey(k)} ${v}`).join('，')}</span>:null}</div>:<button className="inline" onClick={()=>void openCalc(id)}>查看计算 <span className="mono">{id}</span></button>}</li>;
        })}</ul>
      </div>}
      {grid&&<div className="scenario-result">
        <h3>敏感性网格（27 组合，s×x×k）</h3>
        <p className="muted">模型 {MODEL_VERSION} · 横轴：价格冲击 x（%）· 纵轴：成本暴露 s（%）· 单元格：情景毛利率 / 毛利率变化（pp）</p>
        {gridProgress&&<p role="status" className="muted">已完成 {gridProgress.completed}/{gridProgress.total} 个格点{gridProgress.completed<gridProgress.total?'；中断时保留已完成结果。':''}</p>}
        {GRID_K.map(kv=><div className="sensitivity" key={kv}>
          <h4>固定客户传导 k = {fmtAmount(kv,'ratio')}</h4>
          <div className="table"><table>
            <thead><tr><th>成本暴露 s \ 价格冲击 x</th>{GRID_X.map(xv=><th key={xv}>{fmtAmount(xv,'ratio')}</th>)}</tr></thead>
            <tbody>{GRID_S.map(sv=><tr key={sv}><th>{fmtAmount(sv,'ratio')}</th>{GRID_X.map(xv=>{
              const cell=grid.find(g=>g.s===sv&&g.x===xv&&g.k===kv);
              return <td key={xv}>{cell?<>{fmtAmount(cell.r.outputs.gross_margin,'ratio')}<span className="muted">{fmtPp(cell.r.outputs.delta_gross_margin_pp)}</span></>:busy?'计算中…':'未完成'}</td>;
            })}</tr>)}</tbody>
          </table></div>
        </div>)}
      </div>}
    </>}
  </section>;
}
