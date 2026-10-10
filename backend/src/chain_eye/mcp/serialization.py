"""Bounded JSON serialization for the external MCP boundary."""
import json
from decimal import Decimal

from pydantic import BaseModel

MAX_MCP_VALUE_BYTES=262144
SENSITIVE_KEYS=frozenset({'authorization','api_key','token','secret','password','environment','env'})


class MCPSerializationError(ValueError):
    pass


def json_value(value):
    if isinstance(value,BaseModel):return json_value(value.model_dump(mode='json'))
    if isinstance(value,Decimal):return str(value)
    if isinstance(value,list):return [json_value(item) for item in value]
    if isinstance(value,tuple):return [json_value(item) for item in value]
    if isinstance(value,dict):
        return {
            str(key):json_value(item)
            for key,item in value.items()
            if str(key).casefold() not in SENSITIVE_KEYS
        }
    if value is None or isinstance(value,(str,int,bool,float)):return value
    raise MCPSerializationError(f'unsupported MCP value type: {type(value).__name__}')


def bounded_value(value):
    normalized=json_value(value)
    encoded=json.dumps(normalized,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    if len(encoded)>MAX_MCP_VALUE_BYTES:raise MCPSerializationError('MCP result exceeds the bounded response size')
    return normalized


def bounded_json(value):
    normalized=bounded_value(value)
    return json.dumps(normalized,ensure_ascii=False,sort_keys=True,separators=(',',':'))
