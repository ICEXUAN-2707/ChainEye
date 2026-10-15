from typing import Literal

from pydantic import Field,model_validator

from .contracts import Contract


CompanyCode=Literal['CATL','EVE']
CompanyId=Literal['catl','eve-energy']
INDUSTRY_PROFILE_VERSION=1


class SecurityIdentifier(Contract):
    market: Literal['SZSE']
    kind: Literal['stock_code','cninfo_org_id']
    value: str = Field(min_length=1,max_length=32)


class CompanyProfile(Contract):
    id: CompanyId
    company_code: CompanyCode
    legal_name: str = Field(min_length=1,max_length=100)
    aliases: list[str]
    security_ids: list[SecurityIdentifier]
    industry_profile_id: Literal['battery-manufacturing-cn-v1']
    industry_profile_version: int = Field(ge=1)
    profile_version: int = Field(ge=1)
    supported_report_years: list[int]
    report_name_patterns: list[str]
    segment_aliases: dict[Literal['power_battery','energy_storage'],list[str]]
    source_policy: Literal['official_public_disclosure_attribution_required']


class CompanyCollection(Contract):
    items: list[CompanyProfile]
    next_offset: int | None


class IdentityCandidate(Contract):
    source_id: str
    company_id: CompanyId | None
    company_code: CompanyCode | None
    legal_name: str | None
    report_year: int | None
    report_type: Literal['annual_report','unknown']
    status: Literal['identified','unrecognized','ambiguous','conflict']
    evidence_pages: list[int]
    warnings: list[str]
    @model_validator(mode='after')
    def identity_shape(self):
        if any(page<1 for page in self.evidence_pages):raise ValueError('identity evidence pages are one-based')
        if len(set(self.evidence_pages))!=len(self.evidence_pages):raise ValueError('identity evidence pages must be unique')
        if self.status in ('identified','conflict'):
            if None in (self.company_id,self.company_code,self.legal_name,self.report_year):
                raise ValueError('identified identity requires company and report year')
            if self.report_type!='annual_report':raise ValueError('identified identity requires report type')
        return self


class IdentityCandidateCollection(Contract):
    dataset_id: str
    dataset_version: int = Field(ge=1)
    items: list[IdentityCandidate]


class IdentityConfirmation(Contract):
    expected_version: int = Field(ge=1,strict=True)
    company_id: CompanyId
    report_year: int = Field(ge=2000,le=2100)
    report_type: Literal['annual_report']
    reason: str = Field(min_length=1,max_length=1000)


class CapabilityItem(Contract):
    module_id: Literal['M1','M2','M3','M4','M5']
    status: Literal['ready','needs_review','missing_data','unsupported','failed']
    reason_code: str
    required_inputs: list[str]
    missing_inputs: list[str]
    evidence_gaps: list[str]
    supported_actions: list[str]


class CapabilityCollection(Contract):
    dataset_id: str
    dataset_version: int = Field(ge=1)
    company_id: CompanyId
    industry_profile_id: str
    industry_profile_version: int = Field(ge=1)
    items: list[CapabilityItem]


COMPANY_PROFILES=(
    CompanyProfile(
        id='catl',company_code='CATL',legal_name='宁德时代新能源科技股份有限公司',
        aliases=['宁德时代','CATL'],
        security_ids=[
            SecurityIdentifier(market='SZSE',kind='stock_code',value='300750'),
            SecurityIdentifier(market='SZSE',kind='cninfo_org_id',value='9900024733'),
        ],
        industry_profile_id='battery-manufacturing-cn-v1',industry_profile_version=INDUSTRY_PROFILE_VERSION,profile_version=1,
        supported_report_years=[2024,2025],
        report_name_patterns=['宁德时代新能源科技股份有限公司{year}年年度报告全文'],
        segment_aliases={'power_battery':['动力电池系统'],'energy_storage':['储能电池系统']},
        source_policy='official_public_disclosure_attribution_required',
    ),
    CompanyProfile(
        id='eve-energy',company_code='EVE',legal_name='惠州亿纬锂能股份有限公司',
        aliases=['亿纬锂能','EVE Energy'],
        security_ids=[
            SecurityIdentifier(market='SZSE',kind='stock_code',value='300014'),
            SecurityIdentifier(market='SZSE',kind='cninfo_org_id',value='9900008311'),
        ],
        industry_profile_id='battery-manufacturing-cn-v1',industry_profile_version=INDUSTRY_PROFILE_VERSION,profile_version=1,
        supported_report_years=[2024,2025],
        report_name_patterns=['惠州亿纬锂能股份有限公司{year}年年度报告全文'],
        segment_aliases={'power_battery':['动力电池'],'energy_storage':['储能电池']},
        source_policy='official_public_disclosure_attribution_required',
    ),
)

COMPANY_BY_ID={item.id:item for item in COMPANY_PROFILES}
COMPANY_BY_CODE={item.company_code:item for item in COMPANY_PROFILES}


def require_company_profile(company_id):
    try:return COMPANY_BY_ID[company_id]
    except KeyError as exc:raise ValueError('unknown company profile') from exc


class IdentityVersionConflictError(ValueError):
    def __init__(self,current_version):
        self.current_version=current_version
        super().__init__('dataset version changed')


class IdentityCandidateNotFoundError(ValueError):
    pass


def identity_candidate_matches(candidate,company_id,report_year,report_type):
    profile=COMPANY_BY_ID.get(company_id)
    return (
        profile is not None
        and candidate.status=='identified'
        and candidate.company_id==company_id
        and candidate.report_year in (report_year,report_year-1)
        and candidate.report_year in profile.supported_report_years
        and candidate.report_type==report_type
    )


def capability_matrix(dataset,facts,profile=None):
    if dataset.identity_status!='confirmed' or not dataset.company_id:
        return []
    profile=profile or require_company_profile(dataset.company_id)
    valid=[fact for fact in facts if fact.company==profile.company_code and fact.status!='missing']
    present={(fact.metric,fact.segment) for fact in valid}
    review={(fact.metric,fact.segment) for fact in valid if fact.status!='verified'}
    specs={
        'M1':[('revenue','group'),('cost_of_sales','group'),('parent_net_profit','group')],
        'M2':[('operating_cash_flow','group'),('inventory','group'),('accounts_receivable','group')],
        'M5':[('revenue','power_battery'),('cost_of_sales','power_battery'),('revenue','energy_storage'),('cost_of_sales','energy_storage')],
    }
    items=[]
    for module_id in ('M1','M2','M3','M4','M5'):
        if module_id in ('M3','M4'):
            items.append(CapabilityItem(
                module_id=module_id,status='unsupported',reason_code='MODULE_DEFERRED_TO_G8',
                required_inputs=[],missing_inputs=[],evidence_gaps=['研究模块尚未在G6实现'],supported_actions=[],
            ));continue
        required=specs[module_id];missing=[f'{metric}:{segment}' for metric,segment in required if (metric,segment) not in present]
        pending=[f'{metric}:{segment}' for metric,segment in required if (metric,segment) in review]
        if missing:status='missing_data';reason='REQUIRED_FACTS_MISSING'
        elif pending:status='needs_review';reason='FACTS_REQUIRE_REVIEW'
        else:status='ready';reason='REQUIRED_FACTS_VERIFIED'
        items.append(CapabilityItem(
            module_id=module_id,status=status,reason_code=reason,
            required_inputs=[f'{metric}:{segment}' for metric,segment in required],missing_inputs=missing,
            evidence_gaps=pending,supported_actions=['review_facts'] if status=='needs_review' else ([] if status!='ready' else ['run_research']),
        ))
    return items
