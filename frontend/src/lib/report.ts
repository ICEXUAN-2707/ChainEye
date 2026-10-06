import type {AssumptionRecord,Calculation,Claim,Evidence,Report,Run} from '../api/generated';

export type ResolvedReference<T>={id:string;value:T|null};

function resolve<T extends {id:string}>(ids:string[],items:T[]):ResolvedReference<T>[] {
  const byId=new Map(items.map(item=>[item.id,item]));
  return ids.map(id=>({id,value:byId.get(id)??null}));
}

export type ClaimReferences={
  evidence:ResolvedReference<Evidence>[];
  counterEvidence:ResolvedReference<Evidence>[];
  calculations:ResolvedReference<Calculation>[];
  assumptions:ResolvedReference<AssumptionRecord>[];
};

export function resolveEvidenceReferences(report:Report,ids:string[]):ResolvedReference<Evidence>[] {
  return resolve(ids,report.evidence);
}

export function resolveClaimReferences(report:Report,claim:Claim):ClaimReferences {
  return {
    evidence:resolveEvidenceReferences(report,claim.evidence_ids),
    counterEvidence:resolveEvidenceReferences(report,claim.counter_evidence_ids),
    calculations:resolve(claim.calculation_ids,report.calculations),
    assumptions:resolve(claim.assumption_ids,report.assumptions),
  };
}

export function reportRequestRunId(run:Run|null|undefined):string|null {
  return run?.report_ready?run.id:null;
}

export function shouldAcceptReportResponse(requestRunId:string,currentRunId:string,aborted:boolean):boolean {
  return !aborted&&requestRunId===currentRunId;
}

export type ReportLoadResult=
  | {status:'idle'|'stale'}
  | {status:'loaded';report:Report}
  | {status:'failed';error:unknown};

export async function loadCurrentReport(
  run:Run|null|undefined,
  signal:AbortSignal,
  currentRunId:()=>string,
  request:(runId:string,signal:AbortSignal)=>Promise<Report>,
):Promise<ReportLoadResult>{
  const runId=reportRequestRunId(run);if(!runId)return {status:'idle'};
  try{
    const report=await request(runId,signal);
    return shouldAcceptReportResponse(runId,currentRunId(),signal.aborted)?{status:'loaded',report}:{status:'stale'};
  }catch(error){
    return shouldAcceptReportResponse(runId,currentRunId(),signal.aborted)?{status:'failed',error}:{status:'stale'};
  }
}

export function reportExportUrl(runId:string,format:'markdown'|'pdf'):string {
  return `/api/v1/runs/${encodeURIComponent(runId)}/report?format=${format}`;
}

export function evidenceApiUrl(evidenceId:string):string {
  return `/api/v1/evidence/${encodeURIComponent(evidenceId)}`;
}

export function calculationApiUrl(calculationId:string):string {
  return `/api/v1/calculations/${encodeURIComponent(calculationId)}`;
}

export function sourcePageUrl(sourceId:string,pdfPage:number|null|undefined):string {
  const path=`/api/v1/sources/${encodeURIComponent(sourceId)}/content`;
  return pdfPage==null?path:`${path}#page=${pdfPage}`;
}
