from typing import Literal
from pydantic import Field,model_validator
from .contracts import Contract
from .companies import CompanyCode,CompanyId

class DatasetCreate(Contract):
    name: str = Field(min_length=1,max_length=100)
    company: CompanyCode
    year: Literal[2024,2025]
class Dataset(Contract):
    id: str
    name: str
    company: CompanyCode
    year: Literal[2024,2025]
    version: int = Field(ge=1)
    source_ids: list[str]
    created_at: str
    data_basis: Literal['empty','reviewed_fixture','user_uploaded']
    company_id: CompanyId
    company_profile_version: int = Field(ge=1)
    industry_profile_id: Literal['battery-manufacturing-cn-v1']
    industry_profile_version: int = Field(ge=1)
    report_type: Literal['annual_report']
    identity_status: Literal['confirmed','conflict','unconfirmed']
    identity_confirmation_reason: str | None
    @model_validator(mode='before')
    @classmethod
    def legacy_identity(cls,value):
        if not isinstance(value,dict):return value
        value=dict(value);company=value.get('company')
        if 'company_id' not in value and company in ('CATL','EVE'):
            value['company_id']={'CATL':'catl','EVE':'eve-energy'}[company]
        value.setdefault('company_profile_version',1)
        value.setdefault('industry_profile_id','battery-manufacturing-cn-v1')
        value.setdefault('industry_profile_version',1)
        value.setdefault('report_type','annual_report')
        value.setdefault('identity_status','confirmed')
        value.setdefault('identity_confirmation_reason','legacy_explicit_company_selection')
        return value
    @model_validator(mode='after')
    def identity(self):
        expected={'CATL':'catl','EVE':'eve-energy'}[self.company]
        if self.company_id!=expected:raise ValueError('company and company_id mismatch')
        if self.identity_status=='confirmed' and not self.identity_confirmation_reason:
            raise ValueError('confirmed identity requires reason')
        return self

class Source(Contract):
    id: str
    filename: str
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    media_type: Literal['application/pdf','text/csv']
    page_count: int | None = Field(default=None,ge=1)
    url: str | None
    published_date: str | None
    parse_status: Literal['queued','parsed','needs_review','failed']
    data_basis: Literal['reviewed_fixture','user_uploaded']

class SourceAttachment(Contract):
    dataset: Dataset
    source: Source

class DatasetSourceLimitError(ValueError):
    pass
