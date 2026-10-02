import type {Fact,FactCorrection} from '../api/generated';

export type ReviewStatus=FactCorrection['status'];

export function canSubmitReview(input:{
  busy:boolean;
  status:ReviewStatus;
  value:string;
  missingReason:string;
  reason:string;
  evidenceCount:number;
  evidenceReady:boolean;
}):boolean{
  if(input.busy||!input.reason.trim())return false;
  if(input.status==='missing')return !!input.missingReason.trim();
  if(!input.value.trim())return false;
  if(input.status==='verified')return input.evidenceCount>0&&input.evidenceReady;
  return true;
}

export function buildFactCorrection(
  fact:Fact,status:ReviewStatus,value:string,rawValue:string,missingReason:string,reason:string,
):FactCorrection{
  const isMissing=status==='missing';
  return {
    expected_revision:fact.revision??1,
    value:isMissing?null:value.trim(),
    raw_value:isMissing?null:(rawValue.trim()||null),
    status,
    evidence_ids:fact.evidence_ids,
    reason:reason.trim(),
    missing_reason:isMissing?missingReason.trim():null,
  };
}
