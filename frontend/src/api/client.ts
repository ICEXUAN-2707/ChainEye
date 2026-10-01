import type {DatasetCollection, FactCollection, Evidence, ErrorResponse} from './generated';
export const BASE_URL='http://127.0.0.1:8000';
export class ApiError extends Error {
  constructor(public status:number,public payload:ErrorResponse){super(payload.error.message);}
}
async function get<T>(path:string,signal?:AbortSignal):Promise<T>{
  const res=await fetch(BASE_URL+path,{signal});
  const body:unknown=await res.json();
  if(!res.ok){
    if(body && typeof body==='object' && 'error' in body)throw new ApiError(res.status,body as ErrorResponse);
    throw new Error(`接口异常 HTTP ${res.status}`);
  }
  return body as T;
}
export const api={
  datasets:(signal?:AbortSignal)=>get<DatasetCollection>('/api/v1/datasets',signal),
  facts:(id:string,version:number,signal?:AbortSignal)=>get<FactCollection>(`/api/v1/datasets/${encodeURIComponent(id)}/facts?version=${version}`,signal),
  evidence:(id:string,signal?:AbortSignal)=>get<Evidence>(`/api/v1/evidence/${encodeURIComponent(id)}`,signal),
};
