"""Typed metadata and execution context shared by all agent tools."""
from dataclasses import dataclass,replace
from typing import Callable,FrozenSet,Literal

ToolCaller=Literal['agent','mcp']
ToolHandler=Callable[...,object]


class ToolFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class ToolSpec:
    name:str
    version:str
    description:str
    allowed_callers:FrozenSet[ToolCaller]
    timeout_seconds:int
    side_effect:Literal['read','deterministic_write']
    handler:ToolHandler


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
    deadline:float|None=None

    def with_deadline(self,deadline:float):
        return replace(self,deadline=deadline)

    def with_skill(self,skill_id:str|None,skill_version:str|None):
        return replace(self,skill_id=skill_id,skill_version=skill_version)

    def check_snapshot(self,dataset_id,dataset_version):
        if dataset_id!=self.dataset_id or dataset_version!=self.dataset_version:
            raise ToolFailure('tool request is outside the run snapshot')

    def check_budget(self):
        if self.deadline is not None and self.clock()>self.deadline:
            raise ToolFailure('tool time budget exceeded')
