"""Backend citation validation (blueprint section 13.3).

Citation correctness is enforced here as a testable property, not left to
prompt wording: any source_id the model returns that wasn't actually in
the supplied context is dropped, never surfaced to the client, and never
fabricated. See backend/tests/test_citations.py.
"""
import uuid
from dataclasses import dataclass

from app.rag.generation import CitationClaim
from app.rag.prompt import SourceBlock

_EXCERPT_MAX_CHARS = 400


def _truncate(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + "..."


@dataclass(frozen=True)
class ValidatedCitation:
    source_id: str
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    filename: str
    page_start: int | None
    page_end: int | None
    excerpt: str
    claim: str


def validate_citations(
    claimed: list[CitationClaim], sources: list[SourceBlock]
) -> list[ValidatedCitation]:
    by_id = {s.source_id: s for s in sources}
    validated: list[ValidatedCitation] = []
    seen: set[str] = set()
    for citation in claimed:
        if citation.source_id in seen:
            continue
        block = by_id.get(citation.source_id)
        if block is None:
            # The model cited a source_id that was never in the context --
            # discard rather than trust it (section 13.3 step 2).
            continue
        seen.add(citation.source_id)
        validated.append(
            ValidatedCitation(
                source_id=citation.source_id,
                document_id=block.chunk.document_id,
                chunk_id=block.chunk.chunk_id,
                filename=block.filename,
                page_start=block.chunk.page_start,
                page_end=block.chunk.page_end,
                excerpt=_truncate(block.chunk.content, _EXCERPT_MAX_CHARS),
                claim=citation.claim,
            )
        )
    return validated
