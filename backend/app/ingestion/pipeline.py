"""End-to-end ingestion for one document (blueprint section 5.1 steps 6-7,
section 9.2 idempotency strategy).

This is the function the worker calls per SQS message. It:
  1. Claims the job with a compare-and-set status transition -- if a
     duplicate delivery arrives after another worker already claimed it,
     this becomes a no-op instead of double-processing.
  2. Downloads, parses, chunks, and embeds outside of any DB transaction.
  3. Writes the new chunk version, then atomically flips the document to
     READY -- the previous good version is left in place until this
     succeeds, so the document never goes temporarily unqueryable.
"""
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db import repositories
from app.db.models import Document, DocumentChunk
from app.ingestion.chunker import chunk_units
from app.ingestion.embeddings import embed_chunks
from app.ingestion.errors import PermanentError
from app.ingestion.parser import parse
from app.rag.embeddings import EmbeddingProvider, get_embedding_provider
from app.storage import s3

logger = logging.getLogger(__name__)


class DocumentAlreadyClaimed(Exception):
    """Raised when this worker lost the compare-and-set race for a job --
    the caller should delete the SQS message and move on, not fail the job.
    """


async def process_document(
    db: AsyncSession,
    *,
    document_id: uuid.UUID,
    settings: Settings | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> None:
    settings = settings or get_settings()
    embedding_provider = embedding_provider or get_embedding_provider(settings)

    claimed = await repositories.claim_job(db, document_id=document_id)
    if not claimed:
        raise DocumentAlreadyClaimed(str(document_id))

    document = await db.get(Document, document_id)
    if document is None:
        raise PermanentError("DOCUMENT_NOT_FOUND", f"document {document_id} does not exist")

    next_version = document.processing_version + (1 if document.status == "READY" else 0)
    # Note: claim_job already set status to PROCESSING; processing_version
    # bump only applies on *re*-ingestion. On first ingestion it stays 1.

    try:
        raw_bytes = s3.get_object_bytes(key=document.s3_key)
        units = parse(mime_type=document.mime_type, data=raw_bytes)
        raw_chunks = chunk_units(
            units, target_tokens=settings.chunk_target_tokens, overlap_tokens=settings.chunk_overlap_tokens
        )
        if not raw_chunks:
            raise PermanentError("EMPTY_DOCUMENT", "Parsing produced zero chunks")

        vectors = embed_chunks(embedding_provider, [c.content for c in raw_chunks])

        db_chunks = [
            DocumentChunk(
                id=uuid.uuid4(),
                chunk_index=c.chunk_index,
                content=c.content,
                page_start=c.page_start,
                page_end=c.page_end,
                section_path=c.section_path,
                token_count=c.token_count,
                content_sha256=c.content_sha256,
                embedding=vector,
            )
            for c, vector in zip(raw_chunks, vectors, strict=True)
        ]

        await repositories.replace_chunks(
            db, document_id=document_id, processing_version=next_version, chunks=db_chunks
        )
        await repositories.delete_stale_versions(db, document_id=document_id, keep_version=next_version)
        await repositories.mark_ready(
            db, document_id=document_id, page_count=_estimate_page_count(units), chunk_count=len(db_chunks)
        )
        logger.info(
            "document ingested",
            extra={"context": {"document_id": str(document_id), "chunks": len(db_chunks), "version": next_version}},
        )
    except PermanentError as exc:
        await repositories.mark_failed(
            db, document_id=document_id, error_code=exc.error_code, error_message=str(exc)
        )
        logger.warning(
            "document ingestion failed permanently",
            extra={"context": {"document_id": str(document_id), "error_code": exc.error_code}},
        )
        # Permanent errors are not re-raised: the SQS message should still be
        # deleted (no point retrying), only the document is marked FAILED.


def _estimate_page_count(units: list) -> int:
    pages = [u.page_end for u in units if u.page_end is not None]
    return max(pages) if pages else 0
