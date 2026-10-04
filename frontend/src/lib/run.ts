import type {Claim,Dataset,Event,Run,RunCreate} from '../api/generated';
import {stableKey} from './scenario.ts';

export function buildRunCreate(dataset:Dataset,question:string,segment:RunCreate['segment'],mode:RunCreate['mode'],replayRunId:string):RunCreate{
  const common={dataset_id:dataset.id,dataset_version:dataset.version,question:question.trim(),segment,mode};
  return mode==='replay'?{...common,replay_run_id:replayRunId.trim()}:{...common};
}

function canonical(value:unknown):string{
  if(Array.isArray(value))return `[${value.map(canonical).join(',')}]`;
  if(value&&typeof value==='object'){
    const record=value as Record<string,unknown>;
    return `{${Object.keys(record).sort().map(key=>`${JSON.stringify(key)}:${canonical(record[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

export function runIdempotencyKey(body:RunCreate):string{return stableKey(canonical(body));}

export function isRunActive(status:Run['status']):boolean{return status==='queued'||status==='running';}

export function mergeEvents(current:Event[],incoming:Event[]):Event[]{
  const bySeq=new Map(current.map(event=>[event.seq,event]));
  for(const event of incoming)bySeq.set(event.seq,event);
  return [...bySeq.values()].sort((a,b)=>a.seq-b.seq);
}

function isClaim(value:unknown):value is Claim{
  if(!value||typeof value!=='object')return false;
  const claim=value as Partial<Claim>;
  return typeof claim.id==='string'&&typeof claim.text==='string'&&Array.isArray(claim.evidence_ids)&&Array.isArray(claim.calculation_ids)&&Array.isArray(claim.assumption_ids)&&Array.isArray(claim.counter_evidence_ids)&&Array.isArray(claim.limitations)&&typeof claim.review_status==='string';
}

export function claimsFromEvents(events:Event[]):Claim[]{
  const claims=new Map<string,Claim>();
  for(const event of events){
    const value=event.payload.claims;
    if(Array.isArray(value))for(const claim of value)if(isClaim(claim))claims.set(claim.id,claim);
  }
  return [...claims.values()];
}
