"""DeepSeek adapter. Provider details do not cross into domain/application code."""
import json
import os
import time

import httpx2 as httpx

from chain_eye.ports.services import (
    LLMResponse,ModelInvalidResponse,ModelRateLimited,ModelUnavailable,
    TypedProviderError,
)

ModelFailure=TypedProviderError


class DeepSeekAdapter:
    provider='deepseek'
    endpoint='https://api.deepseek.com/chat/completions'

    def __init__(self,api_key=None,model=None,timeout_seconds=60):
        self._api_key=api_key if api_key is not None else os.getenv('DEEPSEEK_API_KEY')
        self.model=model or os.getenv('DEEPSEEK_MODEL') or 'deepseek-flash'
        self.timeout_seconds=timeout_seconds

    @property
    def public_config(self):
        return {'provider':self.provider,'model':self.model,'response_format':'json_object','timeout_seconds':self.timeout_seconds}

    def generate(self,task_name,prompt_version,messages,response_schema,budget):
        if not self._api_key:raise ModelUnavailable('DEEPSEEK_API_KEY is not configured')
        if task_name!='claims':raise ModelInvalidResponse(f'unsupported task: {task_name}')
        timeout=min(float(budget.get('timeout_seconds',self.timeout_seconds)),self.timeout_seconds)
        schema_message={
            'role':'system',
            'content':f'Your response must satisfy this JSON Schema: {json.dumps(response_schema,separators=(",",":"))}',
        }
        request_messages=[messages[0],schema_message,*messages[1:]] if messages and messages[0].get('role')=='system' else [schema_message,*messages]
        payload={
            'model':self.model,'messages':request_messages,
            'response_format':{'type':'json_object'},'temperature':0,
        }
        if budget.get('max_output_tokens') is not None:payload['max_tokens']=int(budget['max_output_tokens'])
        started=time.monotonic()
        try:
            response=httpx.post(
                self.endpoint,headers={'Authorization':f'Bearer {self._api_key}','Content-Type':'application/json'},
                json=payload,timeout=timeout,
            )
        except Exception as exc:
            raise ModelUnavailable('DeepSeek request failed') from exc
        latency_ms=max(0,round((time.monotonic()-started)*1000))
        if response.status_code==429:raise ModelRateLimited('DeepSeek rate limit reached')
        if response.status_code>=500:raise ModelUnavailable('DeepSeek service unavailable')
        if response.status_code>=400:raise ModelFailure(f'DeepSeek rejected request ({response.status_code})')
        try:
            envelope=response.json();content=envelope['choices'][0]['message']['content'];parsed=json.loads(content)
            if not isinstance(parsed,dict):raise TypeError('response is not an object')
            claims=parsed.get('claims')
            if not isinstance(claims,list) or not claims:raise TypeError('claims is empty or not a list')
            usage=envelope.get('usage') or {}
        except (ValueError,KeyError,IndexError,TypeError) as exc:
            raise ModelInvalidResponse('DeepSeek returned invalid claim JSON') from exc
        return LLMResponse(
            output=parsed,provider=self.provider,model=envelope.get('model',self.model),usage=usage,
            latency_ms=latency_ms,request_id=envelope.get('id'),cost=envelope.get('cost'),
        )
