import {useEffect,useState} from 'react';
import type {Dataset,Fact,Evidence,SourceAttachment} from './api/generated';
import {api,ApiError} from './api/client';
import {CONTRACT_VERSION} from './api/generated';
import {names,statusLabels} from './lib/format';
import {UploadPanel} from './components/UploadPanel';
import {FactTable} from './components/FactTable';
import {ReviewForm} from './components/ReviewForm';
import {ScenarioPanel} from './components/ScenarioPanel';
import {DiagnosticPanel} from './components/DiagnosticPanel';
import {RunPanel} from './components/RunPanel';

function message(e:unknown){return e instanceof ApiError?`${e.message}（${e.payload.error.code}，${e.payload.error.request_id}）`:e instanceof Error?e.message:'无法读取数据';}
const SEGMENTS=['all','group','power_battery','energy_storage'];
const STATUSES=['all','extracted','needs_review','verified','missing','conflict'];

function App(){
  const [datasets,setDatasets]=useState<Dataset[]>([]);
  const [selected,setSelected]=useState('');
  const [facts,setFacts]=useState<Fact[]>([]);
  const [segment,setSegment]=useState('all');
  const [statusF,setStatusF]=useState('all');
  const [view,setView]=useState<'review'|'diagnostic'|'research'|'run'>('review');
  const [reviewing,setReviewing]=useState<Fact|null>(null);
  const [evidence,setEvidence]=useState<Evidence|null>(null);
  const [evidenceLoading,setEvidenceLoading]=useState(false);
  const [evidenceError,setEvidenceError]=useState('');
  const [error,setError]=useState('');
  const [loading,setLoading]=useState(false);

  const loadFacts=(id:string,version:number)=>{
    const c=new AbortController();
    setLoading(true);setError('');setFacts([]);
    api.facts(id,version,{signal:c.signal}).then(v=>setFacts(v.items)).catch(e=>{if(!c.signal.aborted)setError(message(e));}).finally(()=>{if(!c.signal.aborted)setLoading(false);});
    return()=>c.abort();
  };

  useEffect(()=>{
    const c=new AbortController();
    setLoading(true);
    api.datasets(c.signal).then(v=>{setDatasets(v.items);setSelected(v.items[0]?.id??'');}).catch(e=>{if(!c.signal.aborted)setError(message(e));}).finally(()=>{if(!c.signal.aborted)setLoading(false);});
    return()=>c.abort();
  },[]);

  useEffect(()=>{
    if(!selected)return;
    const d=datasets.find(x=>x.id===selected);
    if(!d)return;
    return loadFacts(d.id,d.version);
  },[selected,datasets]);

  useEffect(()=>{setReviewing(null);setEvidence(null);setEvidenceError('');},[selected]);

  useEffect(()=>{
    setEvidence(null);
    setEvidenceError('');
    if(!reviewing||!reviewing.evidence_ids.length){setEvidenceLoading(false);return;}
    const c=new AbortController();
    setEvidenceLoading(true);
    api.evidence(reviewing.evidence_ids[0],c.signal)
      .then(setEvidence)
      .catch(e=>{if(!c.signal.aborted)setEvidenceError(message(e));})
      .finally(()=>{if(!c.signal.aborted)setEvidenceLoading(false);});
    return()=>c.abort();
  },[reviewing]);

  const onUploaded=(a:SourceAttachment)=>{setDatasets(prev=>prev.map(d=>d.id===a.dataset.id?a.dataset:d));};
  const refreshLatest=async(factId:string|null)=>{
    if(!selected)return;
    setLoading(true);setError('');
    try{
      const latest=await api.dataset(selected);
      const collection=await api.facts(latest.id,latest.version);
      setDatasets(prev=>prev.map(d=>d.id===latest.id?latest:d));
      setFacts(collection.items);
      setReviewing(factId?collection.items.find(f=>f.id===factId)??null:null);
    }catch(e){setError(message(e));}
    finally{setLoading(false);}
  };
  const onSaved=async(_fact:Fact)=>refreshLatest(null);
  const onReload=async()=>refreshLatest(reviewing?.id??null);

  const visible=facts.filter(f=>(segment==='all'||f.segment===segment)&&(statusF==='all'||f.status===statusF));
  const d=datasets.find(x=>x.id===selected);

  return <main>
    <header><div><p>链眼 · 契约 v{CONTRACT_VERSION}</p><h1>宁德时代研究工作台</h1></div><span>R3 上传·复核·情景</span></header>
    <aside className="notice">上传年报后由后端提取候选事实，需人工对照原文复核后方可标记「已复核」。情景研究仅使用已复核基线，结果为条件情景，不构成预测或投资建议。</aside>
    <UploadPanel datasetId={selected} onUploaded={onUploaded}/>
    <nav className="tabs">
      <button className={view==='review'?'tab active':'tab'} onClick={()=>setView('review')}>数据复核</button>
      <button className={view==='diagnostic'?'tab active':'tab'} onClick={()=>setView('diagnostic')}>财务诊断</button>
      <button className={view==='research'?'tab active':'tab'} onClick={()=>setView('research')}>情景研究</button>
      <button className={view==='run'?'tab active':'tab'} onClick={()=>setView('run')}>研究任务</button>
    </nav>
    <section className="controls">
      <label>数据包<select value={selected} onChange={e=>setSelected(e.target.value)}>{datasets.map(x=><option key={x.id} value={x.id}>{x.name} · 版本{x.version}</option>)}</select></label>
      {view==='review'&&<label>业务<select value={segment} onChange={e=>setSegment(e.target.value)}>{SEGMENTS.map(s=><option key={s} value={s}>{s==='all'?'全部':names[s]}</option>)}</select></label>}
      {view==='review'&&<label>状态<select value={statusF} onChange={e=>setStatusF(e.target.value)}>{STATUSES.map(s=><option key={s} value={s}>{s==='all'?'全部':statusLabels[s]}</option>)}</select></label>}
    </section>
    {error&&<p role="alert" className="error">{error}</p>}{loading&&<p role="status">正在读取…</p>}
    {!loading&&!datasets.length&&!error&&<p>暂无数据包。</p>}
    {view==='review'
      ?<section className="panel"><h2>财务事实复核</h2>{reviewing
        ?<ReviewForm key={`${reviewing.id}:${reviewing.revision??1}`} fact={reviewing} evidence={evidence} evidenceLoading={evidenceLoading} evidenceError={evidenceError} onClose={()=>setReviewing(null)} onSaved={onSaved} onReload={onReload}/>
        :<FactTable facts={visible} onSelect={setReviewing} onEvidence={setReviewing}/>}</section>
      :view==='diagnostic'
        ?<DiagnosticPanel facts={facts}/>
        :view==='research'
          ?(d?<ScenarioPanel dataset={d} facts={facts}/>:<p>请先选择数据包。</p>)
          :(d?<RunPanel dataset={d}/>:<p>请先选择数据包。</p>)}
  </main>;
}
export default App;
