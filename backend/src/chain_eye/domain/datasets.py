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

class Source(Contract):
    id: str
    filename: str
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    media_type: Literal['application/pdf','text/csv']
    page_count: int | None = Field(default=None,ge=1)
    url: str | None
    published_date: str | None
    parse_status: Literal['queued','parsed','needs_review','failed']
    data_basis: Literal['reviewed_fixture','user_uploaded']

class SourceAttachment(Contract):
    dataset: Dataset
    source: Source

class DatasetSourceLimitError(ValueError):
    pass
