"""Pure R3 financial rules over an explicitly supplied fact snapshot."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal,localcontext
from typing import Literal

from .contracts import Fact

FINANCIAL_METRIC_IDS=(
    'revenue_yoy','gross_profit','gross_margin','inventory_change',
    'accounts_receivable_change','parent_adjusted_profit_gap',
)
UNITS={
    'revenue_yoy':'ratio','gross_profit':'CNY','gross_margin':'ratio',
    'inventory_change':'CNY','accounts_receivable_change':'CNY','parent_adjusted_profit_gap':'CNY',
}

@dataclass(frozen=True)
class FinancialValue:
    formula_id:str
    input_facts:tuple[Fact,...]
    unit:Literal['CNY','ratio']
    value:Decimal|None
    reason:str|None=None

def _result(metric_id,facts,value=None,reason=None):
    return FinancialValue(metric_id,tuple(facts),UNITS[metric_id],value,reason)

def _scope(fact):return fact.company,fact.segment,fact.statement_scope,fact.currency
def _year(fact):return date.fromisoformat(fact.period_end).year

def _series(facts,metric_id,group_only=False):
    selected=[f for f in facts if f.metric==metric_id]
    if group_only:selected=[f for f in selected if f.segment=='group']
    if len({_scope(f) for f in selected})>1:return None,selected,'ambiguous fact scope'
    if len({f.period_end for f in selected})!=len(selected):return None,selected,'ambiguous facts for period'
    selected=sorted(selected,key=lambda f:f.period_end)
    if len(selected)<2:return None,selected,'current and prior annual facts are required'
    pair=selected[-2:]
    if _year(pair[1])!=_year(pair[0])+1:return None,pair,'consecutive annual facts are required'
    if pair[0].period_kind=='point_in_time':
        prior_date=date.fromisoformat(pair[0].period_end);current_date=date.fromisoformat(pair[1].period_end)
        if (prior_date.month,prior_date.day)!=(current_date.month,current_date.day):
            return None,pair,'comparable point-in-time dates are required'
    if any(f.status!='verified' or f.value is None for f in pair):return None,pair,'required facts are missing or not verified'
    return pair,pair,None

def _same_period(facts,metric_ids,group_only=False):
    selected=[f for f in facts if f.metric in metric_ids]
    if group_only:selected=[f for f in selected if f.segment=='group']
    if len({_scope(f) for f in selected})>1:return None,selected,'ambiguous fact scope'
    keys=[(f.metric,f.period_end) for f in selected]
    if len(set(keys))!=len(keys):return None,selected,'ambiguous facts for period'
    by_metric={metric:{f.period_end:f for f in selected if f.metric==metric} for metric in metric_ids}
    common=set.intersection(*(set(items) for items in by_metric.values())) if by_metric else set()
    if not common:return None,selected,'same-period facts are required'
    period=max(common);chosen=[by_metric[metric][period] for metric in metric_ids]
    if any(f.status!='verified' or f.value is None for f in chosen):return None,chosen,'required facts are missing or not verified'
    return chosen,chosen,None

def calculate(facts:list[Fact],requested_metric_ids:list[str])->list[FinancialValue]:
    unknown=set(requested_metric_ids)-set(FINANCIAL_METRIC_IDS)
    if unknown:raise ValueError(f'unknown financial metric: {sorted(unknown)[0]}')
    results=[]
    with localcontext() as ctx:
        ctx.prec=40
        for metric_id in requested_metric_ids:
            if metric_id=='revenue_yoy':
                pair,inputs,reason=_series(facts,'revenue')
                if reason:results.append(_result(metric_id,inputs,reason=reason));continue
                prior,current=pair;prior_value=Decimal(prior.value)
                if prior_value<=0:results.append(_result(metric_id,pair,reason='prior revenue must be positive'));continue
                results.append(_result(metric_id,pair,(Decimal(current.value)-prior_value)/prior_value))
            elif metric_id in ('gross_profit','gross_margin'):
                pair,inputs,reason=_same_period(facts,('revenue','cost_of_sales'))
                if reason:results.append(_result(metric_id,inputs,reason=reason));continue
                revenue,cost=pair;r=Decimal(revenue.value);gross_profit=r-Decimal(cost.value)
                if metric_id=='gross_margin' and r<=0:results.append(_result(metric_id,pair,reason='revenue must be positive'));continue
                results.append(_result(metric_id,pair,gross_profit if metric_id=='gross_profit' else gross_profit/r))
            elif metric_id in ('inventory_change','accounts_receivable_change'):
                source_metric=metric_id.removesuffix('_change')
                pair,inputs,reason=_series(facts,source_metric,group_only=True)
                if reason:results.append(_result(metric_id,inputs,reason=reason));continue
                prior,current=pair;results.append(_result(metric_id,pair,Decimal(current.value)-Decimal(prior.value)))
            else:
                pair,inputs,reason=_same_period(facts,('parent_net_profit','parent_adjusted_net_profit'),group_only=True)
                if reason:results.append(_result(metric_id,inputs,reason=reason));continue
                profit,adjusted=pair;results.append(_result(metric_id,pair,Decimal(profit.value)-Decimal(adjusted.value)))
    return results
