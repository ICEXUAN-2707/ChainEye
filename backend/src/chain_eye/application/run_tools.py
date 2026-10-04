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
    def __init__(self,repository,financial_service,scenario_service,run_id,dataset_id,dataset_version,clock=time.monotonic):
        self.repository=repository;self.financial_service=financial_service;self.scenario_service=scenario_service
        self.run_id=run_id;self.dataset_id=dataset_id;self.dataset_version=dataset_version;self.clock=clock
        self._deadline=None

    def _check_snapshot(self,dataset_id,dataset_version):
        if dataset_id!=self.dataset_id or dataset_version!=self.dataset_version:
            raise ToolFailure('tool request is outside the run snapshot')

    def _check_budget(self):
        if self._deadline is not None and self.clock()>self._deadline:
            raise ToolFailure('tool time budget exceeded')

    def call(self,name,arguments):
        if name not in TOOL_NAMES:raise ToolFailure(f'tool is not allowed: {name}')
        started=datetime.now(timezone.utc).isoformat();start=self.clock();call_id=str(uuid4())
        input_value,input_hash=_event_value(arguments)
        record={
            'call_id':call_id,'run_id':self.run_id,'tool_name':name,'tool_version':'1',
            'input':input_value,'input_sha256':input_hash,'output':None,'output_sha256':None,
            'status':'running','error':None,'started_at':started,'ended_at':None,
        }
        try:
            self._deadline=start+TOOL_TIMEOUT_SECONDS
            self._check_budget()
            output=getattr(self,f'_{name}')(**arguments)
            self._check_budget()
            output_value,output_hash=_event_value(output)
            record.update(output=output_value,output_sha256=output_hash,status='completed',ended_at=datetime.now(timezone.utc).isoformat())
            self.repository.append_event(self.run_id,'tool_call',name,record)
            return output
        except Exception as exc:
            record.update(status='failed',error={'code':'TOOL_FAILED','message':str(exc)[:500]},ended_at=datetime.now(timezone.utc).isoformat())
            self.repository.append_event(self.run_id,'tool_call',name,record)
            raise
        finally:
            self._deadline=None

    def _get_facts(self,dataset_id,dataset_version,metric_ids=None,segment=None,period=None):
        self._check_snapshot(dataset_id,dataset_version);self._check_budget()
        metrics=set(metric_ids or [])
        facts=self.repository.facts(self.dataset_id,self.dataset_version);self._check_budget()
        return [
            fact for fact in facts
            if (not metrics or fact.metric in metrics)
            and (segment is None or fact.segment==segment)
            and (period is None or fact.period_end==period or fact.period_end.startswith(f'{period}-'))
        ]

    @staticmethod
    def _search_terms(query):
        terms=set()
        for token in re.findall(r'[A-Za-z0-9_]+|[\u4e00-\u9fff]+',query.casefold()):
            if re.fullmatch(r'[\u4e00-\u9fff]+',token):
                if len(token)==1:terms.add(token)
                else:terms.update(token[index:index+2] for index in range(len(token)-1))
            elif len(token)>1:terms.add(token)
        return terms

    def _search_documents(self,dataset_id,dataset_version,query,filters=None,top_k=8):
        self._check_snapshot(dataset_id,dataset_version)
        if not isinstance(top_k,int) or isinstance(top_k,bool) or not 1<=top_k<=8:
            raise ToolFailure('top_k must be an integer from 1 to 8')
        filters=filters or {};unknown=set(filters)-{'source_ids','locator_kind','pdf_page'}
        if unknown:raise ToolFailure(f'unsupported search filter: {sorted(unknown)[0]}')
        terms=self._search_terms(query)
        evidence=self.repository.evidence_for_snapshot(self.dataset_id,self.dataset_version)
        scored=[]
        for item in evidence:
            self._check_budget()
            if filters.get('source_ids') and item.source_id not in filters['source_ids']:continue
            if filters.get('locator_kind') and item.locator_kind!=filters['locator_kind']:continue
            if filters.get('pdf_page') and item.pdf_page!=filters['pdf_page']:continue
            text=item.excerpt.casefold();score=sum(1 for term in terms if term in text)
            if score:scored.append((score,item.id,item))
        scored.sort(key=lambda row:(-row[0],row[1]))
        return [row[2] for row in scored[:top_k]]

    def _get_evidence(self,evidence_ids):
        self._check_budget()
        allowed={item.id:item for item in self.repository.evidence_for_snapshot(self.dataset_id,self.dataset_version)}
        self._check_budget()
        missing=[item for item in evidence_ids if item not in allowed]
        if missing:raise ToolFailure('evidence reference is outside the run snapshot')
        return [allowed[item] for item in evidence_ids]

    def _compute_financials(self,fact_ids,revisions,metric_ids):
        if set(fact_ids)!=set(revisions):raise ToolFailure('fact revisions must match fact IDs')
        by_id={fact.id:fact for fact in self.repository.facts(self.dataset_id,self.dataset_version)}
        facts=[]
        for fact_id in fact_ids:
            fact=by_id.get(fact_id)
            if fact is None or fact.revision!=revisions[fact_id]:
                raise ToolFailure('fact revision is outside the run snapshot')
            facts.append(fact)
        self._check_budget()
        return self.financial_service.compute(facts,metric_ids)

    def _compute_scenario(self,request):
        parsed=ScenarioRequest.model_validate(request)
        self._check_snapshot(parsed.dataset_id,parsed.dataset_version);self._check_budget()
        return self.scenario_service.execute(parsed,f'run-{self.run_id}')

    def _validate_claims(self,claims,allowed_evidence_ids,allowed_calculation_ids,allowed_assumption_ids):
        evidence=set(allowed_evidence_ids);calculations=set(allowed_calculation_ids);assumptions=set(allowed_assumption_ids)
        validated=[]
        for raw in claims:
            self._check_budget()
            claim=Claim.model_validate(raw)
            refs_valid=(
                set(claim.evidence_ids)<=evidence
                and set(claim.counter_evidence_ids)<=evidence
                and set(claim.calculation_ids)<=calculations
                and set(claim.assumption_ids)<=assumptions
            )
            numeric=bool(re.search(r'(?<![A-Za-z])[-+]?\d+(?:\.\d+)?%?',claim.text))
            supported=bool(claim.evidence_ids or claim.calculation_ids)
            if not refs_valid:status='rejected'
            elif numeric and not supported:status='insufficient'
            elif claim.review_status=='rejected':status='rejected'
            elif supported:status='pending'
            else:status='insufficient'
            validated.append(claim.model_copy(update={'review_status':status}))
        return validated
