from dataclasses import dataclass
from typing import Literal

from chain_eye.domain.contracts import Evidence,Fact

@dataclass(frozen=True,slots=True)
class DocumentWord:
    text: str
    bbox: tuple[float,float,float,float]

@dataclass(frozen=True,slots=True)
class DocumentBlock:
    text: str
    bbox: tuple[float,float,float,float]

@dataclass(frozen=True,slots=True)
class DocumentPage:
    page_no: int
    text: str
    words: tuple[DocumentWord,...]
    blocks: tuple[DocumentBlock,...]
    table_candidates: tuple[str,...]
    parse_warnings: tuple[str,...]

@dataclass(frozen=True,slots=True)
class DocumentPages:
    source_id: str
    page_count: int
    pages: tuple[DocumentPage,...]

@dataclass(frozen=True,slots=True)
class ExtractionResult:
    facts: tuple[Fact,...]
    evidence: tuple[Evidence,...]
    parse_status: Literal['parsed','needs_review','failed']
    warnings: tuple[str,...]

class ExtractionError(ValueError):
    pass
