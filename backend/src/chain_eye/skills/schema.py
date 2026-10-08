"""Immutable schema for executable agent skill policy."""
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
    timeout_seconds:int
    max_model_calls:int
