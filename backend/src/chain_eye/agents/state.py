"""Typed in-process state passed between Agent graph nodes."""
from dataclasses import dataclass,field
from typing import Any

from chain_eye.api.dto import RunCreate
from chain_eye.application.run_manifest import RunBindings

AGENT_STATE_SCHEMA_VERSION='1'
AGENT_STATE_FIELDS=(
    'run_id','dataset_id','dataset_version','mode','request','record','bindings',
    'started','run_deadline','artifacts',
)


@dataclass
class AgentState:
    """Runtime-only state; persisted identities remain in the Run record and events."""

    run_id:str
    dataset_id:str
    dataset_version:int
    mode:str
    request:RunCreate
    record:dict[str,Any]
    bindings:RunBindings
    started:float
    run_deadline:float
    artifacts:dict[str,Any]=field(default_factory=dict)

    def update_record(self,record):
        if record is not None:self.record=record
        return self.record

