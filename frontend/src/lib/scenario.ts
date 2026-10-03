import type {Fact} from '../api/generated';

export interface BaselinePair{
  revenue:Fact;
  cost:Fact;
  periodEnd:string;
}

// 把同口径（期间+公司+业务+报表范围+币种）的 verified 收入、成本配对，返回按年度倒序（最新在前）。
// 若某口径存在重复事实（>1 收入或 >1 成本），视为歧义、跳过，绝不静默配对其中一个。
export function pairBaseline(facts:Fact[],segment:'power_battery'|'energy_storage'):BaselinePair[]{
  const scopeKey=(f:Fact)=>[f.period_start,f.period_end,f.company,f.segment,f.statement_scope,f.currency].join('|');
  const group=<T,>(items:T[],key:(x:T)=>string):Map<string,T[]>=>{
    const m=new Map<string,T[]>();
    for(const x of items){const k=key(x);const arr=m.get(k);if(arr)arr.push(x);else m.set(k,[x]);}
    return m;
  };
  const revenues=group(facts.filter(f=>f.segment===segment&&f.metric==='revenue'&&f.status==='verified'),scopeKey);
  const costs=group(facts.filter(f=>f.segment===segment&&f.metric==='cost_of_sales'&&f.status==='verified'),scopeKey);
  const pairs:BaselinePair[]=[];
  for(const [k,revs] of revenues){
    const cs=costs.get(k);
    if(!cs)continue;
    if(revs.length!==1||cs.length!==1)continue;  // 重复口径 → 歧义，跳过
    pairs.push({revenue:revs[0],cost:cs[0],periodEnd:revs[0].period_end??''});
  }
  pairs.sort((a,b)=>b.periodEnd.localeCompare(a.periodEnd));
  return pairs;
}

// 确定性、固定长度（16 位十六进制，满足后端 8~128 字符约束）：相同请求得到相同 key，参数变化则 key 变化。
export function stableKey(input:string):string{
  let h1=5381,h2=52711;
  for(let i=0;i<input.length;i++){
    const c=input.charCodeAt(i);
    h1=((h1<<5)+h1+c)>>>0;
    h2=((h2<<5)+h2+c)>>>0;
  }
  return (h1>>>0).toString(16).padStart(8,'0')+(h2>>>0).toString(16).padStart(8,'0');
}

export interface ScenarioKeyInput{
  dataset_id:string;dataset_version:number;
  revenue_fact_id:string;revenue_revision:number;
  cost_fact_id:string;cost_revision:number;
  cost_exposure:string;effective_price_shock:string;customer_pass_through:string;
  basis:string;
}

// 幂等键：纳入全部影响请求体的字段（含 basis）。
export function scenarioKey(input:ScenarioKeyInput):string{
  const raw=[
    input.dataset_id,input.dataset_version,
    input.revenue_fact_id,input.revenue_revision,
    input.cost_fact_id,input.cost_revision,
    input.cost_exposure,input.effective_price_shock,input.customer_pass_through,
    input.basis,
  ].join('|');
  return stableKey(raw);
}
