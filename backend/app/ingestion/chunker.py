"""Structure-aware chunking (blueprint section 10).

Chunk size and overlap are treated as evaluation parameters, not facts --
callers pass them in (see app.core.config for the defaults and
evaluation/run_eval.py for the experiment matrix from section 15.5) rather
than this module hardcoding "the right" values.

Token counting here is a cheap approximation (chars / 4), not a real
tokenizer for any specific model. That's an intentional simplification for
a portfolio project: it's consistent within a run, which is all chunk-size
tuning needs, but should not be quoted as an exact token count for a
specific provider.
"""
import hashlib
from dataclasses import dataclass

from app.ingestion.parser import Unit

_HARD_MAX_MULTIPLIER = 1.6  # a single unit may exceed the target by this much before being force-split


def approx_token_count(text: str) -> int:
    return max(1, len(text) // 4)


@dataclass(frozen=True)
class Chunk:
    chunk_index: int
    content: str
    page_start: int | None
    page_end: int | None
    section_path: str | None
    token_count: int
    content_sha256: str


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _split_on_words(text: str, target_chars: int) -> list[str]:
    """Last-resort fallback for text with no sentence-ending periods at all
    (e.g. a wall of repeated tokens, or prose using only line breaks) --
    slices on word boundaries so `_force_split` is guaranteed to make
    progress instead of returning its input unchanged.
    """
    words = text.split()
    pieces: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in words:
        if current and current_len + len(word) + 1 > target_chars:
            pieces.append(" ".join(current))
            current, current_len = [], 0
        current.append(word)
        current_len += len(word) + 1
    if current:
        pieces.append(" ".join(current))
    return pieces


def _force_split(unit: Unit, target_tokens: int) -> list[Unit]:
    """Only invoked when a single paragraph alone exceeds the hard maximum
    (section 10.1 step 3) -- splits on sentence boundaries first, then
    falls back to word-boundary slicing for any piece that still doesn't
    fit (guaranteeing this always makes progress, unlike sentence-splitting
    alone on text with no ". " boundaries).
    """
    target_chars = target_tokens * 4
    sentences = unit.text.replace("\n", " ").split(". ")
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current}. {sentence}".strip(". ").strip() if current else sentence
        if len(candidate) > target_chars and current:
            pieces.append(current.strip())
            current = sentence
        else:
            current = candidate
    if current:
        pieces.append(current.strip())

    final_pieces: list[str] = []
    for piece in pieces:
        if len(piece) > target_chars:
            final_pieces.extend(_split_on_words(piece, target_chars))
        else:
            final_pieces.append(piece)

    return [
        Unit(text=p, page_start=unit.page_start, page_end=unit.page_end, section_path=unit.section_path)
        for p in final_pieces
    ]


def chunk_units(units: list[Unit], *, target_tokens: int, overlap_tokens: int) -> list[Chunk]:
    hard_max = int(target_tokens * _HARD_MAX_MULTIPLIER)

    # Step 1: pre-split any unit that alone exceeds the hard maximum.
    expanded: list[Unit] = []
    for unit in units:
        if approx_token_count(unit.text) > hard_max:
            expanded.extend(_force_split(unit, target_tokens))
        else:
            expanded.append(unit)

    chunks: list[Chunk] = []
    current_units: list[Unit] = []
    current_tokens = 0
    chunk_index = 0

    def flush(carry_overlap: bool) -> list[Unit]:
        nonlocal chunk_index
        if not current_units:
            return []
        text = "\n\n".join(u.text for u in current_units)
        pages = [u.page_start for u in current_units if u.page_start is not None]
        pages += [u.page_end for u in current_units if u.page_end is not None]
        section_path = next((u.section_path for u in current_units if u.section_path), None)
        chunks.append(
            Chunk(
                chunk_index=chunk_index,
                content=text,
                page_start=min(pages) if pages else None,
                page_end=max(pages) if pages else None,
                section_path=section_path,
                token_count=approx_token_count(text),
                content_sha256=_hash(text),
            )
        )
        chunk_index += 1

        if not carry_overlap or overlap_tokens <= 0:
            return []
        # Step 4: carry a small overlap of prior trailing units (not
        # arbitrary character slices) into the next chunk. The first
        # trailing unit is always included even if it alone exceeds
        # overlap_tokens (better one unit of overlap than none), but
        # overlap_tokens <= 0 above means "no overlap at all" -- without
        # that guard this loop would still carry one unit regardless.
        overlap: list[Unit] = []
        tokens = 0
        for u in reversed(current_units):
            t = approx_token_count(u.text)
            if tokens + t > overlap_tokens and overlap:
                break
            overlap.insert(0, u)
            tokens += t
        return overlap

    for unit in expanded:
        unit_tokens = approx_token_count(unit.text)
        if current_units and current_tokens + unit_tokens > target_tokens:
            current_units = flush(carry_overlap=True)
            current_tokens = sum(approx_token_count(u.text) for u in current_units)
        current_units.append(unit)
        current_tokens += unit_tokens

    flush(carry_overlap=False)
    return chunks
