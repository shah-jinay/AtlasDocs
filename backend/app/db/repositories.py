"""Data-access functions grouped by aggregate. Kept as plain functions (not a
repository class hierarchy) since each one is a single, easily-testable
statement -- see blueprint section 22.1 for the unit-test list this supports.
"""
import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentChunk, IngestionJob, QueryCitation, QueryRun


# --------------------------------------------------------------------------
# Documents
# --------------------------------------------------------------------------

async def create_uploading_document(
    db: AsyncSession, *, owner_id: uuid.UUID, filename: str, mime_type: str, size_bytes: int
) -> Document:
    # Unique, non-guessable storage key -- never the raw filename (security
    # checklist, section 19: "never use raw user filenames as the storage key").
    document_id = uuid.uuid4()
    digest = hashlib.sha256(f"{owner_id}:{document_id}:{filename}".encode()).hexdigest()[:16]
    s3_key = f"documents/{owner_id}/{document_id}-{digest}"
    doc = Document(
        id=document_id,
        owner_id=owner_id,
        filename=filename,
        mime_type=mime_type,
        s3_key=s3_key,
        size_bytes=size_bytes,
        status="UPLOADING",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


async def get_document(db: AsyncSession, *, document_id: uuid.UUID, owner_id: uuid.UUID) -> Document | None:
    stmt = select(Document).where(Document.id == document_id, Document.owner_id == owner_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_documents(db: AsyncSession, *, owner_id: uuid.UUID) -> list[Document]:
    stmt = select(Document).where(Document.owner_id == owner_id).order_by(Document.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def mark_queued(db: AsyncSession, *, document: Document) -> IngestionJob:
    """Idempotent: a duplicate `/complete` call on an already-queued/processed
    document returns the existing job instead of enqueuing duplicate work
    (blueprint section 20, "Duplicate complete request").
    """
    if document.status != "UPLOADING":
        stmt = select(IngestionJob).where(IngestionJob.document_id == document.id).order_by(
            IngestionJob.started_at.desc().nullslast()
        )
        existing = (await db.execute(stmt)).scalars().first()
        if existing is not None:
            return existing

    document.status = "QUEUED"
    job = IngestionJob(document_id=document.id, status="QUEUED")
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def claim_job(db: AsyncSession, *, document_id: uuid.UUID) -> bool:
    """Compare-and-set QUEUED -> PROCESSING. Returns False if another worker
    (or a duplicate SQS delivery) already claimed it -- the caller should
    treat that as "already handled" and delete the message (section 9.2).
    """
    stmt = (
        update(Document)
        .where(Document.id == document_id, Document.status == "QUEUED")
        .values(status="PROCESSING")
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount == 1


async def mark_ready(db: AsyncSession, *, document_id: uuid.UUID, page_count: int, chunk_count: int) -> None:
    stmt = (
        update(Document)
        .where(Document.id == document_id)
        .values(
            status="READY",
            page_count=page_count,
            chunk_count=chunk_count,
            processed_at=datetime.now(timezone.utc),
            error_code=None,
            error_message=None,
        )
    )
    await db.execute(stmt)
    await db.commit()


async def mark_failed(db: AsyncSession, *, document_id: uuid.UUID, error_code: str, error_message: str) -> None:
    stmt = (
        update(Document)
        .where(Document.id == document_id)
        .values(status="FAILED", error_code=error_code, error_message=error_message[:2000])
    )
    await db.execute(stmt)
    await db.commit()


# --------------------------------------------------------------------------
# Chunks
# --------------------------------------------------------------------------

async def replace_chunks(
    db: AsyncSession, *, document_id: uuid.UUID, processing_version: int, chunks: list[DocumentChunk]
) -> None:
    """Write all chunks for a new processing_version. The previous version's
    rows are left untouched until the document flips to READY, so queries
    against the old version keep working during re-ingestion (section 9.2).
    """
    for chunk in chunks:
        chunk.document_id = document_id
        chunk.processing_version = processing_version
        db.add(chunk)
    await db.commit()


async def delete_stale_versions(db: AsyncSession, *, document_id: uuid.UUID, keep_version: int) -> None:
    stmt = select(DocumentChunk).where(
        DocumentChunk.document_id == document_id, DocumentChunk.processing_version != keep_version
    )
    stale = (await db.execute(stmt)).scalars().all()
    for chunk in stale:
        await db.delete(chunk)
    await db.commit()


# --------------------------------------------------------------------------
# Query telemetry
# --------------------------------------------------------------------------

async def record_query_run(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
    question: str,
    retrieval_k: int,
    answer: str | None,
    total_latency_ms: int,
    retrieval_latency_ms: int,
    generation_latency_ms: int,
    retrieved: list[tuple[uuid.UUID, int, float, bool]],  # (chunk_id, rank, distance, cited)
) -> QueryRun:
    run = QueryRun(
        owner_id=owner_id,
        question=question,
        retrieval_k=retrieval_k,
        answer=answer,
        total_latency_ms=total_latency_ms,
        retrieval_latency_ms=retrieval_latency_ms,
        generation_latency_ms=generation_latency_ms,
    )
    db.add(run)
    await db.flush()
    for chunk_id, rank, distance, cited in retrieved:
        db.add(QueryCitation(query_id=run.id, chunk_id=chunk_id, rank=rank, distance=distance, cited=cited))
    await db.commit()
    await db.refresh(run)
    return run
