from dataclasses import dataclass
from typing import Any, Protocol
from chain_eye.domain.contracts import Calculation, Claim, Fact, ScenarioRequest, ScenarioResult
from chain_eye.domain.extraction import DocumentPages
from chain_eye.api.dto import Report,RunCreate,Run
class Parser(Protocol):
    def parse(self,source_id:str,content:bytes)->DocumentPages:...
class ScenarioService(Protocol):
    def execute(self,request:ScenarioRequest,idempotency_key:str)->ScenarioResult:...
class FinancialService(Protocol):
    def compute(self,fact_snapshot:list[Fact],requested_metric_ids:list[str])->list[Calculation]:...
class RunService(Protocol):
    def create(self,request:RunCreate,idempotency_key:str)->Run:...
class ReportService(Protocol):
    def build(self,run_snapshot:dict[str,Any],claims:list[Claim],calculations:list[Calculation])->Report:...


class TypedProviderError(RuntimeError):
    code='MODEL_FAILED';retryable=False


class ModelUnavailable(TypedProviderError):
    code='MODEL_UNAVAILABLE';retryable=True


class ModelRateLimited(TypedProviderError):
    code='MODEL_RATE_LIMITED';retryable=True


class ModelInvalidResponse(TypedProviderError):
    code='MODEL_INVALID_RESPONSE';retryable=False


@dataclass(frozen=True)
class LLMResponse:
    output:dict[str,Any]
    provider:str
    model:str
    usage:dict[str,Any]
    latency_ms:int
    request_id:str|None
    cost:dict[str,Any]|None


class LLMPort(Protocol):
    def generate(
        self,task_name:str,prompt_version:str,messages:list[dict[str,str]],
        response_schema:dict[str,Any],budget:dict[str,Any],
    )->LLMResponse:...
