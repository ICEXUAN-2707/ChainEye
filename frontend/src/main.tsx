import React,{useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {api,BASE_URL,ApiError} from './api/client';
import {CONTRACT_VERSION} from './api/generated';
import type {Dataset,Fact,Evidence} from './api/generated';
import './style.css';
const names:Record<string,string>={group:'集团',power_battery:'动力电池',energy_storage:'储能电池'};
const metrics:Record<string,string>={revenue:'营业收入',cost_of_sales:'营业成本',reported_gross_margin:'披露毛利率',parent_net_profit:'归母净利润',parent_adjusted_net_profit:'扣非归母净利润',operating_cash_flow:'经营现金流',total_assets:'总资产',parent_equity:'归母权益',inventory:'存货',accounts_receivable:'应收账款'};
function show(f:Fact){
 if(f.value===null)return '缺失';
 // Financial arithmetic stays server-side. Display exact raw amount to avoid float loss.
 return `${f.raw_value ?? f.value} ${f.raw_unit==='percent'?'%':'千元'}`;
}
function message(e:unknown){return e instanceof ApiError?`${e.message}（${e.payload.error.code}，${e.payload.error.request_id}）`:e instanceof Error?e.message:'无法读取数据';}
function App(){
 const [datasets,setDatasets]=useState<Dataset[]>([]),[selected,setSelected]=useState(''),[facts,setFacts]=useState<Fact[]>([]),[evidence,setEvidence]=useState<Evidence|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false),[segment,setSegment]=useState('all');
 useEffect(()=>{const c=new AbortController();setLoading(true);api.datasets(c.signal).then(v=>{setDatasets(v.items);setSelected(v.items[0]?.id??'');}).catch(e=>{if(!c.signal.aborted)setError(message(e));}).finally(()=>{if(!c.signal.aborted)setLoading(false);});return()=>c.abort();},[]);
 useEffect(()=>{if(!selected)return;const c=new AbortController();const d=datasets.find(d=>d.id===selected);if(!d)return;setLoading(true);setError('');setFacts([]);setEvidence(null);api.facts(d.id,d.version,c.signal).then(v=>setFacts(v.items)).catch(e=>{if(!c.signal.aborted)setError(message(e));}).finally(()=>{if(!c.signal.aborted)setLoading(false);});return()=>c.abort();},[selected,datasets]);
 const inspect=async(f:Fact)=>{setError('');setEvidence(null);try{setEvidence(await api.evidence(f.evidence_ids[0]));}catch(e){setError(message(e));}};
 return <main><header><div><p>链眼 · 契约 v{CONTRACT_VERSION}</p><h1>宁德时代研究工作台</h1></div><span>R1 本地骨架</span></header><aside className="notice">当前展示人工核对样本。上传提取、情景接口和Agent尚待后续轮次实现；不会将样本展示作为自动分析结果。</aside>
 <section className="controls"><label>数据包<select value={selected} onChange={e=>setSelected(e.target.value)}>{datasets.map(d=><option key={d.id} value={d.id}>{d.name} · 版本{d.version}</option>)}</select></label><label>业务<select value={segment} onChange={e=>setSegment(e.target.value)}><option value="all">全部</option>{Object.entries(names).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label></section>
 {error&&<p role="alert" className="error">{error}</p>}{loading&&<p role="status">正在读取…</p>}
 {!loading&&!datasets.length&&!error&&<p>暂无数据包。</p>}
 <div className="grid"><section><h2>财务基线</h2><p>金额按原始千元展示，日期与业务分别保存；本页不执行财务计算。</p><div className="table"><table><thead><tr><th>业务</th><th>指标</th><th>期间</th><th>原值</th><th>证据</th></tr></thead><tbody>{facts.filter(f=>segment==='all'||f.segment===segment).map(f=><tr key={f.id}><td>{names[f.segment]}</td><td>{metrics[f.metric]}</td><td>{f.period_kind==='point_in_time'?f.period_end:f.period_start+' 至 '+f.period_end}</td><td>{show(f)}</td><td><button disabled={!f.evidence_ids.length} onClick={()=>inspect(f)}>查看原文</button></td></tr>)}</tbody></table></div>{!loading&&!facts.length&&<p>该版本暂无事实记录。</p>}</section>
 <section className="evidence"><h2>原文证据</h2>{evidence?<><p>PDF第{evidence.pdf_page}页 · 印刷页码{evidence.printed_page}</p><pre>{evidence.excerpt}</pre><a target="_blank" rel="noreferrer" href={`${BASE_URL}/api/v1/sources/${encodeURIComponent(evidence.source_id)}/content#page=${evidence.pdf_page}`}>打开原始PDF</a><p>证据高亮坐标：{evidence.bbox?'已定位数值':'仅定位整页'}</p></>:<p>选择一条事实查看对应原文。</p>}<h2>后续开发</h2><ul><li>R2 上传与字段复核</li><li>R3 财务与情景计算</li><li>R4 DeepSeek及证据分析</li></ul></section></div></main>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
