"""Deterministic conditional-scenario kernel; never a profit forecast."""
from decimal import Decimal, localcontext
from .contracts import Assumptions, Fact
from .decimal_values import decimal_text

class DomainError(ValueError):
    def __init__(self, code, message): self.code=code; super().__init__(message)

class ScenarioFactNotFoundError(LookupError): pass
class ScenarioFactScopeError(ValueError): pass
class ScenarioEvidenceNotFoundError(LookupError): pass
class ScenarioEvidenceScopeError(ValueError): pass
class IdempotencyConflictError(ValueError): pass

def validated_baseline(revenue:Fact,cost:Fact):
    if revenue.status!='verified' or cost.status!='verified': raise DomainError('FACT_NOT_VERIFIED','baseline requires reviewed facts')
    if revenue.segment not in ('power_battery','energy_storage'): raise DomainError('INVALID_BASELINE','scenario requires battery business baseline')
    keys=('company','segment','statement_scope','period_kind','period_start','period_end','currency','unit')
    if any(getattr(revenue,k)!=getattr(cost,k) for k in keys): raise DomainError('SCOPE_MISMATCH','baseline scopes differ')
    if revenue.metric!='revenue' or cost.metric!='cost_of_sales' or revenue.unit!='CNY' or revenue.period_kind!='annual_flow': raise DomainError('INVALID_BASELINE','requires annual revenue and cost')
    r,c=Decimal(revenue.value),Decimal(cost.value)
    if r<=0 or c<0: raise DomainError('INVALID_BASELINE','revenue must be positive; cost nonnegative')
    return r,c

def baseline(revenue:Fact,cost:Fact):
    with localcontext() as ctx:
        ctx.prec=40
        r,c=validated_baseline(revenue,cost);gp=r-c
        return {k:decimal_text(v) for k,v in dict(revenue=r,cost_of_sales=c,gross_profit=gp,gross_margin=gp/r).items()}

def compute(revenue: Fact, cost: Fact, assumptions: Assumptions):
    with localcontext() as ctx:
        ctx.prec=40
        r,c=validated_baseline(revenue,cost)
        dc=c*assumptions.cost_exposure*assumptions.effective_price_shock
        r1=r+assumptions.customer_pass_through*dc; c1=c+dc
        if r1<=0 or c1<0: raise DomainError('INVALID_SCENARIO','nonpositive revenue or negative cost')
        gp0=r-c; gp1=r1-c1; gm0=gp0/r; gm1=gp1/r1
        return {k:decimal_text(v) for k,v in dict(revenue=r1,cost_of_sales=c1,gross_profit=gp1,gross_margin=gm1,delta_gross_profit=gp1-gp0,delta_gross_margin_pp=(gm1-gm0)*100,delta_cost=dc).items()}
