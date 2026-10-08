"""Compatibility facade over the single runtime ToolRegistry."""
import time

from chain_eye.tools.registry import (
    DEFAULT_TOOL_REGISTRY,MAX_EVENT_VALUE_BYTES,TOOL_NAMES,TOOL_TIMEOUT_SECONDS,
    ToolRegistry,_event_value,
)
from chain_eye.tools.spec import ToolContext,ToolFailure


class RunTools:
    def __init__(
        self,repository,financial_service,scenario_service,run_id,dataset_id,dataset_version,
        clock=time.monotonic,registry:ToolRegistry|None=None,skill=None,
    ):
        self.repository=repository;self.financial_service=financial_service;self.scenario_service=scenario_service
        self.run_id=run_id;self.dataset_id=dataset_id;self.dataset_version=dataset_version;self.clock=clock
        self.registry=registry or DEFAULT_TOOL_REGISTRY;self.skill=skill

    def for_skill(self,skill):
        return RunTools(
            self.repository,self.financial_service,self.scenario_service,self.run_id,
            self.dataset_id,self.dataset_version,self.clock,self.registry,skill,
        )

    def call(self,name,arguments):
        context=ToolContext(
            repository=self.repository,financial_service=self.financial_service,
            scenario_service=self.scenario_service,run_id=self.run_id,
            dataset_id=self.dataset_id,dataset_version=self.dataset_version,clock=self.clock,
            skill_id=getattr(self.skill,'id',None),skill_version=getattr(self.skill,'version',None),
        )
        allowed=getattr(self.skill,'allowed_tools',None)
        return self.registry.call(name,arguments,context,'agent',allowed)


__all__=[
    'MAX_EVENT_VALUE_BYTES','RunTools','TOOL_NAMES','TOOL_TIMEOUT_SECONDS',
    'ToolFailure','_event_value',
]
