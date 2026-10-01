from typing import Literal
from pydantic import Field
from .contracts import Contract

class DatasetCreate(Contract):
    name: str = Field(min_length=1,max_length=100)
    company: Literal['CATL']
    year: Literal[2024,2025]
class Dataset(Contract):
    id: str
    name: str
    company: Literal['CATL']
    year: Literal[2024,2025]
    version: int = Field(ge=1)
    source_ids: list[str]
    created_at: str
    data_basis: Literal['empty','reviewed_fixture','user_uploaded']
