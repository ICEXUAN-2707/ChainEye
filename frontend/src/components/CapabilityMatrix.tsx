import type {CapabilityCollection,CapabilityItem} from '../api/generated';

const moduleLabels:Record<CapabilityItem['module_id'],string>={M1:'盈利增长',M2:'现金运营',M3:'扩产资金',M4:'行业竞争',M5:'产业链情景'};
const statusLabels:Record<CapabilityItem['status'],string>={ready:'可运行',needs_review:'待复核',missing_data:'缺少数据',unsupported:'暂不支持',failed:'不可运行'};

function list(values:string[],empty='无'){
  return values.length?<ul>{values.map((value,index)=><li key={`${value}:${index}`}>{value}</li>)}</ul>:<span className="muted">{empty}</span>;
}

export function CapabilityMatrix({capabilities,loading}:{capabilities:CapabilityCollection|null;loading:boolean}){
  return <section className="panel capability-panel">
    <div className="section-heading"><div><h2>能力矩阵</h2><p className="hint">能力状态绑定 Dataset、企业配置和行业配置版本，不代表所有企业均已支持。</p></div>{capabilities&&<span className="mono">v{capabilities.dataset_version} · profile v{capabilities.industry_profile_version}</span>}</div>
    {loading?<p role="status">正在读取能力矩阵…</p>:capabilities?<div className="capability-table-wrap"><table className="capability-table"><thead><tr><th>模块</th><th>状态</th><th>原因</th><th>必需输入</th><th>缺失输入</th><th>证据缺口</th><th>支持动作</th></tr></thead><tbody>
      {capabilities.items.map(item=><tr key={item.module_id}><th>{item.module_id} · {moduleLabels[item.module_id]}</th><td><span className={`status-pill capability-${item.status}`}>{statusLabels[item.status]}</span></td><td><code>{item.reason_code}</code></td><td>{list(item.required_inputs)}</td><td>{list(item.missing_inputs)}</td><td>{list(item.evidence_gaps)}</td><td>{list(item.supported_actions)}</td></tr>)}
    </tbody></table></div>:<p className="muted">请选择 Dataset 后读取能力状态。</p>}
  </section>;
}
