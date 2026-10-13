from chain_eye.application.errors import AppError
from chain_eye.domain.companies import (
    CapabilityCollection,CapabilityItem,IdentityCandidateCollection,
    IdentityCandidateNotFoundError,IdentityVersionConflictError,capability_matrix,
)


class CompanyIdentityService:
    def __init__(self,repository):self.repository=repository

    def _profile_for_dataset(self,dataset):
        profile=self.repository.get_company_profile(dataset.company_id,dataset.company_profile_version)
        if profile is None or profile.industry_profile_id!=dataset.industry_profile_id or profile.industry_profile_version!=dataset.industry_profile_version:
            raise AppError('STALE_SNAPSHOT','数据包绑定的企业或行业配置版本不可用',409)
        return profile

    def candidates(self,dataset_id,version):
        dataset=self.repository.get_dataset(dataset_id,version)
        if dataset is None:raise AppError('NOT_FOUND','数据包或版本不存在',404)
        return IdentityCandidateCollection(
            dataset_id=dataset_id,dataset_version=version,
            items=self.repository.identity_candidates(dataset_id,version),
        )

    def confirm(self,dataset_id,request):
        try:dataset=self.repository.confirm_identity(dataset_id,request)
        except IdentityVersionConflictError as exc:
            raise AppError('IDENTITY_CONFLICT','数据包版本已变化，身份确认未写入',409,details={'current_version':exc.current_version}) from None
        except IdentityCandidateNotFoundError as exc:
            raise AppError('IDENTITY_UNCONFIRMED','没有与确认内容匹配的文档身份候选',409,details={'reason':str(exc)}) from None
        if dataset is None:raise AppError('NOT_FOUND','数据包不存在',404)
        return dataset

    def capabilities(self,dataset_id,version,industry_profile_version):
        dataset=self.repository.get_dataset(dataset_id,version)
        if dataset is None:raise AppError('NOT_FOUND','数据包或版本不存在',404)
        if dataset.industry_profile_version!=industry_profile_version:
            raise AppError(
                'STALE_SNAPSHOT','请求的行业配置版本与数据包快照不一致',409,
                details={'requested_version':industry_profile_version,'snapshot_version':dataset.industry_profile_version},
            )
        profile=self._profile_for_dataset(dataset)
        candidates=self.repository.identity_candidates(dataset_id,version)
        conflict=any(item.status in ('conflict','ambiguous') for item in candidates)
        if dataset.identity_status!='confirmed' or conflict:
            reason='IDENTITY_CONFLICT' if conflict else 'IDENTITY_UNCONFIRMED'
            items=[CapabilityItem(
                module_id=module_id,status='failed',reason_code=reason,required_inputs=[],missing_inputs=[],
                evidence_gaps=['请先核对并确认企业与报告年度'],supported_actions=['confirm_identity'],
            ) for module_id in ('M1','M2','M3','M4','M5')]
        else:items=capability_matrix(dataset,self.repository.facts(dataset_id,version),profile)
        return CapabilityCollection(
            dataset_id=dataset_id,dataset_version=version,company_id=profile.id,
            industry_profile_id=profile.industry_profile_id,
            industry_profile_version=dataset.industry_profile_version,items=items,
        )

    def require_runnable_identity(self,dataset_id,version):
        dataset=self.repository.get_dataset(dataset_id,version)
        if dataset is None:raise AppError('NOT_FOUND','数据包或版本不存在',404)
        self._profile_for_dataset(dataset)
        candidates=self.repository.identity_candidates(dataset_id,version)
        if any(item.status in ('conflict','ambiguous') for item in candidates):
            raise AppError('IDENTITY_CONFLICT','文档身份与数据包身份冲突，禁止执行公司结论',409)
        if dataset.identity_status!='confirmed':
            raise AppError('IDENTITY_UNCONFIRMED','企业身份尚未确认，禁止执行公司结论',409)
        return dataset
