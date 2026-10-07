import {useState} from 'react';
import type {Fact} from '../api/generated';
import {names,metrics,fmtAmount} from '../lib/format';
import {diagnosticComparison,metricMatchesQuery} from '../lib/diagnostic';

// 展示口径分组：流量类（利润表/现金流量）与余额类（资产负债表）
const FLOW=['revenue','cost_of_sales','reported_gross_margin','parent_net_profit','parent_adjusted_net_profit','operating_cash_flow'];
const STOCK=['total_assets','parent_equity','inventory','accounts_receivable'];
// 信号卡片关注的指标与说明
const SIGNAL_ITEMS:[string,string,string][]=[
  ['revenue','收入变化','收入同比为核查信号，需结合业务拆分判断'],
  ['reported_gross_margin','毛利率变化','毛利率变动需结合成本与售价传导判断'],
  ['inventory','存货变化','存货上升仅作核查信号，不直接定性积压'],
  ['accounts_receivable','应收变化','应收上升仅作核查信号，需结合账期判断'],
];

function fmtValue(f:Fact):string{
  if(f.status==='missing'||f.value===null)return f.missing_reason?`缺失·${f.missing_reason}`:'缺失';
  return fmtAmount(f.value,f.unit);
}

export function DiagnosticPanel({facts}:{facts:Fact[]}){
  const [segment,setSegment]=useState<'group'|'power_battery'|'energy_storage'>('group');
  const [query,setQuery]=useState('');
  const reviewed=facts.filter(f=>f.segment===segment&&(f.status==='verified'||f.status==='missing'));
  const byYear=(metric:string):Record<string,Fact[]>=>{
    const out:Record<string,Fact[]>={};
    for(const f of reviewed)if(f.metric===metric){
      const year=(f.period_end??'').slice(0,4);
      (out[year]??=[]).push(f);
    }
    return out;
  };
  const yearValue=(items:Fact[]|undefined)=>!items?.length?'—':items.length>1?'口径歧义·请复核':fmtValue(items[0]);

  // 柱状图：取某指标 2024/2025 的规范值，按相对高度绘制
  const renderBars=(metric:Fact['metric'])=>{
    if(!metricMatchesQuery(metrics[metric]??metric,query))return null;
    const comparison=diagnosticComparison(facts,segment,metric);
    if(!comparison||comparison.previousValue<0||comparison.currentValue<0)return null;
    const {previous:f24,current:f25,previousValue:v24,currentValue:v25}=comparison;
    if(v24===0&&v25===0)return null;
    const max=Math.max(v24,v25,1);
    const barH=(v:number)=>v===0?0:Math.max(4,Math.round(v/max*140));
    const show=(f:Fact)=>fmtAmount(f.value,f.unit);
    return <div className="bar-chart" role="img" aria-label={`${metrics[metric]??metric} 2024 与 2025 对比`}>
      <div className="bar-col"><span className="bar-value">{show(f24)}</span><div className="bar bar-prev" style={{height:barH(v24)}}/><span className="bar-label">2024</span></div>
      <div className="bar-col"><span className="bar-value">{show(f25)}</span><div className="bar" style={{height:barH(v25)}}/><span className="bar-label">2025</span></div>
    </div>;
  };

  // 信号卡片：仅做方向性对比（不计算权威同比），并附核查说明
  const signalOf=(metric:string)=>{
    if(!metricMatchesQuery(metrics[metric]??metric,query))return null;
    return diagnosticComparison(facts,segment,metric as Fact['metric'])?.direction??null;
  };
  const signalDir=Object.fromEntries(SIGNAL_ITEMS.map(([m])=>[m,signalOf(m)]));
  const hasSignal=Object.values(signalDir).some(Boolean);
  const revenueBars=renderBars('revenue');
  const marginBars=renderBars('reported_gross_margin');

  const renderGroup=(title:string,list:string[])=>(
    <div className="table"><table>
      <thead><tr><th>{title}</th><th>2024</th><th>2025</th><th>口径说明</th></tr></thead>
      <tbody>{list.filter(m=>metricMatchesQuery(metrics[m]??m,query)).map(m=>{
        const y=byYear(m);const f2024=y['2024'];const f2025=y['2025'];
        if(!f2024&&!f2025)return null;
        const sample=f2025?.[0]??f2024?.[0];
        return <tr key={m}>
          <td>{metrics[m]}</td>
          <td>{yearValue(f2024)}</td>
          <td>{yearValue(f2025)}</td>
          <td className="muted">{sample?.period_kind==='point_in_time'?'期末余额':'全年流量'}{m==='reported_gross_margin'?'·披露值':''}</td>
        </tr>;
      })}</tbody>
    </table></div>
  );

  return <section className="panel">
    <h2>财务诊断</h2>
    <p className="hint">对比 2024 与 2025 已复核财务事实。本页只展示原始披露值，同比、比率等权威计算由后端财务服务给出；存货/应收变化仅作核查信号，不自动判定积压或舞弊。</p>
    <section className="controls">
      <label>业务<select value={segment} onChange={e=>setSegment(e.target.value as 'group'|'power_battery'|'energy_storage')}>
        <option value="group">集团</option>
        <option value="power_battery">动力电池</option>
        <option value="energy_storage">储能电池</option>
      </select></label>
      <label>搜索指标<input type="search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="按指标名筛选（如 收入/存货）"/></label>
    </section>
    {!reviewed.length?<p>该业务暂无已复核事实，请先在「数据复核」页完成人工复核。</p>:<>
      {hasSignal&&<div className="signal-cards">{SIGNAL_ITEMS.map(([metric,label,note])=>{
        const dir=signalDir[metric];
        if(!dir)return null;
        const icon=dir==='up'?'↑':dir==='down'?'↓':'→';
        const text=dir==='up'?'上升':dir==='down'?'下降':'持平';
        return <div key={metric} className={`signal-card ${dir==='up'?'signal-up':dir==='down'?'signal-down':'signal-flat'}`}><span className="signal-name">{label}</span><span className="signal-dir">{icon} {text}</span><span className="signal-note">{note}</span></div>;
      })}</div>}
      {revenueBars&&<><h3>收入对比</h3>{revenueBars}</>}
      {marginBars&&<><h3>毛利率对比</h3>{marginBars}</>}
      {renderGroup('经营指标',FLOW)}
      {renderGroup('资产负债指标',STOCK)}
    </>}
    <aside className="notice">核查提示：① 存货、应收账款增长是核查信号，需结合周转与账期进一步判断，不直接定性为积压或舞弊；② 经营现金流与归母净利润的比值须披露口径差异后再比较；③ 扣非差额 = 归母净利润 − 扣非归母净利润，不自动等同于非经常性损益。</aside>
  </section>;
}
