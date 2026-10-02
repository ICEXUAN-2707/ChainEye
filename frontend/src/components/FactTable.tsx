import type {Fact} from '../api/generated';
import {names,metrics,statusLabels,statusClass,fmtAmount,fmtRaw,periodOf} from '../lib/format';

export function FactTable({facts,onSelect,onEvidence}:{facts:Fact[];onSelect:(f:Fact)=>void;onEvidence:(f:Fact)=>void}){
  if(!facts.length)return <p>该版本暂无事实记录。</p>;
  return <div className="table"><table>
    <thead><tr><th>业务</th><th>指标</th><th>期间</th><th>原值</th><th>规范值</th><th>状态</th><th>证据</th></tr></thead>
    <tbody>{facts.map(f=>(
      <tr key={f.id} onClick={()=>onSelect(f)} className="clickable">
        <td>{names[f.segment]}</td>
        <td>{metrics[f.metric]}</td>
        <td>{periodOf(f)}</td>
        <td>{fmtRaw(f.raw_value,f.raw_unit)}</td>
        <td>{f.status==='missing'?(f.missing_reason?`缺失·${f.missing_reason}`:'缺失'):fmtAmount(f.value,f.unit)}</td>
        <td><span className={`badge ${statusClass[f.status]}`}>{statusLabels[f.status]}</span></td>
        <td><button disabled={!f.evidence_ids.length} onClick={e=>{e.stopPropagation();onEvidence(f);}}>查看原文</button></td>
      </tr>
    ))}</tbody>
  </table></div>;
}
