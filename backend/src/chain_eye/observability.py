"""Bounded, redacted JSONL events for local reproduction and diagnostics."""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel


MAX_LOG_LINE_BYTES=65536
MAX_STRING_LENGTH=2000
MAX_COLLECTION_ITEMS=100
MAX_DEPTH=6
REQUIRED_CONTEXT_FIELDS=(
    'request_id','run_id','node','skill_id','tool_call_id','prompt_version',
    'model','duration_ms','status','error_code',
)
SENSITIVE_KEYS=frozenset({
    'authorization','proxy_authorization','api_key','token','access_token','refresh_token','id_token',
    'secret','client_secret','password','passwd','cookie','set_cookie','credentials',
    'environment','env','header','headers','request_headers','response_headers',
})
SENSITIVE_SUFFIXES=('_api_key','_token','_secret','_password','_passwd','_cookie','_headers')
BEARER_PATTERN=re.compile(r'(?i)\bbearer\s+[a-z0-9._~+/=-]+')
SECRET_PATTERN=re.compile(r'(?i)\bsk-[a-z0-9_-]{6,}\b')
ASSIGNMENT_PATTERN=re.compile(
    r'(?i)\b(api[_-]?key|token|secret|password|authorization)\s*([:=])\s*([^\s,;]+)'
)


def _normalized_key(value):
    return re.sub(r'[^a-z0-9]+','_',str(value).casefold()).strip('_')


def _sensitive_key(value):
    normalized=_normalized_key(value)
    return normalized in SENSITIVE_KEYS or normalized.endswith(SENSITIVE_SUFFIXES)


def redact_text(value):
    value=BEARER_PATTERN.sub('Bearer [REDACTED]',value)
    value=SECRET_PATTERN.sub('[REDACTED]',value)
    return ASSIGNMENT_PATTERN.sub(lambda match:f'{match.group(1)}{match.group(2)}[REDACTED]',value)


def safe_value(value,*,key=None,depth=0):
    """Return a JSON value without secrets, unbounded text, or unsafe repr output."""
    if key is not None and _sensitive_key(key):return '[REDACTED]'
    if depth>MAX_DEPTH:return {'truncated':True,'reason':'max_depth'}
    if isinstance(value,BaseModel):value=value.model_dump(mode='json')
    if value is None or isinstance(value,(bool,int)):return value
    if isinstance(value,float):return value if math.isfinite(value) else '[NON_FINITE]'
    if isinstance(value,Decimal):return str(value)
    if isinstance(value,Path):return str(value)
    if isinstance(value,str):
        redacted=redact_text(value)
        if len(redacted)<=MAX_STRING_LENGTH:return redacted
        return redacted[:MAX_STRING_LENGTH]+'…[TRUNCATED]'
    if isinstance(value,(bytes,bytearray,memoryview)):
        raw=bytes(value)
        return {'omitted_binary':True,'size_bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    if isinstance(value,dict):
        items=list(value.items());result={}
        for item_key,item in items[:MAX_COLLECTION_ITEMS]:
            text_key=str(item_key)[:128]
            result[text_key]=safe_value(item,key=text_key,depth=depth+1)
        if len(items)>MAX_COLLECTION_ITEMS:result['_truncated_items']=len(items)-MAX_COLLECTION_ITEMS
        return result
    if isinstance(value,(list,tuple,set,frozenset)):
        items=list(value)
        result=[safe_value(item,depth=depth+1) for item in items[:MAX_COLLECTION_ITEMS]]
        if len(items)>MAX_COLLECTION_ITEMS:
            result.append({'truncated_items':len(items)-MAX_COLLECTION_ITEMS})
        return result
    return {'omitted_type':type(value).__name__}


class NullJsonlLogger:
    path=None

    def emit(self,event,level='INFO',**fields):
        return None


class JsonlLogger:
    """Append one safe UTF-8 JSON object per line."""

    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self._lock=threading.Lock()

    def _record(self,event,level,fields):
        record={
            'timestamp':datetime.now(timezone.utc).isoformat(),
            'level':str(level).upper()[:16],
            'event':safe_value(str(event)),
        }
        for name in REQUIRED_CONTEXT_FIELDS:
            record[name]=safe_value(fields.pop(name,None),key=name)
        for name,value in fields.items():
            key=str(name)[:128]
            if key not in record:record[key]=safe_value(value,key=key)
        encoded=json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
        if len(encoded)>MAX_LOG_LINE_BYTES:
            digest=hashlib.sha256(encoded).hexdigest();size=len(encoded)
            record={key:record[key] for key in ('timestamp','level','event',*REQUIRED_CONTEXT_FIELDS)}
            record['details']={'truncated':True,'size_bytes':size,'sha256':digest}
            encoded=json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
        return encoded

    def emit(self,event,level='INFO',**fields):
        encoded=self._record(event,level,dict(fields))
        with self._lock,self.path.open('ab') as target:
            target.write(encoded+b'\n');target.flush()
        return json.loads(encoded)
