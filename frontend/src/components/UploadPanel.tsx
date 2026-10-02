import {useState} from 'react';
import type {SourceAttachment} from '../api/generated';
import {api,ApiError} from '../api/client';
import {parseStatusLabels} from '../lib/format';

function message(e:unknown):string{
  if(e instanceof ApiError){
    return `${e.message}（${e.code}，${e.requestId}）`;
  }
  return e instanceof Error?e.message:'上传失败';
}

export function UploadPanel({datasetId,onUploaded}:{datasetId:string;onUploaded:(a:SourceAttachment)=>void}){
  const [file,setFile]=useState<File|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [result,setResult]=useState<SourceAttachment|null>(null);
  const submit=async()=>{
    if(!file||!datasetId)return;
    setBusy(true);setError('');
    try{
      const a=await api.uploadSource(datasetId,file);
      setResult(a);onUploaded(a);
    }catch(e){setError(message(e));}
    finally{setBusy(false);}
  };
  return <section className="panel">
    <h2>上传年报 PDF</h2>
    <p className="hint">限受控数据包内的年报原件：≤30 MiB、≤500 页、非加密、文本型 PDF。上传后由后端提取候选事实，人工复核前不会标记为已复核。</p>
    <div className="upload-row">
      <input type="file" accept="application/pdf" onChange={e=>{setFile(e.target.files?.[0]??null);setResult(null);setError('');}}/>
      <button onClick={submit} disabled={!file||busy||!datasetId}>{busy?'上传中…':'上传并解析'}</button>
    </div>
    {error&&<p role="alert" className="error">{error}</p>}
    {result&&<div className="result">
      <p>已上传：<strong>{result.source.filename}</strong>（解析状态：{parseStatusLabels[result.source.parse_status]}）</p>
      <p className="mono">SHA256 {result.source.sha256}</p>
      <p>数据包版本已更新为 v{result.dataset.version}</p>
    </div>}
  </section>;
}
