from typing import Protocol
from chain_eye.domain.contracts import ScenarioRequest, ScenarioResult
from chain_eye.domain.extraction import DocumentPages
from chain_eye.api.dto import RunCreate,Run
class Parser(Protocol):
    def parse(self,source_id:str,content:bytes)->DocumentPages:...
class ScenarioService(Protocol):
    def execute(self,request:ScenarioRequest,idempotency_key:str)->ScenarioResult:...
class RunService(Protocol):
    def create(self,request:RunCreate,idempotency_key:str)->Run:...
