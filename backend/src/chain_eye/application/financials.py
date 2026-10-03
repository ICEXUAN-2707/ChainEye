from uuid import uuid4

from chain_eye.domain.contracts import Calculation,Fact
from chain_eye.domain.decimal_values import decimal_text
from chain_eye.domain.financials import calculate

class FinancialService:
    def __init__(self,repository=None):self.repository=repository
    def compute(self,fact_snapshot:list[Fact],requested_metric_ids:list[str])->list[Calculation]:
        calculations=[]
        for result in calculate(fact_snapshot,requested_metric_ids):
            inputs=list(result.input_facts)
            calculations.append(Calculation(
                id=str(uuid4()),formula_id=result.formula_id,formula_version='1',
                input_fact_ids=[fact.id for fact in inputs],input_revisions={fact.id:fact.revision for fact in inputs},
                assumption_snapshot={},value=decimal_text(result.value) if result.value is not None else None,
                unit=result.unit,status='computed' if result.value is not None else 'not_computable',reason=result.reason,
            ))
        if self.repository:self.repository.save_calculations(calculations)
        return calculations
