import {useEffect,useMemo,useState,type FormEvent} from 'react';
import type {CompanyProfile,Dataset,DatasetCreate} from '../api/generated';
import {datasetLabel} from '../lib/format';

export function DatasetPanel({datasets,companies,selectedId,creating,onSelect,onCreate}:{
  datasets:Dataset[];
  companies:CompanyProfile[];
  selectedId:string;
  creating:boolean;
  onSelect:(id:string)=>void;
  onCreate:(body:DatasetCreate)=>Promise<void>;
}){
  const [companyId,setCompanyId]=useState<CompanyProfile['id']|''>(companies[0]?.id??'');
  const profile=companies.find(item=>item.id===companyId)??companies[0];
  const years=useMemo(()=>profile?.supported_report_years??[],[profile]);
  const [year,setYear]=useState<number>(years[0]??2025);
  const [name,setName]=useState('');
  const [error,setError]=useState('');

  useEffect(()=>{
    if(!companies.length)return;
    setCompanyId(current=>companies.some(item=>item.id===current)?current:companies[0].id);
  },[companies]);
  useEffect(()=>{
    if(years.length&&!years.includes(year))setYear(years[0]);
  },[years,year]);

  const submit=async(event:FormEvent)=>{
    event.preventDefault();
    if(!profile||!name.trim())return;
    setError('');
    try{await onCreate({name:name.trim(),company:profile.company_code,year:year as DatasetCreate['year']});setName('');}
    catch(value){setError(value instanceof Error?value.message:'创建 Dataset 失败');}
  };

  return <section className="panel dataset-panel">
    <div className="section-heading"><div><h2>Dataset</h2><p className="hint">每个 Dataset 固定企业、报告年度和显式版本；上传、身份确认和事实修订都会生成新快照。</p></div></div>
    <div className="dataset-grid">
      <label>当前 Dataset<select value={selectedId} onChange={event=>onSelect(event.target.value)} disabled={!datasets.length}>
        {!datasets.length&&<option value="">暂无 Dataset</option>}
        {datasets.map(item=><option key={item.id} value={item.id}>{datasetLabel(item)} · v{item.version} · {item.identity_status}</option>)}
      </select></label>
      <form className="dataset-create" onSubmit={submit}>
        <label>名称<input value={name} onChange={event=>setName(event.target.value)} placeholder="例如：亿纬锂能 2025 年报"/></label>
        <label>企业<select value={profile?.id??''} onChange={event=>setCompanyId(event.target.value as CompanyProfile['id'])} disabled={!companies.length}>
          {companies.map(item=><option key={item.id} value={item.id}>{item.legal_name}（{item.company_code}）</option>)}
        </select></label>
        <label>年度<select value={year} onChange={event=>setYear(Number(event.target.value))} disabled={!years.length}>
          {years.map(item=><option key={item} value={item}>{item}</option>)}
        </select></label>
        <button type="submit" disabled={creating||!profile||!name.trim()}>{creating?'创建中…':'创建 Dataset'}</button>
      </form>
    </div>
    {error&&<p role="alert" className="error">{error}</p>}
  </section>;
}
