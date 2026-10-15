import {useEffect,useRef,useState} from 'react';
import type {CapabilityCollection,CompanyProfile,Dataset,DatasetCreate,Evidence,Fact,IdentityCandidate,IdentityConfirmation,SourceAttachment} from './api/generated';
import {api,ApiError} from './api/client';
import {CONTRACT_VERSION} from './api/generated';
import {names,statusLabels} from './lib/format';
import {shortcutView,type WorkbenchView} from './lib/navigation';
import {hasIdentityBlocker,loadWorkbenchSnapshot,snapshotKey} from './lib/workbench';
import {DatasetPanel} from './components/DatasetPanel';
import {UploadPanel} from './components/UploadPanel';
import {IdentityPanel} from './components/IdentityPanel';
import {CapabilityMatrix} from './components/CapabilityMatrix';
import {FactTable} from './components/FactTable';
import {ReviewForm} from './components/ReviewForm';
import {ScenarioPanel} from './components/ScenarioPanel';
import {DiagnosticPanel} from './components/DiagnosticPanel';
import {RunPanel} from './components/RunPanel';

function message(error:unknown){return error instanceof ApiError?`${error.message}（${error.payload.error.code}，${error.payload.error.request_id}）`:error instanceof Error?error.message:'无法读取数据';}
const SEGMENTS=['all','group','power_battery','energy_storage'];
const STATUSES=['all','extracted','needs_review','verified','missing','conflict'];

function upsertDataset(items:Dataset[],dataset:Dataset):Dataset[]{
  const index=items.findIndex(item=>item.id===dataset.id);
  if(index<0)return [dataset,...items];
  if(items[index].version>dataset.version)return items;
  const next=[...items];next[index]=dataset;return next;
}

function App(){
  const [companies,setCompanies]=useState<CompanyProfile[]>([]);
  const [datasets,setDatasets]=useState<Dataset[]>([]);
  const [selected,setSelected]=useState('');
  const [facts,setFacts]=useState<Fact[]>([]);
  const [candidates,setCandidates]=useState<IdentityCandidate[]>([]);
  const [capabilities,setCapabilities]=useState<CapabilityCollection|null>(null);
  const [segment,setSegment]=useState('all');
  const [statusF,setStatusF]=useState('all');
  const [view,setView]=useState<WorkbenchView>('review');
  const [reviewing,setReviewing]=useState<Fact|null>(null);
  const [evidence,setEvidence]=useState<Evidence|null>(null);
  const [evidenceLoading,setEvidenceLoading]=useState(false);
  const [evidenceError,setEvidenceError]=useState('');
  const [error,setError]=useState('');
  const [initialLoading,setInitialLoading]=useState(false);
  const [snapshotLoading,setSnapshotLoading]=useState(false);
  const [creating,setCreating]=useState(false);
  const [reloadNonce,setReloadNonce]=useState(0);

  const dataset=datasets.find(item=>item.id===selected);
  const selectedIdRef=useRef(selected);
  const selectionKeyRef=useRef(dataset?snapshotKey(dataset):'');
  selectedIdRef.current=selected;
  selectionKeyRef.current=dataset?snapshotKey(dataset):'';
  const snapshotRequestRef=useRef(0);
  const createRequestRef=useRef(0);
  const createControllerRef=useRef<AbortController|null>(null);
  const identityControllerRef=useRef<AbortController|null>(null);
  const latestControllerRef=useRef<AbortController|null>(null);
  const pendingReviewIdRef=useRef<string|null>(null);

  useEffect(()=>{
    const controller=new AbortController();setInitialLoading(true);setError('');
    Promise.all([api.datasets(controller.signal),api.companies({signal:controller.signal})])
      .then(([datasetCollection,companyCollection])=>{
        if(controller.signal.aborted)return;
        setDatasets(datasetCollection.items);setCompanies(companyCollection.items);
        setSelected(current=>datasetCollection.items.some(item=>item.id===current)?current:datasetCollection.items[0]?.id??'');
      })
      .catch(value=>{if(!controller.signal.aborted)setError(message(value));})
      .finally(()=>{if(!controller.signal.aborted)setInitialLoading(false);});
    return()=>controller.abort();
  },[]);

  useEffect(()=>{
    const requestId=++snapshotRequestRef.current;
    if(!dataset){setFacts([]);setCandidates([]);setCapabilities(null);setSnapshotLoading(false);return;}
    const controller=new AbortController();
    setSnapshotLoading(true);setError('');setFacts([]);setCandidates([]);setCapabilities(null);setReviewing(null);setEvidence(null);setEvidenceError('');
    void loadWorkbenchSnapshot(dataset,requestId,controller.signal,()=>({key:selectionKeyRef.current,requestId:snapshotRequestRef.current}),{
      facts:(id,version,signal)=>api.facts(id,version,{signal}),
      candidates:api.identityCandidates,
      capabilities:api.datasetCapabilities,
    }).then(result=>{
      if(result.status==='stale')return;
      if(result.status==='failed'){setError(message(result.error));setSnapshotLoading(false);return;}
      setFacts(result.data.facts.items);setCandidates(result.data.candidates.items);setCapabilities(result.data.capabilities);
      const factId=pendingReviewIdRef.current;
      setReviewing(factId?result.data.facts.items.find(item=>item.id===factId)??null:null);
      pendingReviewIdRef.current=null;setSnapshotLoading(false);
    });
    return()=>controller.abort();
  },[dataset?.id,dataset?.version,reloadNonce]);

  useEffect(()=>{
    setEvidence(null);setEvidenceError('');
    if(!reviewing||!reviewing.evidence_ids.length){setEvidenceLoading(false);return;}
    const controller=new AbortController();setEvidenceLoading(true);
    api.evidence(reviewing.evidence_ids[0],controller.signal)
      .then(value=>{if(!controller.signal.aborted)setEvidence(value);})
      .catch(value=>{if(!controller.signal.aborted)setEvidenceError(message(value));})
      .finally(()=>{if(!controller.signal.aborted)setEvidenceLoading(false);});
    return()=>controller.abort();
  },[reviewing]);

  useEffect(()=>{
    const handler=(event:KeyboardEvent)=>{
      const target=event.target;
      const editable=target instanceof HTMLInputElement||target instanceof HTMLTextAreaElement||target instanceof HTMLSelectElement||(target instanceof HTMLElement&&target.isContentEditable);
      const next=shortcutView(event.key,editable);if(next)setView(next);
    };
    window.addEventListener('keydown',handler);return()=>window.removeEventListener('keydown',handler);
  },[]);

  useEffect(()=>()=>{
    createControllerRef.current?.abort();identityControllerRef.current?.abort();latestControllerRef.current?.abort();
  },[]);

  const reloadCurrentSnapshot=()=>{snapshotRequestRef.current++;setReloadNonce(value=>value+1);};

  const onCreate=async(body:DatasetCreate)=>{
    const requestId=++createRequestRef.current;
    const originSelectedId=selectedIdRef.current;
    createControllerRef.current?.abort();const controller=new AbortController();createControllerRef.current=controller;
    setCreating(true);
    try{
      const created=await api.createDataset(body,controller.signal);
      if(controller.signal.aborted||requestId!==createRequestRef.current)return;
      setDatasets(items=>upsertDataset(items,created));
      if(selectedIdRef.current===originSelectedId)setSelected(created.id);
    }finally{if(!controller.signal.aborted&&requestId===createRequestRef.current)setCreating(false);}
  };

  const onUploaded=(attachment:SourceAttachment,requestedDatasetId:string)=>{
    setDatasets(items=>upsertDataset(items,attachment.dataset));
    if(selectedIdRef.current===requestedDatasetId&&attachment.dataset.version===dataset?.version)reloadCurrentSnapshot();
  };

  const onConfirm=async(body:IdentityConfirmation):Promise<Dataset>=>{
    if(!dataset)throw new Error('请先选择 Dataset');
    const requestedKey=snapshotKey(dataset);
    identityControllerRef.current?.abort();const controller=new AbortController();identityControllerRef.current=controller;
    const confirmed=await api.confirmDatasetIdentity(dataset.id,body,controller.signal);
    if(controller.signal.aborted)throw new DOMException('请求已取消','AbortError');
    setDatasets(items=>upsertDataset(items,confirmed));
    if(selectionKeyRef.current===requestedKey&&confirmed.version===dataset.version)reloadCurrentSnapshot();
    return confirmed;
  };

  const refreshLatest=async(datasetId:string,requestedKey:string,factId:string|null)=>{
    latestControllerRef.current?.abort();const controller=new AbortController();latestControllerRef.current=controller;
    setError('');
    try{
      const latest=await api.dataset(datasetId,controller.signal);
      if(controller.signal.aborted||selectedIdRef.current!==datasetId||selectionKeyRef.current!==requestedKey)return;
      pendingReviewIdRef.current=factId;setDatasets(items=>upsertDataset(items,latest));
      if(latest.version===dataset?.version)reloadCurrentSnapshot();
    }catch(value){if(!controller.signal.aborted&&selectedIdRef.current===datasetId&&selectionKeyRef.current===requestedKey)setError(message(value));}
  };

  const visible=facts.filter(fact=>(segment==='all'||fact.segment===segment)&&(statusF==='all'||fact.status===statusF));
  const identityBlocked=!dataset||snapshotLoading||hasIdentityBlocker(dataset,candidates);
  const busy=initialLoading||snapshotLoading;

  return <main>
    <header><div><p>链眼 ChainEye · 面向产业链的全链路可追溯投研智能体 · 契约 v{CONTRACT_VERSION}</p><h1>溯链智研工作台</h1></div><span>数据 · 身份 · 能力 · 复核 · 情景 · 研究</span></header>
    <aside className="notice">上传年报后先核对企业身份，再对候选事实进行人工复核。身份冲突或未确认时禁止情景与研究任务；所有结论均绑定明确 Dataset 版本。</aside>
    <DatasetPanel datasets={datasets} companies={companies} selectedId={selected} creating={creating} onSelect={setSelected} onCreate={onCreate}/>
    {dataset&&<UploadPanel datasetId={dataset.id} onUploaded={onUploaded}/>}
    {dataset&&<IdentityPanel dataset={dataset} candidates={candidates} companies={companies} loading={snapshotLoading} onConfirm={onConfirm} onRefresh={()=>refreshLatest(dataset.id,snapshotKey(dataset),null)}/>}
    <CapabilityMatrix capabilities={capabilities} loading={snapshotLoading}/>
    <nav className="tabs">
      <button className={view==='review'?'tab active':'tab'} onClick={()=>setView('review')}>数据复核 <kbd>1</kbd></button>
      <button className={view==='diagnostic'?'tab active':'tab'} onClick={()=>setView('diagnostic')}>财务诊断 <kbd>2</kbd></button>
      <button className={view==='research'?'tab active':'tab'} onClick={()=>setView('research')} disabled={identityBlocked} title={identityBlocked?'请先确认企业身份':''}>情景研究 <kbd>3</kbd></button>
      <button className={view==='run'?'tab active':'tab'} onClick={()=>setView('run')} disabled={identityBlocked} title={identityBlocked?'请先确认企业身份':''}>研究任务 <kbd>4</kbd></button>
    </nav>
    <section className="controls">
      {view==='review'&&<label>业务<select value={segment} onChange={event=>setSegment(event.target.value)}>{SEGMENTS.map(item=><option key={item} value={item}>{item==='all'?'全部':names[item]}</option>)}</select></label>}
      {view==='review'&&<label>状态<select value={statusF} onChange={event=>setStatusF(event.target.value)}>{STATUSES.map(item=><option key={item} value={item}>{item==='all'?'全部':statusLabels[item]}</option>)}</select></label>}
    </section>
    {error&&<p role="alert" className="error">{error}</p>}{busy&&<p role="status">正在读取当前快照…</p>}
    {!busy&&!datasets.length&&!error&&<p>暂无 Dataset，请先创建。</p>}
    {view==='review'
      ?<section className="panel"><h2>财务事实复核</h2>{reviewing
        ?<ReviewForm key={`${reviewing.id}:${reviewing.revision??1}`} fact={reviewing} evidence={evidence} evidenceLoading={evidenceLoading} evidenceError={evidenceError} onClose={()=>setReviewing(null)} onSaved={()=>dataset?refreshLatest(dataset.id,snapshotKey(dataset),null):Promise.resolve()} onReload={()=>dataset?refreshLatest(dataset.id,snapshotKey(dataset),reviewing?.id??null):Promise.resolve()}/>
        :<FactTable facts={visible} onSelect={setReviewing} onEvidence={setReviewing}/>}</section>
      :view==='diagnostic'
        ?<DiagnosticPanel facts={facts}/>
        :view==='research'
          ?(dataset&&!identityBlocked?<ScenarioPanel dataset={dataset} facts={facts}/>:<section className="panel"><p className="error">请先解决企业身份冲突并完成人工确认。</p></section>)
          :(dataset&&!identityBlocked?<RunPanel key={`${dataset.id}:${dataset.version}`} dataset={dataset}/>:<section className="panel"><p className="error">请先解决企业身份冲突并完成人工确认。</p></section>)}
  </main>;
}
export default App;
