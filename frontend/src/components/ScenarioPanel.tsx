import {useState} from 'react';
import type {Dataset, Fact, ScenarioRequest, ScenarioResult} from '../api/generated';
import {api,ApiError} from '../api/client';
import {names,fmtAmount,fmtPp} from '../lib/format';

function message(e:unknown):string{
  if(e instanceof ApiError){
    if(e.code==='NOT_IMPLEMENTED')return '情景接口尚待实现（后端 R3 未完成）。';
    if(e.code==='IDEMPOTENCY_CONFLICT')return '相同请求已存在结果，请稍后重试。';
    return `${e.message}（${e.code}，${e.requestId}）`;
  }
  return e instanceof Error?e.message:'情景计算失败';
}

const MODEL_VERSION='static-gross-profit-v1';

export function ScenarioPanel({dataset,facts}:{dataset:Dataset;facts:Fact[]}){
  const [segment,setSegment]=useState<'power_battery'|'energy_storage'>('power_battery');
  const [s,setS]=useState('1');
  const [x,setX]=useState('-0.1');
  const [k,setK]=useState('0.5');
  const [basis,setBasis]=useState<'user_assumption'|'research_assumption'>('research_assumption');
  const [acknowledged,setAcknowledged]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [result,setResult]=useState<ScenarioResult|null>(null);

  const revenue=facts.find(f=>f.segment===segment&&f.metric==='revenue'&&f.status==='verified');
  const cost=facts.find(f=>f.segment===segment&&f.metric==='cost_of_sales'&&f.status==='verified');
  const baselineReady=!!revenue&&!!cost;
  const canRun=baselineReady&&acknowledged&&s.trim()!==''&&x.trim()!==''&&k.trim()!==''&&!busy;

  const run=async()=>{
    if(!revenue||!cost||!canRun)return;
    const body:ScenarioRequest={
      dataset_id:dataset.id,
      dataset_version:dataset.version,
      revenue_fact_id:revenue.id,
      cost_fact_id:cost.id,
      revenue_revision:revenue.revision??1,
      cost_revision:cost.revision??1,
      model_version:MODEL_VERSION,
      assumptions:{
        cost_exposure:s.trim(),
        effective_price_shock:x.trim(),
        customer_pass_through:k.trim(),
        basis,
        acknowledged:true,
      },
    };
    setBusy(true);setError('');setResult(null);
    try{setResult(await api.createScenario(body,crypto.randomUUID()));}
    catch(e){setError(message(e));}
    finally{setBusy(false);}
  };

  return <section className="panel">
    <h2>情景研究</h2>
    <p className="hint">基于已复核的同口径「收入 + 营业成本」基线，设置成本暴露 s、价格冲击 x、客户传导 k 三个研究假设，运行静态情景。结果仅为条件情景，不构成预测或投资建议。</p>
    <section className="controls">
      <label>业务<select value={segment} onChange={e=>setSegment(e.target.value as 'power_battery'|'energy_storage')}>
        <option value="power_battery">动力电池</option>
        <option value="energy_storage">储能电池</option>
      </select></label>
    </section>
    {!baselineReady?<p className="error">「{names[segment]}」业务尚无已复核的「收入」与「营业成本」基线，无法运行情景。请先在「数据复核」页完成人工复核。</p>:<>
      <p className="muted baseline">基线：收入 {fmtAmount(revenue.value,revenue.unit)}（revision {revenue.revision??1}）· 营业成本 {fmtAmount(cost.value,cost.unit)}（revision {cost.revision??1}）</p>
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
      <div className="review-actions"><button onClick={run} disabled={!canRun}>{busy?'计算中…':'运行情景'}</button></div>
      {error&&<p role="alert" className="error">{error}</p>}
      {result&&<div className="scenario-result">
        <p className="muted">模型 {result.model_version} · 假设编号 {result.assumption_id}</p>
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
      </div>}
    </>}
  </section>;
}
