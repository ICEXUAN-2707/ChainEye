from decimal import Decimal

from pydantic import ValidationError

from chain_eye.application.errors import AppError
from chain_eye.domain.contracts import Fact
from chain_eye.domain.decimal_values import decimal_text
from chain_eye.domain.review import EvidenceScopeError,FactNotFoundError,FactRevisionConflictError,FactScopeError

class FactReviewService:
    def __init__(self,repository):self.repository=repository

    def correct(self,fact_id,request):
        try:context=self.repository.get_current_fact_context(fact_id)
        except FactScopeError:raise AppError('SCOPE_MISMATCH','事实同时出现在多个当前数据包中，无法确定更正范围',409) from None
        if context is None:raise AppError('NOT_FOUND','当前数据包中不存在该事实',404)
        dataset,current=context
        if current.revision!=request.expected_revision:
            raise AppError('REVISION_CONFLICT','事实已被其他复核更新',409,details={'current_revision':current.revision})
        raw_value=request.raw_value
        if request.status!='missing' and raw_value is None:
            value=Decimal(request.value)
            raw_value=decimal_text(value/1000 if current.raw_unit=='CNY_thousand' else value*100)
        evidence_ids=list(dict.fromkeys(request.evidence_ids))
        payload={**current.model_dump(),'revision':current.revision+1,'value':request.value,'raw_value':raw_value,'status':request.status,'evidence_ids':evidence_ids,'missing_reason':request.missing_reason}
        try:updated=Fact.model_validate(payload)
        except ValidationError as exc:raise AppError('INVALID_INPUT','更正值与原值、单位或状态不一致',422,details={'fields':[{'loc':list(item['loc']),'message':item['msg'],'type':item['type']} for item in exc.errors()]}) from None
        try:return self.repository.correct_fact(dataset.id,request.expected_revision,updated,request.reason)
        except FactNotFoundError:raise AppError('NOT_FOUND','当前数据包中不存在该事实',404) from None
        except FactRevisionConflictError as exc:raise AppError('REVISION_CONFLICT','事实已被其他复核更新',409,details={'current_revision':exc.current_revision}) from None
        except (EvidenceScopeError,FactScopeError):raise AppError('SCOPE_MISMATCH','事实或证据不属于当前数据包版本',409) from None
