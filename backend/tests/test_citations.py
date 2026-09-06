import uuid

from app.rag.citations import validate_citations
from app.rag.generation import CitationClaim
from app.rag.prompt import SourceBlock
from app.rag.retrieval import RetrievedChunk


def _source(source_id: str) -> SourceBlock:
    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content="Some retrieved passage text.",
        page_start=1,
        page_end=1,
        section_path=None,
        distance=0.1,
    )
    return SourceBlock(source_id=source_id, chunk=chunk, filename="doc.pdf")


def test_valid_citation_is_kept():
    sources = [_source("S1"), _source("S2")]
    result = validate_citations([CitationClaim(source_id="S1", claim="claim text")], sources)
    assert len(result) == 1
    assert result[0].source_id == "S1"
    assert result[0].filename == "doc.pdf"


def test_unknown_citation_is_dropped():
    """The core security property from section 13.3: a hallucinated
    source_id must never reach the client.
    """
    sources = [_source("S1")]
    result = validate_citations([CitationClaim(source_id="S99", claim="fabricated")], sources)
    assert result == []


def test_duplicate_citation_is_deduplicated():
    sources = [_source("S1")]
    result = validate_citations(
        [
            CitationClaim(source_id="S1", claim="first mention"),
            CitationClaim(source_id="S1", claim="second mention"),
        ],
        sources,
    )
    assert len(result) == 1


def test_empty_citations_returns_empty_list():
    assert validate_citations([], [_source("S1")]) == []


def test_mixed_valid_and_invalid_citations():
    sources = [_source("S1"), _source("S2")]
    result = validate_citations(
        [CitationClaim(source_id="S1", claim="ok"), CitationClaim(source_id="S7", claim="bad")], sources
    )
    assert [c.source_id for c in result] == ["S1"]
