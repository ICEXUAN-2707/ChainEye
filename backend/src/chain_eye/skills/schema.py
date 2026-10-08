"""Immutable schema for executable agent skill policy."""
import hashlib
import json
from dataclasses import dataclass
from typing import FrozenSet


@dataclass(frozen=True)
class SkillSpec:
    id:str
    version:str
    description:str
    instructions_path:str
    instructions_sha256:str
    instructions:str
    allowed_tools:FrozenSet[str]
    prompt_version:str|None
    input_requirements:tuple[str,...]
    output_constraints:tuple[str,...]
    input_contract:str
    output_contract:str
    timeout_seconds:int
    max_model_calls:int

    @property
    def spec_sha256(self):
        canonical=json.dumps({
            'id':self.id,'version':self.version,'description':self.description,
            'instructions_sha256':self.instructions_sha256,'allowed_tools':sorted(self.allowed_tools),
            'prompt_version':self.prompt_version,'input_requirements':list(self.input_requirements),
            'output_constraints':list(self.output_constraints),'input_contract':self.input_contract,
            'output_contract':self.output_contract,'timeout_seconds':self.timeout_seconds,
            'max_model_calls':self.max_model_calls,
        },ensure_ascii=False,sort_keys=True,separators=(',',':'))
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()
