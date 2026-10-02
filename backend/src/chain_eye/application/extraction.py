import re
from collections import Counter
from decimal import Decimal
from uuid import NAMESPACE_URL,uuid5

from chain_eye.adapters.pymupdf import PyMuPDFParser
from chain_eye.application.errors import AppError
from chain_eye.application.source_upload import sha256_file
from chain_eye.domain.contracts import Evidence,Fact
from chain_eye.domain.decimal_values import decimal_text
from chain_eye.domain.extraction import ExtractionError,ExtractionResult

NUMBER=re.compile(r'^-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?$')
BALANCE_METRICS={'total_assets','parent_equity','inventory','accounts_receivable'}

def normalized(text):return re.sub(r'[\s:：（）()]','',text)

def report_year(document):
    years=[]
    pattern=re.compile(r'宁德时代新能源科技股份有限公司(20\d{2})年年度报告全文')
    for page in document.pages:
        years.extend(pattern.findall(normalized(page.text)))
    return int(Counter(years).most_common(1)[0][0]) if years else None

def page_with(document,*markers):
    for page in document.pages:
        text=normalized(page.text)
        if all(normalized(marker) in text for marker in markers):return page
    return None

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

def valid_table_context(document,page,year):
    if page is None:return False
    nearby=context_text(document,page)
    current=normalized(page.text)
    return '单位千元' in nearby and f'{year}年年度报告全文' in current

def segment_table(document,year,labels):
    header_markers=('营业收入及营业成本整体情况','营业成本','毛利率')
    for page in document.pages:
        if not valid_table_context(document,page,year):continue
        nearby=context_text(document,page)
        if normalized(header_markers[0]) not in nearby:continue
        header_words=[word for word in page.words if normalized(word.text) in {normalized(v) for v in header_markers[1:]}]
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
    SEGMENTS={'power_battery':('动力电池系统',),'energy_storage':('储能电池系统',)}

    def extract(self,dataset,source,document):
        year=report_year(document)
        if year not in (2024,2025) or year>dataset.year or year<dataset.year-1:
            return ExtractionResult(facts=(),evidence=(),parse_status='needs_review',warnings=('unsupported_company_or_report_year',))
        summary=page_with(document,'主要会计数据和财务指标')
        balance=page_with(document,'合并资产负债表','应收账款','存货')
        profit=page_with(document,'合并利润表','营业总成本','营业成本')
        summary=summary if valid_table_context(document,summary,year) else None
        balance=balance if valid_table_context(document,balance,year) else None
        profit=profit if valid_table_context(document,profit,year) else None
        segment,segment_min_y=segment_table(document,year,self.SEGMENTS)
        found=[]
        for metric,labels in self.SUMMARY.items():found.append(self._candidate(document,dataset,source,year,'group',metric,summary,labels,0,'主要会计数据和财务指标；单位：千元',year_column=True))
        for metric,labels in self.STATEMENTS.items():
            target=balance if metric in ('inventory','accounts_receivable') else profit
            found.append(self._candidate(document,dataset,source,year,'group',metric,target,labels,0,'合并财务报表；单位：千元',year_column=True))
        for segment_name,labels in self.SEGMENTS.items():
            for index,metric in enumerate(('revenue','cost_of_sales','reported_gross_margin')):
                found.append(self._candidate(document,dataset,source,year,segment_name,metric,segment,labels,index,'营业收入及营业成本整体情况；单位：千元；分产品',segment_min_y))
        facts=tuple(item[0] for item in found);evidence=tuple(item[1] for item in found if item[1] is not None)
        missing=sum(fact.status=='missing' for fact in facts)
        return ExtractionResult(facts=facts,evidence=evidence,parse_status='parsed' if missing==0 else 'needs_review',warnings=(() if missing==0 else (f'{missing}_target_fields_missing',)))

    def _candidate(self,document,dataset,source,year,segment,metric,page,labels,value_index,section,min_y=0,year_column=False):
        values,label_words=row_values(page,labels,min_y)
        raw_unit='percent' if metric=='reported_gross_margin' else 'CNY_thousand'
        period_kind='point_in_time' if metric in BALANCE_METRICS else 'annual_flow'
        fact_id=str(uuid5(NAMESPACE_URL,f'chain-eye/fact/{dataset.id}/{source.id}/{year}/{segment}/{metric}'))
        common=dict(id=fact_id,revision=1,company='CATL',metric=metric,segment=segment,statement_scope='consolidated',period_kind=period_kind,period_start=None if period_kind=='point_in_time' else f'{year}-01-01',period_end=f'{year}-12-31',currency='CNY',raw_unit=raw_unit,restatement_status='not_restated')
        selected=value_under_year(document,page,values,year) if year_column else (values[value_index] if values and value_index<len(values) else None)
        if selected is None:
            fact=Fact(**common,value=None,unit='ratio' if raw_unit=='percent' else 'CNY',raw_value=None,status='missing',evidence_ids=[],missing_reason='目标字段未在受支持的表头、行名、年份列和单位上下文中唯一识别')
            return fact,None
        raw=selected.text.replace(',','').removesuffix('%')
        value=Decimal(raw)/100 if raw_unit=='percent' else Decimal(raw)*1000
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
