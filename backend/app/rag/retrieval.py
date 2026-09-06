"""Tenant-safe vector retrieval (blueprint section 12.1).

Authorization is enforced *inside* this SQL, not only in application code
above it -- the query joins through `documents.owner_id` so the database
itself can never hand another tenant's chunk to the generator, even if a
caller forgets to filter in Python.

Raw SQL (rather than the ORM query builder) is used deliberately here: it
is the exact statement from the blueprint, it is the one place recall/
latency get benchmarked (evaluation/run_eval.py, section 15.2), and being
literal SQL makes an EXPLAIN ANALYZE trivial to run against it unchanged.
"""
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    content: str
    page_start: int | None
    page_end: int | None
    section_path: str | None
    distance: float


_QUERY = text(
    """
    SELECT
        c.id, c.document_id, c.content, c.page_start, c.page_end, c.section_path,
        c.embedding <=> CAST(:query_embedding AS vector) AS distance
    FROM document_chunks c
    JOIN documents d ON d.id = c.document_id
    WHERE d.owner_id = :owner_id
        AND d.status = 'READY'
        AND c.processing_version = d.processing_version
        AND (CAST(:document_ids AS uuid[]) IS NULL OR c.document_id = ANY(CAST(:document_ids AS uuid[])))
    ORDER BY c.embedding <=> CAST(:query_embedding AS vector)
    LIMIT :candidate_k
    """
)


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


async def retrieve_candidates(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
    query_embedding: list[float],
    document_ids: list[uuid.UUID] | None,
    candidate_k: int,
) -> list[RetrievedChunk]:
    result = await db.execute(
        _QUERY,
        {
            "owner_id": owner_id,
            "query_embedding": _vector_literal(query_embedding),
            "document_ids": document_ids,
            "candidate_k": candidate_k,
        },
    )
    return [
        RetrievedChunk(
            chunk_id=row.id,
            document_id=row.document_id,
            content=row.content,
            page_start=row.page_start,
            page_end=row.page_end,
            section_path=row.section_path,
            distance=row.distance,
        )
        for row in result
    ]
