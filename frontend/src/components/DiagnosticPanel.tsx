import {useState} from 'react';
import type {Fact} from '../api/generated';
import {names,metrics,fmtAmount} from '../lib/format';

// 展示口径分组：流量类（利润表/现金流量）与余额类（资产负债表）
const FLOW=['revenue','cost_of_sales','reported_gross_margin','parent_net_profit','parent_adjusted_net_profit','operating_cash_flow'];
const STOCK=['total_assets','parent_equity','inventory','accounts_receivable'];

function fmtValue(f:Fact):string{
  if(f.status==='missing'||f.value===null)return f.missing_reason?`缺失·${f.missing_reason}`:'缺失';
  return fmtAmount(f.value,f.unit);
}

export function DiagnosticPanel({facts}:{facts:Fact[]}){
  const [segment,setSegment]=useState<'group'|'power_battery'|'energy_storage'>('group');
  const verified=facts.filter(f=>f.segment===segment&&f.status==='verified');
  const byYear=(metric:string):Record<string,Fact>=>{
    const out:Record<string,Fact>={};
    for(const f of verified)if(f.metric===metric)out[(f.period_end??'').slice(0,4)]=f;
    return out;
  };
  const renderGroup=(title:string,list:string[])=>(
    <div className="table"><table>
      <thead><tr><th>{title}</th><th>2024</th><th>2025</th><th>口径说明</th></tr></thead>
      <tbody>{list.map(m=>{
        const y=byYear(m);const f2024=y['2024'];const f2025=y['2025'];
        if(!f2024&&!f2025)return null;
        return <tr key={m}>
          <td>{metrics[m]}</td>
          <td>{f2024?fmtValue(f2024):'—'}</td>
          <td>{f2025?fmtValue(f2025):'—'}</td>
          <td className="muted">{f2025?.period_kind==='point_in_time'?'期末余额':'全年流量'}{m==='reported_gross_margin'?'·披露值':''}</td>
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
    </section>
    {!verified.length?<p>该业务暂无已复核事实，请先在「数据复核」页完成人工复核。</p>:<>
      {renderGroup('经营指标',FLOW)}
      {renderGroup('资产负债指标',STOCK)}
    </>}
    <aside className="notice">核查提示：① 存货、应收账款增长是核查信号，需结合周转与账期进一步判断，不直接定性为积压或舞弊；② 经营现金流与归母净利润的比值须披露口径差异后再比较；③ 扣非差额 = 归母净利润 − 扣非归母净利润，不自动等同于非经常性损益。</aside>
  </section>;
}
