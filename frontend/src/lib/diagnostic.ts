import type {Fact} from '../api/generated';

export type DiagnosticDirection='up'|'down'|'flat';
export type DiagnosticComparison={
  previous:Fact;
  current:Fact;
  previousValue:number;
  currentValue:number;
  direction:DiagnosticDirection;
};

export function diagnosticComparison(
  facts:Fact[],
  segment:Fact['segment'],
  metric:Fact['metric'],
):DiagnosticComparison|null{
  const candidates=(year:string)=>facts.filter(f=>
    f.segment===segment&&f.metric===metric&&f.period_end.startsWith(`${year}-`),
  );
  const previousItems=candidates('2024');
  const currentItems=candidates('2025');
  if(previousItems.length!==1||currentItems.length!==1)return null;
  const previous=previousItems[0];
  const current=currentItems[0];
  if(previous.status!=='verified'||current.status!=='verified'||previous.value===null||current.value===null)return null;
  if(previous.unit!==current.unit||previous.period_kind!==current.period_kind)return null;
  if(previous.period_end.slice(5)!==current.period_end.slice(5))return null;
  const previousValue=Number(previous.value);
  const currentValue=Number(current.value);
  if(!Number.isFinite(previousValue)||!Number.isFinite(currentValue))return null;
  const direction=currentValue>previousValue?'up':currentValue<previousValue?'down':'flat';
  return {previous,current,previousValue,currentValue,direction};
}

export function metricMatchesQuery(label:string,query:string):boolean{
  const normalized=query.trim();
  return !normalized||label.includes(normalized);
}
