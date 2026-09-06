import uuid

from app.rag.citations import is_evidence_insufficient, validate_citations
from app.rag.generation import CitationClaim
from app.rag.prompt import SourceBlock
from app.rag.retrieval import RetrievedChunk


def _source(source_id: str, content: str = "Some retrieved passage text.") -> SourceBlock:
    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content=content,
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


def test_excerpt_is_untouched_when_short():
    sources = [_source("S1", content="A short excerpt.")]
    result = validate_citations([CitationClaim(source_id="S1", claim="c")], sources)
    assert result[0].excerpt == "A short excerpt."


def test_excerpt_is_truncated_with_ellipsis_when_long():
    long_content = "word " * 200  # far more than 400 chars
    sources = [_source("S1", content=long_content)]
    result = validate_citations([CitationClaim(source_id="S1", claim="c")], sources)
    assert result[0].excerpt.endswith("...")
    assert len(result[0].excerpt) <= 403


def test_evidence_sufficient_with_a_validated_citation():
    sources = [_source("S1")]
    validated = validate_citations([CitationClaim(source_id="S1", claim="c")], sources)
    assert not is_evidence_insufficient(retrieved_count=1, validated=validated, provider_flag=False)


def test_evidence_insufficient_when_nothing_was_retrieved():
    assert is_evidence_insufficient(retrieved_count=0, validated=[], provider_flag=False)


def test_evidence_insufficient_when_model_abstains_with_prose_but_no_citations():
    """Regression test: a real LLM correctly abstaining by writing a full
    explanatory sentence with zero citations must still be flagged as
    insufficient evidence -- the provider's own self-reported flag isn't
    trustworthy enough to rely on alone (this is exactly what a real
    Claude response looked like when this bug was found).
    """
    assert is_evidence_insufficient(retrieved_count=3, validated=[], provider_flag=False)


def test_evidence_insufficient_when_provider_flag_is_set_even_with_citations():
    sources = [_source("S1")]
    validated = validate_citations([CitationClaim(source_id="S1", claim="c")], sources)
    assert is_evidence_insufficient(retrieved_count=1, validated=validated, provider_flag=True)
