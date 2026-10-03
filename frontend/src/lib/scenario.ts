import type {Fact} from '../api/generated';

export interface BaselinePair{
  revenue:Fact;
  cost:Fact;
  periodEnd:string;
}

// 把同口径（期间+公司+业务+报表范围+币种）的 verified 收入、成本配对，返回按年度倒序（最新在前）。
export function pairBaseline(facts:Fact[],segment:'power_battery'|'energy_storage'):BaselinePair[]{
  const scopeKey=(f:Fact)=>[f.period_start,f.period_end,f.company,f.segment,f.statement_scope,f.currency].join('|');
  const revenues=facts.filter(f=>f.segment===segment&&f.metric==='revenue'&&f.status==='verified');
  const costs=new Map<string,Fact>();
  for(const c of facts.filter(f=>f.segment===segment&&f.metric==='cost_of_sales'&&f.status==='verified'))costs.set(scopeKey(c),c);
  const pairs:BaselinePair[]=[];
  for(const r of revenues){
    const c=costs.get(scopeKey(r));
    if(c)pairs.push({revenue:r,cost:c,periodEnd:r.period_end??''});
  }
  pairs.sort((a,b)=>b.periodEnd.localeCompare(a.periodEnd));
  return pairs;
}

// 确定性短 key：相同请求得到相同 key（用于 Idempotency-Key 复用），参数变化则 key 变化。
export function stableKey(input:string):string{
  let h=5381;
  for(let i=0;i<input.length;i++){h=((h<<5)+h+input.charCodeAt(i))>>>0;}
  return 'k'+(h>>>0).toString(36);
}
