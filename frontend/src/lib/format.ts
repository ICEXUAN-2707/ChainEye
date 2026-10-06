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

// 公式名 → 中文
export const formulaLabels:Record<string,string>={
  revenue_yoy:'收入同比',gross_profit:'毛利润',gross_margin:'毛利率',
  inventory_change:'存货变化',accounts_receivable_change:'应收变化',parent_adjusted_profit_gap:'扣非差额',
  'baseline-gross-profit':'基线毛利润','baseline-gross-margin':'基线毛利率',
  'scenario-delta-cost':'情景成本变化','scenario-revenue':'情景收入','scenario-cost-of-sales':'情景营业成本',
  'scenario-gross-profit':'情景毛利润','scenario-gross-margin':'情景毛利率',
  'scenario-delta-gross-profit':'情景毛利润变化','scenario-delta-gross-margin-pp':'情景毛利率变化',
};
export function fmtFormula(id:string):string{return formulaLabels[id]??id;}

// 运行节点 → 中文
export const nodeLabels:Record<string,string>={
  extract:'数据提取',validate:'基线校验',finance:'财务计算',research:'研究分析',scenario:'情景计算',verify:'引用核验',report:'报告生成',
};
export function fmtNode(node:string):string{return nodeLabels[node]??node;}

// 假设参数 → 中文
export const assumptionKeyLabels:Record<string,string>={
  cost_exposure:'成本暴露',effective_price_shock:'价格冲击',customer_pass_through:'客户传导',basis:'假设来源',acknowledged:'已确认',
};
export function fmtAssumptionKey(key:string):string{return assumptionKeyLabels[key]??key;}
export const basisLabels:Record<string,string>={user_assumption:'用户假设',research_assumption:'研究假设'};
export function fmtBasis(basis:string):string{return basisLabels[basis]??basis;}

// 缩短长 ID（UUID）为前 8 位，避免界面出现冗长技术标识。
export function shortId(id:string):string{return id.length>12?`${id.slice(0,8)}…`:id;}
