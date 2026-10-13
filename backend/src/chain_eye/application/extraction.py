import re
from decimal import Decimal
from uuid import NAMESPACE_URL,uuid5

from chain_eye.adapters.pymupdf import PyMuPDFParser
from chain_eye.application.errors import AppError
from chain_eye.application.source_upload import sha256_file
from chain_eye.domain.contracts import Evidence,Fact
from chain_eye.domain.companies import COMPANY_PROFILES,COMPANY_BY_ID,IdentityCandidate
from chain_eye.domain.decimal_values import decimal_text
from chain_eye.domain.extraction import ExtractionError,ExtractionResult

NUMBER=re.compile(r'^-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?$')
BALANCE_METRICS={'total_assets','parent_equity','inventory','accounts_receivable'}

def normalized(text):return re.sub(r'[\s:：（）()]','',text)

PROFILE_RULES={
    'catl':{
        'money_raw_unit':'CNY_thousand','unit_marker':'单位千元',
        'segment_sections':('营业收入及营业成本整体情况',),
        'segment_headers':('营业成本','毛利率'),
        'segment_metrics':(('revenue',0),('cost_of_sales',1),('reported_gross_margin',2)),
    },
    'eve-energy':{
        'money_raw_unit':'CNY_yuan','unit_marker':'单位元',
        'segment_sections':('营业收入和营业成本','营业收入、营业成本的分解信息'),
        'segment_headers':('营业收入','营业成本'),
        'segment_metrics':(('revenue',0),('cost_of_sales',1)),
    },
}


def identify_report(source_id,document):
    matches=[]
    for profile in COMPANY_PROFILES:
        for page in document.pages[:20]:
            text=normalized(page.text)
            for template in profile.report_name_patterns:
                pattern=re.escape(normalized(template)).replace(re.escape('{year}'),r'(20\d{2})')
                for year in re.findall(pattern,text):matches.append((profile,int(year),page.page_no))
    unique={(profile.id,year) for profile,year,_ in matches}
    pages=sorted({page for _,_,page in matches})[:3]
    if len(unique)==1:
        company_id,year=next(iter(unique));profile=COMPANY_BY_ID[company_id]
        return IdentityCandidate(
            source_id=source_id,company_id=profile.id,company_code=profile.company_code,
            legal_name=profile.legal_name,report_year=year,report_type='annual_report',
            status='identified',evidence_pages=pages,warnings=[],
        )
    return IdentityCandidate(
        source_id=source_id,company_id=None,company_code=None,legal_name=None,report_year=None,
        report_type='unknown',status='ambiguous' if unique else 'unrecognized',evidence_pages=pages,
        warnings=['multiple_company_or_year_candidates'] if unique else ['identity_not_recognized'],
    )

def page_with(document,*markers):
    for page in document.pages:
        text=normalized(page.text)
        if all(normalized(marker) in text for marker in markers):return page
    return None


def page_in_section(document,section,labels,max_pages=6):
    start=next((index for index,page in enumerate(document.pages) if normalized(section) in normalized(page.text)),None)
    if start is None:return None
    for page in document.pages[start:start+max_pages]:
        if label_band(page,labels) is not None:return page
    return None


def labels_for_unit(labels,money_raw_unit):
    if money_raw_unit!='CNY_yuan':return labels
    return tuple(label.replace('千元','元') for label in labels)

def label_band(page,labels,min_y=0):
    if page is None:return None
    labels={normalized(label) for label in labels}
    words=[word for word in page.words if word.bbox[0]<230 and word.bbox[1]>=min_y and not NUMBER.fullmatch(word.text)]
    for start in range(len(words)):
        combined=''
        selected=[]
        previous_y=None
        for word in words[start:start+4]:
            if previous_y is not None and word.bbox[1]-previous_y>28:break
            selected.append(word);combined+=normalized(word.text);previous_y=word.bbox[3]
            if combined in labels:
                return min(v.bbox[1] for v in selected),max(v.bbox[3] for v in selected),max(v.bbox[2] for v in selected),tuple(selected)
    return None

def row_values(page,labels,min_y=0):
    band=label_band(page,labels,min_y)
    if band is None:return None,None
    y0,y1,label_x,label_words=band
    values=[word for word in page.words if word.bbox[0]>label_x+4 and NUMBER.fullmatch(word.text) and y0-7<=(word.bbox[1]+word.bbox[3])/2<=y1+7]
    values.sort(key=lambda word:word.bbox[0])
    return values,label_words

def value_under_year(document,page,values,year):
    if not values:return None
    row_y=min(word.bbox[1] for word in values)
    headers=[word for word in page.words if normalized(word.text).startswith(str(year)) and word.bbox[3]<row_y]
    if page.page_no>1:headers.extend(word for word in document.pages[page.page_no-2].words if normalized(word.text).startswith(str(year)))
    if not headers:return None
    pair=min(((abs((value.bbox[0]+value.bbox[2]-header.bbox[0]-header.bbox[2])/2),value) for header in headers for value in values),key=lambda item:item[0])
    return pair[1] if pair[0]<=120 else None

def context_text(document,page):
    if page is None:return ''
    pages=[page.text]
    if page.page_no>1:pages.append(document.pages[page.page_no-2].text)
    return normalized('\n'.join(pages))

def valid_table_context(document,page,year,unit_marker):
    if page is None:return False
    nearby=context_text(document,page)
    current=normalized(page.text)
    return normalized(unit_marker) in nearby and f'{year}年年度报告全文' in current

def segment_table(document,year,labels,rule):
    for page in document.pages:
        if not valid_table_context(document,page,year,rule['unit_marker']):continue
        nearby=context_text(document,page)
        if not any(normalized(marker) in nearby for marker in rule['segment_sections']):continue
        header_words=[word for word in page.words if normalized(word.text) in {normalized(v) for v in rule['segment_headers']}]
        min_y=max((word.bbox[3] for word in header_words),default=0)
        if all(row_values(page,variants,min_y)[0] for variants in labels.values()):return page,min_y
    return None,0

def evidence_excerpt(section,page,label_words,values):
    row=' '.join([*(word.text for word in label_words),*(word.text for word in values)])
    return f'{section}；{row}'[:500]

class AnnualReportExtractor:
    SUMMARY={
        'revenue':('营业收入（千元）','营业收入'),
        'parent_net_profit':('归属于上市公司股东的净利润（千元）','归属于上市公司股东的净利润'),
        'parent_adjusted_net_profit':('归属于上市公司股东的扣除非经常性损益的净利润（千元）','归属于上市公司股东的扣除非经常性损益的净利润'),
        'operating_cash_flow':('经营活动产生的现金流量净额（千元）','经营活动产生的现金流量净额'),
        'total_assets':('资产总额（千元）','资产总额'),
        'parent_equity':('归属于上市公司股东的净资产（千元）','归属于上市公司股东的净资产'),
    }
    STATEMENTS={
        'cost_of_sales':('其中：营业成本','营业成本'),
        'inventory':('存货',),
        'accounts_receivable':('应收账款',),
    }
    SEGMENT_CODES=('power_battery','energy_storage')

    def extract(self,dataset,source,document):
        candidate=identify_report(source.id,document)
        if candidate.status!='identified':
            return ExtractionResult(facts=(),evidence=(),parse_status='needs_review',warnings=tuple(candidate.warnings),identity_candidate=candidate)
        profile=COMPANY_BY_ID[candidate.company_id];year=candidate.report_year
        if dataset.identity_status!='confirmed':
            return ExtractionResult(facts=(),evidence=(),parse_status='needs_review',warnings=('identity_unconfirmed',),identity_candidate=candidate)
        if (
            dataset.company_profile_version!=profile.profile_version
            or dataset.industry_profile_id!=profile.industry_profile_id
            or dataset.industry_profile_version!=profile.industry_profile_version
        ):
            return ExtractionResult(facts=(),evidence=(),parse_status='needs_review',warnings=('profile_version_mismatch',),identity_candidate=candidate)
        if profile.id!=dataset.company_id or year not in profile.supported_report_years or year>dataset.year or year<dataset.year-1:
            conflict=candidate.model_copy(update={'status':'conflict','warnings':['dataset_document_identity_conflict']})
            return ExtractionResult(facts=(),evidence=(),parse_status='needs_review',warnings=('identity_conflict',),identity_candidate=conflict)
        rule=PROFILE_RULES[profile.id]
        summary=page_with(document,'主要会计数据和财务指标')
        summary=summary if valid_table_context(document,summary,year,rule['unit_marker']) else None
        segment_labels={key:tuple(profile.segment_aliases[key]) for key in self.SEGMENT_CODES}
        segment,segment_min_y=segment_table(document,year,segment_labels,rule)
        found=[]
        for metric,labels in self.SUMMARY.items():
            labels=labels_for_unit(labels,rule['money_raw_unit'])
            found.append(self._candidate(document,dataset,source,profile,year,'group',metric,summary,labels,0,f"主要会计数据和财务指标；{rule['unit_marker']}",rule['money_raw_unit'],year_column=True))
        for metric,labels in self.STATEMENTS.items():
            section='合并资产负债表' if metric in ('inventory','accounts_receivable') else '合并利润表'
            target=page_in_section(document,section,labels)
            target=target if valid_table_context(document,target,year,rule['unit_marker']) else None
            found.append(self._candidate(
                document,dataset,source,profile,year,'group',metric,target,labels,0,
                f"合并财务报表；{rule['unit_marker']}",rule['money_raw_unit'],
                year_column=metric not in BALANCE_METRICS,
            ))
        for segment_name,labels in segment_labels.items():
            for metric,index in rule['segment_metrics']:
                found.append(self._candidate(document,dataset,source,profile,year,segment_name,metric,segment,labels,index,f"营业收入和营业成本；{rule['unit_marker']}；分产品",rule['money_raw_unit'],segment_min_y))
        facts=tuple(item[0] for item in found);evidence=tuple(item[1] for item in found if item[1] is not None)
        missing=sum(fact.status=='missing' for fact in facts)
        return ExtractionResult(facts=facts,evidence=evidence,parse_status='parsed' if missing==0 else 'needs_review',warnings=(() if missing==0 else (f'{missing}_target_fields_missing',)),identity_candidate=candidate)

    def _candidate(self,document,dataset,source,profile,year,segment,metric,page,labels,value_index,section,money_raw_unit,min_y=0,year_column=False):
        values,label_words=row_values(page,labels,min_y)
        raw_unit='percent' if metric=='reported_gross_margin' else money_raw_unit
        period_kind='point_in_time' if metric in BALANCE_METRICS else 'annual_flow'
        fact_id=str(uuid5(NAMESPACE_URL,f'chain-eye/fact/{dataset.id}/{source.id}/{year}/{segment}/{metric}'))
        common=dict(id=fact_id,revision=1,company=profile.company_code,metric=metric,segment=segment,statement_scope='consolidated',period_kind=period_kind,period_start=None if period_kind=='point_in_time' else f'{year}-01-01',period_end=f'{year}-12-31',currency='CNY',raw_unit=raw_unit,restatement_status='not_restated')
        selected=value_under_year(document,page,values,year) if year_column else (values[value_index] if values and value_index<len(values) else None)
        if selected is None:
            fact=Fact(**common,value=None,unit='ratio' if raw_unit=='percent' else 'CNY',raw_value=None,status='missing',evidence_ids=[],missing_reason='目标字段未在受支持的表头、行名、年份列和单位上下文中唯一识别')
            return fact,None
        raw=selected.text.replace(',','').removesuffix('%')
        value=Decimal(raw)/100 if raw_unit=='percent' else (Decimal(raw)*1000 if raw_unit=='CNY_thousand' else Decimal(raw))
        evidence_id=str(uuid5(NAMESPACE_URL,f'chain-eye/evidence/{source.id}/{year}/{segment}/{metric}/{page.page_no}'))
        excerpt=evidence_excerpt(section,page,label_words,values)
        evidence=Evidence(id=evidence_id,source_id=source.id,locator_kind='pdf',pdf_page=page.page_no,printed_page=str(page.page_no),bbox=list(selected.bbox),url=None,selector=None,excerpt=excerpt,sha256=source.sha256)
        fact=Fact(**common,value=decimal_text(value),unit='ratio' if raw_unit=='percent' else 'CNY',raw_value=raw,status='extracted',evidence_ids=[evidence_id],missing_reason=None)
        return fact,evidence

class ExtractionService:
    def __init__(self,repository,parser=None,extractor=None):
        self.repository=repository;self.parser=parser or PyMuPDFParser();self.extractor=extractor or AnnualReportExtractor()

    def execute(self,dataset_id,source_id):
        dataset=self.repository.get_dataset(dataset_id);source=self.repository.get_source(source_id)
        if dataset is None or source is None:raise AppError('NOT_FOUND','数据包或来源不存在',404)
        path=self.repository.source_path(source_id)
        if path is None or not path.exists():raise AppError('NOT_FOUND','来源原件不存在',404)
        if sha256_file(path)!=source.sha256:raise AppError('SOURCE_HASH_MISMATCH','原件与保存的来源哈希不一致',409)
        try:
            document=self.parser.parse(source_id,path.read_bytes())
            result=self.extractor.extract(dataset,source,document)
        except ExtractionError:
            result=ExtractionResult(facts=(),evidence=(),parse_status='failed',warnings=('pdf_text_parsing_failed',))
        return self.repository.apply_extraction(dataset_id,source_id,result)
