import hashlib
import os
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import fitz

from chain_eye.application.errors import AppError
from chain_eye.domain.datasets import DatasetSourceLimitError,Source

MAX_PDF_BYTES=30*1024*1024
MAX_PDF_PAGES=500
MAX_DATASET_SOURCES=5

def sha256_file(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()

def safe_filename(value):
    name=(value or '').replace('\\','/').split('/')[-1].strip()
    if not name or name in ('.','..') or any(ord(character)<32 for character in name) or len(name)>255:
        raise AppError('INVALID_INPUT','PDF文件名无效',422,details={'reason':'INVALID_FILENAME'})
    return name

class SourceUploadService:
    def __init__(self,repository):self.repository=repository

    def execute(self,dataset_id,staged_path,filename,content_type=None,url=None,published_date=None):
        staged_path=Path(staged_path);filename=safe_filename(filename)
        _=content_type  # The declared MIME type is untrusted; validation uses the bytes and PDF parser.
        if not self.repository.get_dataset(dataset_id):raise AppError('NOT_FOUND','数据包或版本不存在',404)
        if staged_path.stat().st_size>MAX_PDF_BYTES:
            raise AppError('INVALID_INPUT','PDF不能超过30 MiB',422,details={'reason':'FILE_TOO_LARGE','max_bytes':MAX_PDF_BYTES})
        with staged_path.open('rb') as stream:signature=stream.read(5)
        if staged_path.stat().st_size<5 or signature!=b'%PDF-':
            raise AppError('INVALID_INPUT','文件不是有效PDF',422,details={'reason':'INVALID_PDF_SIGNATURE'})
        if published_date is not None:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',published_date):raise AppError('INVALID_INPUT','发布日期必须是有效ISO日期',422,details={'reason':'INVALID_PUBLISHED_DATE'})
            try:date.fromisoformat(published_date)
            except ValueError:raise AppError('INVALID_INPUT','发布日期必须是有效ISO日期',422,details={'reason':'INVALID_PUBLISHED_DATE'}) from None
        if url is not None:
            parsed=urlparse(url)
            if parsed.scheme not in ('http','https') or not parsed.netloc:raise AppError('INVALID_INPUT','来源URL必须是HTTP或HTTPS地址',422,details={'reason':'INVALID_SOURCE_URL'})
        try:
            with fitz.open(staged_path) as document:
                if not document.is_pdf:raise ValueError('not pdf')
                if document.needs_pass or document.is_encrypted:
                    raise AppError('INVALID_INPUT','不支持加密PDF',422,details={'reason':'PDF_ENCRYPTED'})
                page_count=document.page_count
                if page_count<1:raise AppError('INVALID_INPUT','PDF没有页面',422,details={'reason':'EMPTY_PDF'})
                if page_count>MAX_PDF_PAGES:
                    raise AppError('INVALID_INPUT','PDF不能超过500页',422,details={'reason':'TOO_MANY_PAGES','max_pages':MAX_PDF_PAGES})
                has_text=any(page.get_text('text').strip() for page in document)
        except AppError:raise
        except Exception:
            raise AppError('INVALID_INPUT','PDF结构损坏或无法读取',422,details={'reason':'INVALID_PDF'}) from None
        sha256=sha256_file(staged_path)
        existing=self.repository.get_source_by_sha256(sha256)
        destination=None
        if existing:
            proposed=existing;content_path=None
        else:
            destination=(self.repository.upload_root/f'{sha256}.pdf').resolve()
            if not destination.is_relative_to(self.repository.upload_root.resolve()):raise RuntimeError('unsafe upload destination')
            if destination.exists():
                if sha256_file(destination)!=sha256:raise AppError('SOURCE_HASH_MISMATCH','内容寻址文件哈希冲突',409)
                staged_path.unlink()
            else:
                os.replace(staged_path,destination)
            proposed=Source(id=str(uuid4()),filename=filename,sha256=sha256,media_type='application/pdf',page_count=page_count,url=url,published_date=published_date,parse_status='queued' if has_text else 'needs_review',data_basis='user_uploaded')
            content_path=f'upload:{sha256}.pdf'
        try:attachment=self.repository.attach_source(dataset_id,proposed,content_path,MAX_DATASET_SOURCES)
        except DatasetSourceLimitError:
            if destination is not None and not self.repository.get_source_by_sha256(sha256) and destination.exists():destination.unlink()
            raise AppError('INVALID_INPUT','每个数据包最多关联5个文件',422,details={'reason':'SOURCE_LIMIT','max_sources':MAX_DATASET_SOURCES}) from None
        except Exception:
            if destination is not None and not self.repository.get_source_by_sha256(sha256) and destination.exists():destination.unlink()
            raise
        if attachment is None:raise AppError('NOT_FOUND','数据包或版本不存在',404)
        return attachment
