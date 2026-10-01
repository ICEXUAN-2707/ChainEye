from decimal import Decimal
from datetime import date
from typing import Literal, Annotated
import re
from pydantic import BeforeValidator, WithJsonSchema
from pydantic import BaseModel, ConfigDict, Field, model_validator

def decimal_string(v):
    if not isinstance(v,str) or not re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?",v):
        raise ValueError('decimal must be a plain decimal string')
    return v
DecimalInput=Annotated[Decimal, BeforeValidator(decimal_string), WithJsonSchema({'type':'string','pattern':r'^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$'})]
DecimalText=Annotated[str, BeforeValidator(decimal_string)]

class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Evidence(Contract):
    id: str
    source_id: str
    locator_kind: Literal['pdf','html']
    pdf_page: int | None = Field(default=None, ge=1)
    printed_page: str | None = None
    bbox: list[float] | None = None
    url: str | None = None
    selector: str | None = None
    excerpt: str
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    @model_validator(mode='after')
    def locator(self):
        if self.locator_kind == 'pdf' and self.pdf_page is None: raise ValueError('pdf_page required')
        if self.locator_kind == 'html' and not self.url: raise ValueError('url required')
        if self.bbox is not None and (len(self.bbox)!=4 or self.bbox[0]>self.bbox[2] or self.bbox[1]>self.bbox[3]): raise ValueError('invalid bbox')
        return self

class Fact(Contract):
    id: str
    revision: int = Field(default=1, ge=1)
    company: str
    metric: Literal["revenue","cost_of_sales","parent_net_profit","parent_adjusted_net_profit","operating_cash_flow","total_assets","parent_equity","inventory","accounts_receivable","reported_gross_margin"]
    segment: Literal['group','power_battery','energy_storage']
    statement_scope: Literal['consolidated']
    period_kind: Literal['annual_flow','point_in_time']
    period_start: str | None = None
    period_end: str
    currency: Literal['CNY'] = 'CNY'
    value: DecimalText | None
    unit: Literal['CNY','ratio']
    raw_value: DecimalText | None
    raw_unit: Literal['CNY_thousand','percent']
    status: Literal['extracted','needs_review','verified','missing','conflict']
    evidence_ids: list[str]
    missing_reason: str | None = None
    restatement_status: Literal['not_restated','restated','unknown'] = 'unknown'
    @model_validator(mode='after')
    def completeness(self):
        if self.status=='missing':
            if self.value is not None or not self.missing_reason: raise ValueError('missing requires null/reason')
        else:
            if self.value is None: raise ValueError('value required')
            if not Decimal(self.value).is_finite(): raise ValueError('finite decimal required')
        if self.status=='verified' and not self.evidence_ids: raise ValueError('verified fact requires evidence')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',self.period_end): raise ValueError('ISO date required')
        end=date.fromisoformat(self.period_end)
        if self.period_kind=='annual_flow':
            if not self.period_start: raise ValueError('flow requires start')
            start=date.fromisoformat(self.period_start)
            if self.period_start != f'{end.year}-01-01' or self.period_end!=f'{end.year}-12-31': raise ValueError('annual flow requires full calendar year')
        elif self.period_start is not None: raise ValueError('point-in-time has no start')
        if self.unit=='ratio' and self.raw_unit!='percent': raise ValueError('ratio requires percent source')
        if self.unit=='CNY' and self.raw_unit!='CNY_thousand': raise ValueError('money requires thousand source')
        balances={'total_assets','parent_equity','inventory','accounts_receivable'}
        if (self.metric in balances)!=(self.period_kind=='point_in_time'): raise ValueError('metric period kind mismatch')
        if self.metric=='reported_gross_margin' and self.unit!='ratio': raise ValueError('margin must use ratio')
        if self.metric!='reported_gross_margin' and self.unit!='CNY': raise ValueError('monetary metric must use CNY')
        if self.value is not None and self.raw_value is not None:
            raw=Decimal(self.raw_value)
            expected=raw*1000 if self.raw_unit=='CNY_thousand' else raw/100
            if Decimal(self.value)!=expected: raise ValueError('raw/normalized value mismatch')
        if self.status=='verified' and self.raw_value is None: raise ValueError('verified requires raw value')
        return self

class Assumptions(Contract):
    cost_exposure: DecimalInput = Field(ge=0, le=1)
    effective_price_shock: DecimalInput = Field(ge=Decimal('-0.5'), le=Decimal('0.5'))
    customer_pass_through: DecimalInput = Field(ge=0, le=1)
    basis: Literal['user_assumption','research_assumption']
    acknowledged: Literal[True]
    @model_validator(mode='before')
    @classmethod
    def acknowledgement(cls,data):
        if isinstance(data,dict) and data.get('acknowledged') is not True: raise ValueError('explicit true required')
        return data
    evidence_ids: list[str] = Field(default_factory=list)

class ScenarioRequest(Contract):
    dataset_id: str
    dataset_version: int = Field(ge=1)
    revenue_fact_id: str
    cost_fact_id: str
    revenue_revision: int = Field(ge=1)
    cost_revision: int = Field(ge=1)
    model_version: Literal['static-gross-profit-v1']
    assumptions: Assumptions

class Calculation(Contract):
    id: str
    formula_id: str
    formula_version: str
    input_fact_ids: list[str]
    input_revisions: dict[str,int]
    assumption_snapshot: dict[str,str]
    value: DecimalText | None
    unit: Literal['CNY','ratio','pp']
    status: Literal['computed','not_computable']
    reason: str | None = None
    @model_validator(mode='after')
    def computability(self):
        if self.status=='computed' and self.value is None: raise ValueError('computed requires value')
        if self.status=='not_computable' and (self.value is not None or not self.reason): raise ValueError('not_computable needs null/reason')
        if set(self.input_fact_ids)!=set(self.input_revisions): raise ValueError('revision keys must match input facts')
        return self

class Claim(Contract):
    id: str
    kind: Literal['fact','calculation','inference','opinion','hypothesis']
    text: str
    evidence_ids: list[str]
    calculation_ids: list[str]
    assumption_ids: list[str]
    counter_evidence_ids: list[str]
    limitations: list[str]
    review_status: Literal['pending','supported','insufficient','rejected']

class ScenarioBaseline(Contract):
    revenue: DecimalText
    cost_of_sales: DecimalText
    gross_profit: DecimalText
    gross_margin: DecimalText
class ScenarioOutputs(ScenarioBaseline):
    delta_gross_profit: DecimalText
    delta_gross_margin_pp: DecimalText
    delta_cost: DecimalText
class AssumptionRecord(Contract):
    id: str
    values: Assumptions
class ScenarioResult(Contract):
    scenario_id: str
    model_version: str
    dataset_id: str
    dataset_version: int = Field(ge=1)
    revenue_fact_id: str
    cost_fact_id: str
    input_revisions: dict[str,int]
    assumption_id: str
    baseline: ScenarioBaseline
    assumptions: Assumptions
    outputs: ScenarioOutputs
    calculation_ids: list[str]
    limitations: list[str]
    mode: Literal['conditional_scenario'] = 'conditional_scenario'

class ErrorBody(Contract):
    code: str
    message: str
    details: dict = Field(default_factory=dict)
    retryable: bool
    request_id: str
