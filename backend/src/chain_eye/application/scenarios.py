"""R3 scenario use case: validate an immutable snapshot, compute, and persist atomically."""
import hashlib
import json
from datetime import datetime,timedelta,timezone
from uuid import uuid4

from chain_eye.application.errors import AppError
from chain_eye.domain.contracts import Calculation,ScenarioBaseline,ScenarioOutputs,ScenarioRequest,ScenarioResult
from chain_eye.domain.decimal_values import decimal_text
from chain_eye.domain.scenario import (
    DomainError,IdempotencyConflictError,ScenarioEvidenceNotFoundError,
    ScenarioEvidenceScopeError,ScenarioFactNotFoundError,ScenarioFactScopeError,
    baseline,compute,
)

OUTPUT_SPECS=(
    ('baseline-gross-profit','gross_profit','CNY',('revenue','cost')),
    ('baseline-gross-margin','gross_margin','ratio',('revenue','cost')),
    ('scenario-delta-cost','delta_cost','CNY',('cost',)),
    ('scenario-revenue','revenue','CNY',('revenue','cost')),
    ('scenario-cost-of-sales','cost_of_sales','CNY',('cost',)),
    ('scenario-gross-profit','gross_profit','CNY',('revenue','cost')),
    ('scenario-gross-margin','gross_margin','ratio',('revenue','cost')),
    ('scenario-delta-gross-profit','delta_gross_profit','CNY',('cost',)),
    ('scenario-delta-gross-margin-pp','delta_gross_margin_pp','pp',('revenue','cost')),
)

class ScenarioExecutionService:
    def __init__(self,repository):self.repository=repository

    @staticmethod
    def _request_hash(request):
        canonical=json.dumps(request.model_dump(mode='json'),sort_keys=True,separators=(',',':'),ensure_ascii=False)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def execute(self,request:ScenarioRequest,idempotency_key:str)->ScenarioResult:
        if self.repository.get_dataset(request.dataset_id,request.dataset_version) is None:
            raise AppError('NOT_FOUND','数据包或版本不存在',404)
        request_hash=self._request_hash(request);scope=f'scenario:{request.dataset_id}'
        try:
            cached=self.repository.get_idempotent_scenario(scope,idempotency_key,request_hash)
        except IdempotencyConflictError as exc:
            raise AppError('INVALID_INPUT','Idempotency-Key 已用于不同请求',409,details={'reason':'IDEMPOTENCY_KEY_REUSED'}) from exc
        if cached is not None:return cached
        try:
            revenue=self.repository.get_fact_for_snapshot(request.dataset_id,request.dataset_version,request.revenue_fact_id,request.revenue_revision)
            cost=self.repository.get_fact_for_snapshot(request.dataset_id,request.dataset_version,request.cost_fact_id,request.cost_revision)
            self.repository.validate_evidence_snapshot(request.dataset_id,request.dataset_version,request.assumptions.evidence_ids)
            base=baseline(revenue,cost);outputs=compute(revenue,cost,request.assumptions)
        except (ScenarioFactNotFoundError,ScenarioEvidenceNotFoundError) as exc:
            raise AppError('NOT_FOUND',str(exc) or '引用资源不存在',404) from exc
        except (ScenarioFactScopeError,ScenarioEvidenceScopeError) as exc:
            raise AppError('SCOPE_MISMATCH',str(exc) or '引用不属于指定数据快照',409) from exc
        except DomainError as exc:
            status=422 if exc.code=='INVALID_SCENARIO' else 409
            raise AppError(exc.code,str(exc),status) from exc

        assumption_snapshot={
            'cost_exposure':decimal_text(request.assumptions.cost_exposure),
            'effective_price_shock':decimal_text(request.assumptions.effective_price_shock),
            'customer_pass_through':decimal_text(request.assumptions.customer_pass_through),
            'basis':request.assumptions.basis,'acknowledged':'true',
            'evidence_ids':json.dumps(request.assumptions.evidence_ids,separators=(',',':'),ensure_ascii=False),
        }
        facts={'revenue':revenue,'cost':cost};calculations=[]
        for formula_id,key,unit,dependencies in OUTPUT_SPECS:
            selected=[facts[name] for name in dependencies]
            value=base[key] if formula_id.startswith('baseline-') else outputs[key]
            calculations.append(Calculation(
                id=str(uuid4()),formula_id=formula_id,formula_version='1',
                input_fact_ids=[fact.id for fact in selected],
                input_revisions={fact.id:fact.revision for fact in selected},
                assumption_snapshot={} if formula_id.startswith('baseline-') else assumption_snapshot,
                value=value,unit=unit,status='computed',
            ))
        result=ScenarioResult(
            scenario_id=str(uuid4()),model_version=request.model_version,
            dataset_id=request.dataset_id,dataset_version=request.dataset_version,
            revenue_fact_id=revenue.id,cost_fact_id=cost.id,
            input_revisions={revenue.id:revenue.revision,cost.id:cost.revision},
            assumption_id=str(uuid4()),baseline=ScenarioBaseline(**base),
            assumptions=request.assumptions,outputs=ScenarioOutputs(**outputs),
            calculation_ids=[item.id for item in calculations],
            limitations=['条件情景，不是预测或置信区间','固定销量、业务结构及其他投入'],
        )
        try:
            return self.repository.save_scenario_idempotently(
                scope,idempotency_key,request_hash,
                result,calculations,datetime.now(timezone.utc)+timedelta(hours=24),
            )
        except IdempotencyConflictError as exc:
            raise AppError('INVALID_INPUT','Idempotency-Key 已用于不同请求',409,details={'reason':'IDEMPOTENCY_KEY_REUSED'}) from exc
