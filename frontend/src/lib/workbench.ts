import type {CapabilityCollection,Dataset,FactCollection,IdentityCandidate,IdentityCandidateCollection} from '../api/generated';

export type SnapshotIdentity={key:string;requestId:number};

export function snapshotKey(dataset:Pick<Dataset,'id'|'version'>):string {
  return `${dataset.id}:${dataset.version}`;
}

export function candidateMatchesDataset(candidate:IdentityCandidate,dataset:Dataset):boolean {
  if(candidate.company_id===null)return true;
  const yearMatches=candidate.report_year===dataset.year||candidate.report_year===dataset.year-1;
  return candidate.company_id===dataset.company_id&&candidate.report_type===dataset.report_type&&yearMatches;
}

export function hasIdentityBlocker(dataset:Dataset,candidates:IdentityCandidate[]):boolean {
  if(dataset.identity_status!=='confirmed')return true;
  return candidates.some(candidate=>
    candidate.status==='conflict'||candidate.status==='ambiguous'||!candidateMatchesDataset(candidate,dataset),
  );
}

export function shouldAcceptSnapshotResponse(
  requested:SnapshotIdentity,current:SnapshotIdentity,aborted:boolean,
):boolean {
  return !aborted&&requested.key===current.key&&requested.requestId===current.requestId;
}

export type SnapshotData={
  facts:FactCollection;
  candidates:IdentityCandidateCollection;
  capabilities:CapabilityCollection;
};

export type SnapshotLoadResult=
  | {status:'loaded';data:SnapshotData}
  | {status:'failed';error:unknown}
  | {status:'stale'};

export async function loadWorkbenchSnapshot(
  dataset:Dataset,
  requestId:number,
  signal:AbortSignal,
  current:()=>SnapshotIdentity,
  requests:{
    facts:(id:string,version:number,signal:AbortSignal)=>Promise<FactCollection>;
    candidates:(id:string,version:number,signal:AbortSignal)=>Promise<IdentityCandidateCollection>;
    capabilities:(id:string,version:number,industryProfileVersion:number,signal:AbortSignal)=>Promise<CapabilityCollection>;
  },
):Promise<SnapshotLoadResult> {
  const requested={key:snapshotKey(dataset),requestId};
  try{
    const [facts,candidates,capabilities]=await Promise.all([
      requests.facts(dataset.id,dataset.version,signal),
      requests.candidates(dataset.id,dataset.version,signal),
      requests.capabilities(dataset.id,dataset.version,dataset.industry_profile_version,signal),
    ]);
    return shouldAcceptSnapshotResponse(requested,current(),signal.aborted)
      ?{status:'loaded',data:{facts,candidates,capabilities}}
      :{status:'stale'};
  }catch(error){
    return shouldAcceptSnapshotResponse(requested,current(),signal.aborted)
      ?{status:'failed',error}
      :{status:'stale'};
  }
}
