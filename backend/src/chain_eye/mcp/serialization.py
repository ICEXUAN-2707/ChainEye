"""Bounded JSON serialization for the external MCP boundary."""
import json
import re
from decimal import Decimal

from pydantic import BaseModel

MAX_MCP_VALUE_BYTES=262144
SENSITIVE_KEYS=frozenset({
    'authorization','proxy_authorization','api_key','token','access_token','refresh_token','id_token',
    'secret','client_secret','password','passwd','cookie','set_cookie','credentials',
    'environment','env','header','headers','request_headers','response_headers',
})
SENSITIVE_SUFFIXES=('_api_key','_token','_secret','_password','_passwd','_cookie','_headers')
BEARER_PATTERN=re.compile(r'(?i)\bbearer\s+[a-z0-9._~+/=-]+')
SECRET_PATTERN=re.compile(r'(?i)\bsk-[a-z0-9_-]{6,}\b')


class MCPSerializationError(ValueError):
    pass


def _normalized_key(value):
    return re.sub(r'[^a-z0-9]+','_',str(value).casefold()).strip('_')


def _sensitive_key(value):
    normalized=_normalized_key(value)
    return normalized in SENSITIVE_KEYS or normalized.endswith(SENSITIVE_SUFFIXES)


def _redact_text(value):
    return SECRET_PATTERN.sub('[REDACTED]',BEARER_PATTERN.sub('Bearer [REDACTED]',value))


def json_value(value):
    if isinstance(value,BaseModel):return json_value(value.model_dump(mode='json'))
    if isinstance(value,Decimal):return str(value)
    if isinstance(value,list):return [json_value(item) for item in value]
    if isinstance(value,tuple):return [json_value(item) for item in value]
    if isinstance(value,dict):
        return {
            str(key):json_value(item)
            for key,item in value.items()
            if not _sensitive_key(key)
        }
    if isinstance(value,str):return _redact_text(value)
    if value is None or isinstance(value,(int,bool,float)):return value
    raise MCPSerializationError(f'unsupported MCP value type: {type(value).__name__}')


def bounded_value(value):
    normalized=json_value(value)
    encoded=json.dumps(normalized,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    if len(encoded)>MAX_MCP_VALUE_BYTES:raise MCPSerializationError('MCP result exceeds the bounded response size')
    return normalized


def bounded_json(value):
    normalized=bounded_value(value)
    return json.dumps(normalized,ensure_ascii=False,sort_keys=True,separators=(',',':'))
