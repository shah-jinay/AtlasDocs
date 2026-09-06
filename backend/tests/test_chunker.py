from app.ingestion.chunker import chunk_units
from app.ingestion.parser import Unit


def _unit(text: str, page: int | None = None) -> Unit:
    return Unit(text=text, page_start=page, page_end=page, section_path=None)


def test_chunk_boundaries_respect_target_size():
    # approx_token_count is chars/4, so "word " * 8 (40 chars) is ~10 tokens.
    units = [_unit("word " * 8, page=i) for i in range(1, 6)]
    chunks = chunk_units(units, target_tokens=20, overlap_tokens=0)

    assert len(chunks) > 1
    for chunk in chunks:
        # Each chunk should be close to the target, not wildly over it.
        assert chunk.token_count <= 20 * 1.6 + 5


def test_force_split_makes_progress_with_no_sentence_boundaries():
    """Regression test: text with no ". " anywhere (e.g. a wall of repeated
    tokens) must still get split down near the target, not pass through
    the sentence-boundary splitter unchanged.
    """
    huge = _unit("word " * 400)  # ~500 tokens, no periods at all
    chunks = chunk_units([huge], target_tokens=20, overlap_tokens=0)

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.token_count <= 20 * 1.6 + 5


def test_chunk_metadata_propagation():
    units = [_unit("Paragraph one.", page=1), _unit("Paragraph two.", page=2)]
    chunks = chunk_units(units, target_tokens=1000, overlap_tokens=0)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.page_start == 1
    assert chunk.page_end == 2
    assert "Paragraph one." in chunk.content
    assert "Paragraph two." in chunk.content


def test_chunk_overlap_carries_trailing_units():
    units = [_unit(f"Sentence number {i} is here to pad tokens out nicely.", page=i) for i in range(1, 8)]
    chunks = chunk_units(units, target_tokens=15, overlap_tokens=10)

    assert len(chunks) > 1
    # The second chunk should share at least some text with the tail of the first.
    first_tail = chunks[0].content.split("\n\n")[-1]
    assert first_tail in chunks[1].content


def test_chunk_index_is_sequential():
    units = [_unit(f"unit {i} " * 20, page=i) for i in range(1, 4)]
    chunks = chunk_units(units, target_tokens=10, overlap_tokens=0)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_content_hash_is_deterministic():
    units = [_unit("Stable content for hashing.")]
    a = chunk_units(units, target_tokens=100, overlap_tokens=0)
    b = chunk_units(units, target_tokens=100, overlap_tokens=0)
    assert a[0].content_sha256 == b[0].content_sha256


def test_force_split_on_oversized_single_unit():
    huge = _unit("This is one long sentence. " * 100)
    chunks = chunk_units([huge], target_tokens=20, overlap_tokens=0)
    assert len(chunks) > 1
