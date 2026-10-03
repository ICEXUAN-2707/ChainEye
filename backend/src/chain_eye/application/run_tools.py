"""Bounded, snapshot-scoped tools available to the R4 run orchestrator."""
import hashlib
import json
import re
import time
from datetime import datetime,timezone
from uuid import uuid4

from pydantic import BaseModel

from chain_eye.domain.contracts import Claim,ScenarioRequest

TOOL_NAMES=frozenset({
    'search_documents','get_evidence','get_facts','compute_financials',
    'compute_scenario','validate_claims',
})
MAX_EVENT_VALUE_BYTES=32768
TOOL_TIMEOUT_SECONDS=90


class ToolFailure(RuntimeError):
    pass


def _json_value(value):
    if isinstance(value,BaseModel):return value.model_dump(mode='json')
    if isinstance(value,list):return [_json_value(item) for item in value]
    if isinstance(value,dict):return {key:_json_value(item) for key,item in value.items()}
    return value


def _event_value(value):
    value=_json_value(value)
    encoded=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    digest=hashlib.sha256(encoded).hexdigest()
    if len(encoded)<=MAX_EVENT_VALUE_BYTES:return value,digest
    return {'truncated':True,'size_bytes':len(encoded)},digest


class RunTools:
    def __init__(self,repository,financial_service,scenario_service,run_id,dataset_id,dataset_version):
        self.repository=repository;self.financial_service=financial_service;self.scenario_service=scenario_service
        self.run_id=run_id;self.dataset_id=dataset_id;self.dataset_version=dataset_version

    def call(self,name,arguments):
        if name not in TOOL_NAMES:raise ToolFailure(f'tool is not allowed: {name}')
        started=datetime.now(timezone.utc).isoformat();start=time.monotonic();call_id=str(uuid4())
        input_value,input_hash=_event_value(arguments)
        record={
            'call_id':call_id,'run_id':self.run_id,'tool_name':name,'tool_version':'1',
            'input':input_value,'input_sha256':input_hash,'output':None,'output_sha256':None,
            'status':'running','error':None,'started_at':started,'ended_at':None,
        }
        try:
            output=getattr(self,f'_{name}')(**arguments)
            elapsed=time.monotonic()-start
            if elapsed>TOOL_TIMEOUT_SECONDS:raise ToolFailure('tool time budget exceeded')
            output_value,output_hash=_event_value(output)
            record.update(output=output_value,output_sha256=output_hash,status='completed',ended_at=datetime.now(timezone.utc).isoformat())
            self.repository.append_event(self.run_id,'tool_call',name,record)
            return output
        except Exception as exc:
            record.update(status='failed',error={'code':'TOOL_FAILED','message':str(exc)[:500]},ended_at=datetime.now(timezone.utc).isoformat())
            self.repository.append_event(self.run_id,'tool_call',name,record)
            raise

    def _get_facts(self,segment=None,status=None):
        facts=self.repository.facts(self.dataset_id,self.dataset_version)
        return [fact for fact in facts if (segment is None or fact.segment==segment) and (status is None or fact.status==status)]

    def _search_documents(self,query,limit=8):
        limit=max(1,min(int(limit),20));terms={term.casefold() for term in re.findall(r'[\w\u4e00-\u9fff]+',query) if len(term)>1}
        evidence=self.repository.evidence_for_snapshot(self.dataset_id,self.dataset_version)
        scored=[]
        for item in evidence:
            text=item.excerpt.casefold();score=sum(1 for term in terms if term in text)
            if score:scored.append((score,item.id,item))
        scored.sort(key=lambda row:(-row[0],row[1]))
        return [row[2] for row in scored[:limit]]

    def _get_evidence(self,evidence_ids):
        allowed={item.id:item for item in self.repository.evidence_for_snapshot(self.dataset_id,self.dataset_version)}
        missing=[item for item in evidence_ids if item not in allowed]
        if missing:raise ToolFailure('evidence reference is outside the run snapshot')
        return [allowed[item] for item in evidence_ids]

    def _compute_financials(self,facts,metric_ids):
        return self.financial_service.compute(facts,metric_ids)

    def _compute_scenario(self,request,idempotency_key):
        return self.scenario_service.execute(ScenarioRequest.model_validate(request),idempotency_key)

    def _validate_claims(self,claims,allowed_evidence_ids,allowed_calculation_ids,allowed_assumption_ids):
        evidence=set(allowed_evidence_ids);calculations=set(allowed_calculation_ids);assumptions=set(allowed_assumption_ids)
        validated=[]
        for raw in claims:
            claim=Claim.model_validate(raw)
            refs_valid=(set(claim.evidence_ids)<=evidence and set(claim.calculation_ids)<=calculations and set(claim.assumption_ids)<=assumptions)
            numeric=bool(re.search(r'(?<![A-Za-z])[-+]?\d+(?:\.\d+)?%?',claim.text))
            supported=bool(claim.evidence_ids or claim.calculation_ids)
            if not refs_valid:status='rejected'
            elif numeric and not supported:status='insufficient'
            elif claim.review_status=='rejected':status='rejected'
            elif supported:status='supported'
            else:status='insufficient'
            validated.append(claim.model_copy(update={'review_status':status}))
        return validated
