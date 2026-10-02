from typing import Literal
from pydantic import Field, model_validator
from chain_eye.domain.contracts import Contract, Fact, Evidence, Assumptions, Claim, Calculation, ScenarioResult, ErrorBody, AssumptionRecord, DecimalText

from chain_eye.domain.datasets import DatasetCreate,Dataset,Source,SourceAttachment
class FactCollection(Contract):
    dataset_id: str
    dataset_version: int = Field(ge=1)
    items: list[Fact]
class FactCorrection(Contract):
    expected_revision: int = Field(ge=1,strict=True)
    value: DecimalText | None
    raw_value: DecimalText | None = None
    status: Literal['verified','missing','needs_review']
    evidence_ids: list[str]
    reason: str = Field(min_length=1,max_length=1000)
    missing_reason: str | None = None
    @model_validator(mode='after')
    def values(self):
        if self.status=='missing' and (self.value is not None or not self.missing_reason):raise ValueError('missing needs null/reason')
        if self.status!='missing' and self.value is None:raise ValueError('value required')
        if self.status=='verified' and not self.evidence_ids:raise ValueError('evidence required')
        return self
class RunCreate(Contract):
    dataset_id: str
    dataset_version: int = Field(ge=1,strict=True)
    question: str = Field(min_length=1,max_length=4000)
    segment: Literal['power_battery','energy_storage']
    mode: Literal['live','replay']
    assumptions: Assumptions | None = None
    replay_run_id: str | None = None
    @model_validator(mode='after')
    def mode_rules(self):
        if self.mode=='replay' and not self.replay_run_id:raise ValueError('replay source required')
        if self.mode=='live' and self.replay_run_id is not None:raise ValueError('live cannot reference replay source')
        return self
class Run(Contract):
    id: str
    dataset_id: str
    dataset_version: int = Field(ge=1)
    status: Literal['queued','running','waiting_review','completed','partial','failed','cancelled']
    mode: Literal['live','replay']
    current_node: str | None
    missing_requirements: list[str]
    stale: bool
    error: ErrorBody | None
    report_ready: bool
class Event(Contract):
    seq: int = Field(ge=1)
    run_id: str
    type: Literal['file_access','tool_call','calculation','llm_call','node_status','report_generated','error']
    node: str
    at: str
    payload: dict
class EventCollection(Contract):
    items: list[Event]
    next_after_seq: int = Field(ge=0)
    has_more: bool
class ResumeRequest(Contract):
    expected_run_status: Literal['waiting_review']
    dataset_version: int = Field(ge=1,strict=True)
    assumptions: Assumptions | None = None
class Report(Contract):
    run_id: str
    dataset_id: str
    dataset_version: int = Field(ge=1)
    mode: Literal['live','replay']
    title: str
    facts: list[Fact]
    calculations: list[Calculation]
    claims: list[Claim]
    scenarios: list[ScenarioResult]
    assumptions: list[AssumptionRecord]
    evidence: list[Evidence]
    limitations: list[str]
    generated_at: str
class ErrorResponse(Contract):
    error: ErrorBody
class DatasetCollection(Contract):
    items: list[Dataset]
    next_offset: int | None
