"""Single runtime registry and audit boundary for every agent tool."""
import hashlib
import json
from datetime import datetime,timezone
from uuid import uuid4

from pydantic import BaseModel

from chain_eye.application import financials as financials_module
from chain_eye.application import scenarios as scenarios_module
from chain_eye.domain import financials as financial_rules_module
from chain_eye.domain import scenario as scenario_rules_module
from chain_eye.tools.handlers import claims as claims_module
from chain_eye.tools.handlers import evidence as evidence_module
from chain_eye.tools.handlers import financials as financial_handler_module
from chain_eye.tools.handlers import scenario as scenario_handler_module
from chain_eye.tools.handlers.claims import validate_claims
from chain_eye.tools.handlers.evidence import get_evidence,get_facts,search_documents
from chain_eye.tools.handlers.financials import compute_financials
from chain_eye.tools.handlers.scenario import compute_scenario
from chain_eye.tools.spec import ToolContext,ToolFailure,ToolSpec

MAX_EVENT_VALUE_BYTES=32768
TOOL_TIMEOUT_SECONDS=90


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


class ToolRegistry:
    def __init__(self,specs,active_versions=None):
        self._specs={};versions_by_name={}
        for spec in specs:
            identity=(spec.name,spec.version)
            if identity in self._specs:raise ValueError(f'duplicate tool: {spec.name}@{spec.version}')
            if (
                not spec.name or not spec.version or not spec.description
                or not spec.allowed_callers or not spec.allowed_callers<=frozenset({'agent','mcp'})
                or not isinstance(spec.timeout_seconds,int) or isinstance(spec.timeout_seconds,bool)
                or spec.timeout_seconds<=0 or spec.side_effect not in {'read','deterministic_write'}
                or not callable(spec.handler) or not spec.implementation_id
            ):raise ValueError(f'invalid tool specification: {spec.name or "<unnamed>"}')
            try:spec.implementation_sha256
            except ValueError as exc:raise ValueError(f'invalid tool implementation: {spec.name}') from exc
            self._specs[identity]=spec;versions_by_name.setdefault(spec.name,set()).add(spec.version)
        if not self._specs:raise ValueError('tool registry is empty')
        if active_versions is None:
            ambiguous=[name for name,versions in versions_by_name.items() if len(versions)!=1]
            if ambiguous:raise ValueError(f'active tool version is required: {ambiguous[0]}')
            active_versions={name:next(iter(versions)) for name,versions in versions_by_name.items()}
        if set(active_versions)!=set(versions_by_name):raise ValueError('active tool versions do not match registry names')
        for name,version in active_versions.items():
            if (name,version) not in self._specs:raise ValueError(f'unknown active tool: {name}@{version}')
        self._active_versions=dict(active_versions)

    @property
    def names(self):return frozenset(self._active_versions)

    @property
    def active_versions(self):return dict(self._active_versions)

    def require(self,name,version=None):
        selected=version if version is not None else self._active_versions.get(name)
        spec=self._specs.get((name,selected))
        if spec is None:raise ToolFailure(f'tool is not allowed: {name}@{selected or "*"}')
        return spec

    def resolve(self,name,version,spec_sha256,implementation_id=None,implementation_sha256=None):
        spec=self.require(name,version)
        if spec.spec_sha256!=spec_sha256:raise ToolFailure(f'tool hash mismatch: {name}@{version}')
        if implementation_id is not None and spec.implementation_id!=implementation_id:
            raise ToolFailure(f'tool implementation id mismatch: {name}@{version}')
        if implementation_sha256 is not None and spec.implementation_sha256!=implementation_sha256:
            raise ToolFailure(f'tool implementation hash mismatch: {name}@{version}')
        return spec

    def call(self,name,arguments,context:ToolContext,caller='agent',allowed_tools=None,version=None,spec_sha256=None):
        spec=self.require(name,version)
        if spec_sha256 is not None and spec.spec_sha256!=spec_sha256:
            raise ToolFailure(f'tool hash mismatch: {name}@{spec.version}')
        if caller not in spec.allowed_callers:raise ToolFailure(f'tool is not allowed for caller: {caller}')
        if allowed_tools is not None and name not in allowed_tools:
            raise ToolFailure(f'tool is not allowed by skill: {name}')
        started=datetime.now(timezone.utc).isoformat();start=context.clock();call_id=str(uuid4())
        input_value,input_hash=_event_value(arguments)
        record={
            'call_id':call_id,'run_id':context.run_id,'tool_name':name,'tool_version':spec.version,
            'tool_spec_sha256':spec.spec_sha256,'tool_implementation_id':spec.implementation_id,
            'tool_implementation_sha256':spec.implementation_sha256,'skill_id':context.skill_id,
            'skill_version':context.skill_version,'skill_spec_sha256':context.skill_spec_sha256,
            'input':input_value,'input_sha256':input_hash,'output':None,'output_sha256':None,
            'status':'running','error':None,'started_at':started,'ended_at':None,
        }
        try:
            active=context.with_deadline(start+spec.timeout_seconds);active.check_budget()
            output=spec.handler(active,**arguments);active.check_budget()
            output_value,output_hash=_event_value(output)
            record.update(output=output_value,output_sha256=output_hash,status='completed',ended_at=datetime.now(timezone.utc).isoformat())
            context.repository.append_event(context.run_id,'tool_call',name,record)
            return output
        except Exception as exc:
            record.update(status='failed',error={'code':'TOOL_FAILED','message':str(exc)[:500]},ended_at=datetime.now(timezone.utc).isoformat())
            context.repository.append_event(context.run_id,'tool_call',name,record)
            raise


DEFAULT_TOOL_REGISTRY=ToolRegistry([
    ToolSpec('search_documents','1','Search evidence in the bound dataset snapshot.',frozenset({'agent','mcp'}),TOOL_TIMEOUT_SECONDS,'read',search_documents,'chain-eye.search-documents.v1',(evidence_module,)),
    ToolSpec('get_evidence','1','Read evidence by ID from the bound dataset snapshot.',frozenset({'agent','mcp'}),TOOL_TIMEOUT_SECONDS,'read',get_evidence,'chain-eye.get-evidence.v1',(evidence_module,)),
    ToolSpec('get_facts','1','Read facts from the bound dataset snapshot.',frozenset({'agent','mcp'}),TOOL_TIMEOUT_SECONDS,'read',get_facts,'chain-eye.get-facts.v1',(evidence_module,)),
    ToolSpec('compute_financials','1','Run deterministic financial calculations.',frozenset({'agent'}),TOOL_TIMEOUT_SECONDS,'deterministic_write',compute_financials,'chain-eye.compute-financials.v1',(financial_handler_module,financials_module,financial_rules_module)),
    ToolSpec('compute_scenario','1','Run the deterministic scenario model.',frozenset({'agent'}),TOOL_TIMEOUT_SECONDS,'deterministic_write',compute_scenario,'chain-eye.compute-scenario.v1',(scenario_handler_module,scenarios_module,scenario_rules_module)),
    ToolSpec('validate_claims','1','Validate claim references and support status.',frozenset({'agent'}),TOOL_TIMEOUT_SECONDS,'read',validate_claims,'chain-eye.validate-claims.v1',(claims_module,)),
])
TOOL_NAMES=DEFAULT_TOOL_REGISTRY.names
