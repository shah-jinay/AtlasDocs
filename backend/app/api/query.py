"""Query endpoint (blueprint section 5.2, 8.3).

Ties together embedding the question, tenant-filtered pgvector retrieval,
context packing, citation-constrained generation, and backend citation
validation -- then persists query telemetry (section 7.1) so
evaluation/run_eval.py and the load test have real numbers to read back.
"""
import logging
import time
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import CitationResponse, DebugRetrievedChunk, QueryRequest, QueryResponse
from app.core.config import Settings, get_settings
from app.core.security import User, current_user, hash_for_logs
from app.db import repositories
from app.db.models import Document
from app.db.session import get_db
from app.rag.citations import validate_citations
from app.rag.embeddings import get_embedding_provider
from app.rag.generation import SYSTEM_PROMPT, get_generation_provider
from app.rag.prompt import build_context, build_user_message
from app.rag.retrieval import retrieve_candidates

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def ask_question(
    body: QueryRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> QueryResponse:
    total_start = time.perf_counter()
    top_k = body.top_k or settings.retrieval_top_k

    embedding_provider = get_embedding_provider(settings)
    query_embedding = embedding_provider.embed_query(body.question)

    retrieval_start = time.perf_counter()
    candidates = await retrieve_candidates(
        db,
        owner_id=user.id,
        query_embedding=query_embedding,
        document_ids=body.document_ids,
        candidate_k=settings.retrieval_candidate_k,
    )
    retrieval_latency_ms = int((time.perf_counter() - retrieval_start) * 1000)
    top_chunks = candidates[:top_k]

    filenames: dict[uuid.UUID, str] = {}
    if top_chunks:
        doc_ids = {c.document_id for c in top_chunks}
        rows = (await db.execute(select(Document.id, Document.filename).where(Document.id.in_(doc_ids)))).all()
        filenames = {row.id: row.filename for row in rows}

    context, sources = build_context(top_chunks, filenames)
    user_message = build_user_message(body.question, context)

    generation_provider = get_generation_provider(settings)
    generation_start = time.perf_counter()
    result = generation_provider.generate(system_prompt=SYSTEM_PROMPT, user_message=user_message)
    generation_latency_ms = int((time.perf_counter() - generation_start) * 1000)

    validated = validate_citations(result.citations, sources)
    cited_source_ids = {c.source_id for c in validated}

    total_latency_ms = int((time.perf_counter() - total_start) * 1000)

    await repositories.record_query_run(
        db,
        owner_id=user.id,
        question=body.question,
        retrieval_k=top_k,
        answer=result.answer,
        total_latency_ms=total_latency_ms,
        retrieval_latency_ms=retrieval_latency_ms,
        generation_latency_ms=generation_latency_ms,
        retrieved=[
            (c.chunk.chunk_id, i + 1, c.chunk.distance, c.source_id in cited_source_ids)
            for i, c in enumerate(sources)
        ],
    )

    logger.info(
        "query answered",
        extra={
            "context": {
                "user": hash_for_logs(user.email),
                "retrieval_latency_ms": retrieval_latency_ms,
                "generation_latency_ms": generation_latency_ms,
                "total_latency_ms": total_latency_ms,
                "retrieved_count": len(candidates),
                "cited_count": len(validated),
            }
        },
    )

    debug_chunks = (
        [
            DebugRetrievedChunk(chunk_id=c.chunk_id, document_id=c.document_id, distance=c.distance, rank=i + 1)
            for i, c in enumerate(candidates)
        ]
        if body.eval_mode
        else None
    )

    return QueryResponse(
        answer=result.answer,
        citations=[
            CitationResponse(
                source_id=v.source_id,
                document_id=v.document_id,
                filename=v.filename,
                page_start=v.page_start,
                page_end=v.page_end,
                excerpt=v.excerpt,
            )
            for v in validated
        ],
        request_id=uuid.uuid4(),
        insufficient_evidence=result.insufficient_evidence or not candidates,
        debug_retrieved_chunks=debug_chunks,
    )
