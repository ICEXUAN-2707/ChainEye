"""Serializable graph, node and transition specifications."""
import hashlib
import json
from dataclasses import dataclass
from typing import Literal

Recoverability=Literal['safe','conditional','unsafe']


def _sha256(value):
    canonical=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class NodeSpec:
    id:str
    version:str
    description:str
    input_fields:tuple[str,...]
    output_fields:tuple[str,...]
    skill_id:str|None
    allowed_tools:tuple[str,...]
    timeout_seconds:int
    max_retries:int
    recoverability:Recoverability
    terminal_states:tuple[str,...]
    event_fields:tuple[str,...]

    def __post_init__(self):
        if not self.id or not self.version or not self.description:
            raise ValueError('node identity and description are required')
        if self.timeout_seconds<=0 or self.max_retries<0:
            raise ValueError(f'invalid node budget: {self.id}')
        if self.recoverability not in {'safe','conditional','unsafe'}:
            raise ValueError(f'invalid node recoverability: {self.id}')
        if len(set(self.allowed_tools))!=len(self.allowed_tools):
            raise ValueError(f'duplicate allowed tool: {self.id}')

    def to_dict(self):
        return {
            'id':self.id,'version':self.version,'description':self.description,
            'input_fields':list(self.input_fields),'output_fields':list(self.output_fields),
            'skill_id':self.skill_id,'allowed_tools':list(self.allowed_tools),
            'timeout_seconds':self.timeout_seconds,'max_retries':self.max_retries,
            'recoverability':self.recoverability,'terminal_states':list(self.terminal_states),
            'event_fields':list(self.event_fields),
        }

    @property
    def spec_sha256(self):return _sha256(self.to_dict())


@dataclass(frozen=True)
class TransitionSpec:
    source:str
    target:str
    condition:str

    def to_dict(self):return {'source':self.source,'target':self.target,'condition':self.condition}


@dataclass(frozen=True)
class GraphSpec:
    id:str
    version:str
    state_schema_version:str
    state_fields:tuple[str,...]
    initial_node:str
    nodes:tuple[NodeSpec,...]
    transitions:tuple[TransitionSpec,...]

    def __post_init__(self):
        if not self.id or not self.version or not self.state_schema_version:
            raise ValueError('graph identity and state schema are required')
        node_ids=[node.id for node in self.nodes]
        if not node_ids or len(node_ids)!=len(set(node_ids)):
            raise ValueError('graph nodes must be non-empty and unique')
        if self.initial_node not in node_ids:raise ValueError('initial node is not registered')
        known=set(node_ids)
        for edge in self.transitions:
            if edge.source not in known or edge.target not in known:
                raise ValueError(f'unknown graph transition: {edge.source}->{edge.target}')
        if len({(edge.source,edge.target,edge.condition) for edge in self.transitions})!=len(self.transitions):
            raise ValueError('duplicate graph transition')

    @property
    def node_map(self):return {node.id:node for node in self.nodes}

    def require_node(self,node_id):
        try:return self.node_map[node_id]
        except KeyError as exc:raise KeyError(f'unknown graph node: {node_id}') from exc

    def to_dict(self):
        return {
            'id':self.id,'version':self.version,
            'state_schema_version':self.state_schema_version,
            'state_fields':list(self.state_fields),'initial_node':self.initial_node,
            'nodes':[node.to_dict() for node in self.nodes],
            'transitions':[edge.to_dict() for edge in self.transitions],
        }

    @property
    def spec_sha256(self):return _sha256(self.to_dict())

    def export(self):
        return {**self.to_dict(),'spec_sha256':self.spec_sha256}

