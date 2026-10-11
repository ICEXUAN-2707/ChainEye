"""Deterministic graph dispatcher with graph-aware node audit events."""
from dataclasses import dataclass,field
from typing import Any,Callable

from chain_eye.agents.spec import GraphSpec
from chain_eye.agents.state import AgentState


@dataclass(frozen=True)
class NodeResult:
    """A handler's transition decision and public completion details."""

    condition:str|None=None
    terminal:bool=False
    status:str='completed'
    details:dict[str,Any]=field(default_factory=dict)


class AgentOrchestrator:
    def __init__(self,graph:GraphSpec,repository,clock):
        self.graph=graph;self.repository=repository;self.clock=clock

    def _payload(self,node,status,duration_ms=0,error_code=None,details=None):
        return {
            **(details or {}),
            'graph_id':self.graph.id,'graph_version':self.graph.version,
            'graph_spec_sha256':self.graph.spec_sha256,
            'node_id':node.id,'node_version':node.version,
            'node_spec_sha256':node.spec_sha256,'status':status,
            'duration_ms':duration_ms,'error_code':error_code,
        }

    def execute(self,state:AgentState,handlers:dict[str,Callable[[AgentState],NodeResult]]):
        current=self.graph.initial_node
        while current is not None:
            node=self.graph.require_node(current)
            try:handler=handlers[current]
            except KeyError as exc:raise RuntimeError(f'missing graph node handler: {current}') from exc
            state.update_record(self.repository.update_run(state.run_id,current_node=current))
            entered=self.clock()
            self.repository.append_event(state.run_id,'node_status',current,self._payload(node,'started'))
            try:
                result=handler(state)
                if not isinstance(result,NodeResult):
                    raise TypeError(f'graph node returned an invalid result: {current}')
            except Exception as exc:
                elapsed=max(0,int((self.clock()-entered)*1000))
                self.repository.append_event(
                    state.run_id,'node_status',current,
                    self._payload(node,'failed',elapsed,getattr(exc,'code',exc.__class__.__name__)),
                )
                raise
            elapsed=max(0,int((self.clock()-entered)*1000))
            self.repository.append_event(
                state.run_id,'node_status',current,
                self._payload(node,result.status,elapsed,details=result.details),
            )
            if result.terminal:return result
            matches=[
                edge for edge in self.graph.transitions
                if edge.source==current and edge.condition==result.condition
            ]
            if len(matches)!=1:
                raise RuntimeError(
                    f'graph transition must resolve exactly once: {current} / {result.condition}'
                )
            current=matches[0].target
        return NodeResult(terminal=True)
