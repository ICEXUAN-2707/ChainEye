import type {Fact,FactCorrection} from '../api/generated';

export type ReviewStatus=FactCorrection['status'];
export type RawUnit=Fact['raw_unit'];

const DECIMAL=/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/;
const RAW_TO_NORMALIZED_PLACES:Record<RawUnit,number>={CNY_yuan:0,CNY_thousand:3,percent:-2};
const NORMALIZED_TO_RAW_PLACES:Record<RawUnit,number>={CNY_yuan:0,CNY_thousand:-3,percent:2};
const RAW_UNIT_LABELS:Record<RawUnit,string>={CNY_yuan:'元',CNY_thousand:'千元',percent:'百分数'};

function shiftDecimal(value:string,places:number):string|null{
  const source=value.trim();
  if(!DECIMAL.test(source))return null;
  if(places===0)return source;
  const negative=source.startsWith('-');
  const unsigned=negative?source.slice(1):source;
  const [integer,fraction='']=unsigned.split('.');
  const digits=integer+fraction;
  const point=integer.length+places;
  let shifted:string;
  if(point<=0)shifted=`0.${'0'.repeat(-point)}${digits}`;
  else if(point>=digits.length)shifted=digits+'0'.repeat(point-digits.length);
  else shifted=`${digits.slice(0,point)}.${digits.slice(point)}`;
  const [whole,decimal='']=shifted.split('.');
  const normalizedWhole=whole.replace(/^0+(?=\d)/,'')||'0';
  const normalizedDecimal=decimal.replace(/0+$/,'');
  const normalized=normalizedDecimal?`${normalizedWhole}.${normalizedDecimal}`:normalizedWhole;
  return negative&&normalized!=='0'?`-${normalized}`:normalized;
}

export function rawUnitLabel(rawUnit:RawUnit):string{
  return RAW_UNIT_LABELS[rawUnit];
}

export function isDecimalValue(value:string):boolean{
  return DECIMAL.test(value.trim());
}

export function rawValueFromNormalized(value:string,rawUnit:RawUnit):string|null{
  return shiftDecimal(value,NORMALIZED_TO_RAW_PLACES[rawUnit]);
}

export function normalizedValueFromRaw(rawValue:string,rawUnit:RawUnit):string|null{
  return shiftDecimal(rawValue,RAW_TO_NORMALIZED_PLACES[rawUnit]);
}

export function canSubmitReview(input:{
  busy:boolean;
  status:ReviewStatus;
  value:string;
  missingReason:string;
  reason:string;
  evidenceCount:number;
  evidenceReady:boolean;
  valuesValid:boolean;
}):boolean{
  if(input.busy||!input.reason.trim())return false;
  if(input.status==='missing')return !!input.missingReason.trim();
  if(!input.value.trim()||!input.valuesValid)return false;
  if(input.status==='verified')return input.evidenceCount>0&&input.evidenceReady;
  return true;
}

export function buildFactCorrection(
  fact:Fact,status:ReviewStatus,value:string,rawValue:string,missingReason:string,reason:string,
):FactCorrection{
  const isMissing=status==='missing';
  const normalizedValue=value.trim();
  const suppliedRawValue=rawValue.trim();
  return {
    expected_revision:fact.revision??1,
    value:isMissing?null:normalizedValue,
    raw_value:isMissing?null:(suppliedRawValue||rawValueFromNormalized(normalizedValue,fact.raw_unit)),
    status,
    evidence_ids:fact.evidence_ids,
    reason:reason.trim(),
    missing_reason:isMissing?missingReason.trim():null,
  };
}
