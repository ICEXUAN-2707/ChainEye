import type {DatasetCollection, FactCollection, Evidence, ErrorResponse, SourceAttachment, Fact, FactCorrection, Source, Dataset, DatasetCreate, ScenarioRequest, ScenarioResult, Calculation, RunCreate, Run, EventCollection, ResumeRequest} from './generated';

export const BASE_URL='http://127.0.0.1:8000';

export class ApiError extends Error {
  constructor(public status:number,public payload:ErrorResponse){super(payload.error.message);}
  get code(){return this.payload.error.code;}
  get requestId(){return this.payload.error.request_id;}
  get details(){return this.payload.error.details;}
  get retryable(){return this.payload.error.retryable;}
}

function toError(status:number,body:unknown):ApiError{
  if(body && typeof body==='object' && 'error' in body)return new ApiError(status,body as ErrorResponse);
  return new ApiError(status,{error:{code:'HTTP_ERROR',message:`接口异常 HTTP ${status}`,details:undefined,retryable:false,request_id:''}});
}

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const res=await fetch(BASE_URL+path,init);
  const body:unknown=await res.json().catch(()=>null);
  if(!res.ok)throw toError(res.status,body);
  return body as T;
}

function json(method:'POST'|'PATCH',body:unknown):RequestInit{
  return {method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)};
}

export const api={
  datasets:(signal?:AbortSignal)=>request<DatasetCollection>('/api/v1/datasets',{signal}),
  dataset:(id:string,signal?:AbortSignal)=>request<Dataset>(`/api/v1/datasets/${encodeURIComponent(id)}`,{signal}),
  createDataset:(body:DatasetCreate)=>request<Dataset>('/api/v1/datasets',json('POST',body)),
  facts:(id:string,version:number,opts?:{status?:string;segment?:string;signal?:AbortSignal})=>{
    const p=new URLSearchParams({version:String(version)});
    if(opts?.status)p.set('status',opts.status);
    if(opts?.segment)p.set('segment',opts.segment);
    return request<FactCollection>(`/api/v1/datasets/${encodeURIComponent(id)}/facts?${p.toString()}`,{signal:opts?.signal});
  },
  uploadSource:(id:string,file:File,opts?:{url?:string;published_date?:string})=>{
    const fd=new FormData();
    fd.append('file',file);
    if(opts?.url)fd.append('url',opts.url);
    if(opts?.published_date)fd.append('published_date',opts.published_date);
    return request<SourceAttachment>(`/api/v1/datasets/${encodeURIComponent(id)}/sources`,{method:'POST',body:fd});
  },
  correctFact:(id:string,body:FactCorrection)=>request<Fact>(`/api/v1/facts/${encodeURIComponent(id)}`,json('PATCH',body)),
  createScenario:(body:ScenarioRequest,idempotencyKey:string)=>request<ScenarioResult>('/api/v1/scenarios',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':idempotencyKey},body:JSON.stringify(body)}),
  calculation:(id:string,signal?:AbortSignal)=>request<Calculation>(`/api/v1/calculations/${encodeURIComponent(id)}`,{signal}),
  createRun:(body:RunCreate,idempotencyKey:string)=>request<Run>('/api/v1/runs',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':idempotencyKey},body:JSON.stringify(body)}),
  run:(id:string,signal?:AbortSignal)=>request<Run>(`/api/v1/runs/${encodeURIComponent(id)}`,{signal}),
  runEvents:(id:string,opts?:{afterSeq?:number;limit?:number;signal?:AbortSignal})=>{
    const p=new URLSearchParams();
    if(opts?.afterSeq!==undefined)p.set('after_seq',String(opts.afterSeq));
    if(opts?.limit!==undefined)p.set('limit',String(opts.limit));
    const q=p.toString();
    return request<EventCollection>(`/api/v1/runs/${encodeURIComponent(id)}/events${q?`?${q}`:''}`,{signal:opts?.signal});
  },
  resumeRun:(id:string,body:ResumeRequest)=>request<Run>(`/api/v1/runs/${encodeURIComponent(id)}/resume`,json('POST',body)),
  evidence:(id:string,signal?:AbortSignal)=>request<Evidence>(`/api/v1/evidence/${encodeURIComponent(id)}`,{signal}),
  source:(id:string,signal?:AbortSignal)=>request<Source>(`/api/v1/sources/${encodeURIComponent(id)}`,{signal}),
};
