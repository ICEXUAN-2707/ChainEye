import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request,urlopen

import fitz


ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/'data/company_sources.json'
ALLOWED_HOSTS={'static.cninfo.com.cn'}
MAX_BYTES=30*1024*1024


def load_report(report_id):
    manifest=json.loads(MANIFEST.read_text(encoding='utf-8'))
    try:return next(item for item in manifest['reports'] if item['id']==report_id)
    except StopIteration as exc:raise SystemExit(f'unknown report id: {report_id}') from exc


def validate_pdf(path,record):
    path=Path(path)
    if path.stat().st_size!=record['bytes']:raise ValueError('downloaded byte count does not match manifest')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest!=record['sha256']:raise ValueError('downloaded SHA256 does not match manifest')
    with path.open('rb') as stream:
        if stream.read(5)!=b'%PDF-':raise ValueError('download is not a PDF')
    with fitz.open(path) as document:
        if document.page_count!=record['pages']:raise ValueError('PDF page count does not match manifest')
        text_pages=sum(bool(page.get_text('text').strip()) for page in document)
    if text_pages!=record['text_layer_pages']:raise ValueError('PDF text-layer coverage does not match manifest')
    return {'path':str(path),'sha256':digest,'bytes':path.stat().st_size,'pages':record['pages'],'text_layer_pages':text_pages}


def download(record,output_dir):
    parsed=urlparse(record['url'])
    if parsed.scheme!='https' or parsed.hostname not in ALLOWED_HOSTS:raise ValueError('source URL is outside the official allowlist')
    output_dir=Path(output_dir).resolve();output_dir.mkdir(parents=True,exist_ok=True)
    destination=(output_dir/record['filename']).resolve()
    if not destination.is_relative_to(output_dir):raise ValueError('unsafe output filename')
    if destination.exists():return validate_pdf(destination,record)
    fd,temp_name=tempfile.mkstemp(prefix=f".{record['id']}-",suffix='.part',dir=output_dir)
    os.close(fd);temporary=Path(temp_name)
    try:
        request=Request(record['url'],headers={'User-Agent':'chain-eye-source-verifier/1.0'})
        with urlopen(request,timeout=60) as response,temporary.open('wb') as target:
            final=urlparse(response.geturl())
            if final.scheme!='https' or final.hostname not in ALLOWED_HOSTS:raise ValueError('redirect left the official allowlist')
            size=0
            while chunk:=response.read(1024*1024):
                size+=len(chunk)
                if size>MAX_BYTES:raise ValueError('download exceeds 30 MiB')
                target.write(chunk)
        result=validate_pdf(temporary,record)
        os.replace(temporary,destination);result['path']=str(destination)
        return result
    finally:
        if temporary.exists():temporary.unlink()


def main():
    parser=argparse.ArgumentParser(description='Fetch one allowlisted official company report and verify its frozen metadata.')
    parser.add_argument('--report',required=True,help='Report id from data/company_sources.json')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'.runtime/company-sources')
    args=parser.parse_args()
    print(json.dumps(download(load_report(args.report),args.output_dir),ensure_ascii=False,sort_keys=True))


if __name__=='__main__':main()
