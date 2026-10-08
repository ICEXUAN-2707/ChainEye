"""Typed metadata and execution context shared by all agent tools."""
import hashlib
import inspect
import json
from dataclasses import dataclass,replace
from typing import Callable,FrozenSet,Literal

ToolCaller=Literal['agent','mcp']
ToolHandler=Callable[...,object]


class ToolFailure(RuntimeError):
    pass


def _implementation_source(value):
    try:
        source=inspect.getsource(value)
    except (OSError,TypeError) as exc:
        name=getattr(value,'__qualname__',getattr(value,'__name__',type(value).__name__))
        raise ValueError(f'tool implementation source is unavailable: {name}') from exc
    return {
        'identity':f"{getattr(value,'__module__','')}:{getattr(value,'__qualname__',getattr(value,'__name__',''))}",
        'source':source.replace('\r\n','\n'),
    }


@dataclass(frozen=True)
class ToolSpec:
    name:str
    version:str
    description:str
    allowed_callers:FrozenSet[ToolCaller]
    timeout_seconds:int
    side_effect:Literal['read','deterministic_write']
    handler:ToolHandler
    implementation_id:str=''
    implementation_dependencies:tuple[object,...]=()

    @property
    def implementation_sha256(self):
        canonical=json.dumps(
            [_implementation_source(self.handler),*(_implementation_source(item) for item in self.implementation_dependencies)],
            ensure_ascii=False,sort_keys=True,separators=(',',':'),
        )
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

    @property
    def spec_sha256(self):
        canonical=json.dumps({
            'name':self.name,'version':self.version,'description':self.description,
            'allowed_callers':sorted(self.allowed_callers),'timeout_seconds':self.timeout_seconds,
            'side_effect':self.side_effect,'implementation_id':self.implementation_id,
            'implementation_sha256':self.implementation_sha256,
        },ensure_ascii=False,sort_keys=True,separators=(',',':'))
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class ToolContext:
    repository:object
    financial_service:object
    scenario_service:object
    run_id:str
    dataset_id:str
    dataset_version:int
    clock:Callable[[],float]
    skill_id:str|None=None
    skill_version:str|None=None
    skill_spec_sha256:str|None=None
    deadline:float|None=None

    def with_deadline(self,deadline:float):
        return replace(self,deadline=min(self.deadline,deadline) if self.deadline is not None else deadline)

    def with_skill(self,skill_id:str|None,skill_version:str|None):
        return replace(self,skill_id=skill_id,skill_version=skill_version)

    def check_snapshot(self,dataset_id,dataset_version):
        if dataset_id!=self.dataset_id or dataset_version!=self.dataset_version:
            raise ToolFailure('tool request is outside the run snapshot')

    def check_budget(self):
        if self.deadline is not None and self.clock()>self.deadline:
            raise ToolFailure('tool time budget exceeded')
