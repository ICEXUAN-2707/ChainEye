// 展示用格式化。仅做单位换算与排版，不做权威财务计算（权威计算由后端 Python 沙箱完成）。
export const names:Record<string,string>={group:'集团',power_battery:'动力电池',energy_storage:'储能电池'};
export const metrics:Record<string,string>={revenue:'营业收入',cost_of_sales:'营业成本',reported_gross_margin:'披露毛利率',parent_net_profit:'归母净利润',parent_adjusted_net_profit:'扣非归母净利润',operating_cash_flow:'经营现金流',total_assets:'总资产',parent_equity:'归母权益',inventory:'存货',accounts_receivable:'应收账款'};

export const statusLabels:Record<string,string>={extracted:'候选',needs_review:'需复核',verified:'已复核',missing:'缺失',conflict:'冲突'};
export const statusClass:Record<string,string>={extracted:'s-extracted',needs_review:'s-needs-review',verified:'s-verified',missing:'s-missing',conflict:'s-conflict'};
export const parseStatusLabels:Record<string,string>={queued:'排队中',parsed:'已解析',needs_review:'需复核',failed:'失败'};

// value 单位为人民币元（契约规定）；显示时 ≥1e8 换算为亿元，ratio 乘 100 显示百分数。
export function fmtAmount(value:string|null|undefined,unit:'CNY'|'ratio'):string{
  if(value===null||value===undefined||value==='')return '—';
  if(unit==='ratio')return `${(Number(value)*100).toFixed(2)}%`;
  const n=Number(value);
  if(Number.isFinite(n)&&Math.abs(n)>=1e8)return `${(n/1e8).toFixed(2)} 亿元`;
  return `${n.toLocaleString('zh-CN',{maximumFractionDigits:2})} 元`;
}

// 原文披露值：raw_unit 为千元或百分数，保留原始口径展示。
export function fmtRaw(raw:string|null|undefined,rawUnit:'CNY_thousand'|'percent'):string{
  if(raw===null||raw===undefined||raw==='')return '—';
  return rawUnit==='percent'?`${raw}%`:`${raw} 千元`;
}

// 百分点（pp）已由后端按 *100 给出，前端不再乘 100，仅补正负号与保留两位。
export function fmtPp(value:string|null|undefined):string{
  if(value===null||value===undefined||value==='')return '—';
  const n=Number(value);
  return `${n>0?'+':''}${n.toFixed(2)} pp`;
}

export function periodOf(p:{period_kind:string;period_start?:string|null;period_end:string}):string{
  return p.period_kind==='point_in_time'?p.period_end:`${p.period_start} 至 ${p.period_end}`;
}
