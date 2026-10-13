import argparse
import hashlib
import json
import tempfile
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from chain_eye.adapters.pymupdf import PyMuPDFParser
from chain_eye.api.app import create_app
from chain_eye.application.extraction import AnnualReportExtractor
from chain_eye.domain.datasets import Dataset,Source


ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/'data/company_sources.json'


def record_for(report_id):
    reports=json.loads(MANIFEST.read_text(encoding='utf-8'))['reports']
    try:return next(item for item in reports if item['id']==report_id)
    except StopIteration as exc:raise SystemExit(f'unknown report id: {report_id}') from exc


def validate(record,path):
    content=path.read_bytes();digest=hashlib.sha256(content).hexdigest()
    if digest!=record['sha256']:raise ValueError('local report SHA256 does not match manifest')
    dataset=Dataset(
        id=f"validation-{record['id']}",name='G6 native PDF validation',company=record['company_code'],
        company_id=record['company_id'],year=record['report_year'],version=1,source_ids=[record['id']],
        created_at='2026-10-12T00:00:00+08:00',data_basis='user_uploaded',identity_status='confirmed',
        identity_confirmation_reason='official_manifest_validation',
    )
    source=Source(
        id=record['id'],filename=record['filename'],sha256=digest,media_type='application/pdf',
        page_count=record['pages'],url=record['url'],published_date=record['published_date'],
        parse_status='queued',data_basis='user_uploaded',
    )
    document=PyMuPDFParser().parse(source.id,content)
    result=AnnualReportExtractor().extract(dataset,source,document)
    missing=[f'{fact.metric}:{fact.segment}' for fact in result.facts if fact.status=='missing']
    if document.page_count!=record['pages']:raise ValueError('parsed page count does not match manifest')
    if result.identity_candidate is None or result.identity_candidate.status!='identified':raise ValueError('report identity was not identified')
    if result.identity_candidate.company_id!=record['company_id'] or result.identity_candidate.report_year!=record['report_year']:
        raise ValueError('identified company/year does not match manifest')
    if result.parse_status!='parsed' or missing:raise ValueError(f'report extraction incomplete: {missing}')
    if len(result.facts)!=13 or len(result.evidence)!=13:raise ValueError('unexpected EVE extraction field count')
    if any(fact.raw_unit!='CNY_yuan' or Decimal(fact.value)!=Decimal(fact.raw_value) for fact in result.facts):
        raise ValueError('yuan normalization invariant failed')
    return {
        'report_id':record['id'],'validation_role':record['validation_role'],'sha256':digest,
        'pages':document.page_count,'identity':result.identity_candidate.model_dump(mode='json'),
        'parse_status':result.parse_status,'fact_count':len(result.facts),'missing_count':len(missing),
        'facts':[{
            'metric':fact.metric,'segment':fact.segment,'period_end':fact.period_end,
            'raw_value':fact.raw_value,'raw_unit':fact.raw_unit,'value':fact.value,'unit':fact.unit,
            'status':fact.status,'evidence_id':fact.evidence_ids[0],
        } for fact in result.facts],
    }


def validate_api_flow(record,path):
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary);app=create_app(root/'validation.sqlite',seed=False,upload_dir=root/'sources')
        with TestClient(app,base_url='http://localhost',client=('127.0.0.1',50000)) as client:
            created=client.post('/api/v1/datasets',json={
                'name':f"{record['id']} API validation",'company':record['company_code'],'year':record['report_year'],
            })
            if created.status_code!=201:raise ValueError(f'dataset creation failed: {created.status_code}')
            dataset=created.json()
            with path.open('rb') as stream:
                uploaded=client.post(
                    f"/api/v1/datasets/{dataset['id']}/sources",
                    files={'file':(record['filename'],stream,'application/pdf')},
                    data={'url':record['url'],'published_date':record['published_date']},
                )
            if uploaded.status_code!=201:raise ValueError(f'API upload failed: {uploaded.status_code} {uploaded.text[:500]}')
            attachment=uploaded.json();version=attachment['dataset']['version']
            facts=client.get(f"/api/v1/datasets/{dataset['id']}/facts?version={version}")
            identities=client.get(f"/api/v1/datasets/{dataset['id']}/identity-candidates?version={version}")
            capabilities=client.get(f"/api/v1/datasets/{dataset['id']}/capabilities?version={version}&industry_profile_version=1")
            if any(response.status_code!=200 for response in (facts,identities,capabilities)):raise ValueError('API validation readback failed')
            fact_items=facts.json()['items'];identity_items=identities.json()['items'];capability_items=capabilities.json()['items']
            if len(fact_items)!=13 or any(item['company']!='EVE' for item in fact_items):raise ValueError('API fact isolation/count failed')
            if len(identity_items)!=1 or identity_items[0]['status']!='identified':raise ValueError('API identity readback failed')
            status={item['module_id']:item['status'] for item in capability_items}
            if any(status[module]!='needs_review' for module in ('M1','M2','M5')):raise ValueError('API review capability state failed')
            if any(status[module]!='unsupported' for module in ('M3','M4')):raise ValueError('API deferred capability state failed')
            return {
                'dataset_id':dataset['id'],'dataset_version':version,'source_id':attachment['source']['id'],
                'source_parse_status':attachment['source']['parse_status'],'fact_count':len(fact_items),
                'identity_status':identity_items[0]['status'],'capabilities':status,
            }


def main():
    parser=argparse.ArgumentParser(description='Validate one locally fetched company report through the G6 deterministic extractor.')
    parser.add_argument('--report',required=True)
    parser.add_argument('--input-dir',type=Path,default=ROOT/'.runtime/company-sources')
    parser.add_argument('--api-flow',action='store_true',help='Also execute upload, persistence and readback through the real HTTP application.')
    args=parser.parse_args();record=record_for(args.report)
    path=(args.input_dir.resolve()/record['filename']).resolve()
    if not path.is_relative_to(args.input_dir.resolve()):raise SystemExit('unsafe report filename')
    if not path.is_file():raise SystemExit(f'missing local report: {path}; run tools/fetch_company_report.py first')
    result=validate(record,path)
    if args.api_flow:result['api_flow']=validate_api_flow(record,path)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
