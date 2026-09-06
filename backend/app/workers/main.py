"""Long-polling ingestion worker entrypoint (blueprint section 9.1).

Runs as its own process/container (Dockerfile.worker), completely separate
from the FastAPI service, so parsing/embedding load can never compete with
query-path compute or scale independently of it (section 4.2/4).
"""
import asyncio
import logging
import uuid

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import get_sessionmaker
from app.ingestion.errors import PermanentError, RetryableError
from app.ingestion.pipeline import DocumentAlreadyClaimed, process_document
from app.queue import sqs
from app.rag.embeddings import get_embedding_provider

logger = logging.getLogger(__name__)


async def _handle_message(message: sqs.QueueMessage) -> None:
    settings = get_settings()
    embedding_provider = get_embedding_provider(settings)
    sessionmaker = get_sessionmaker()

    async with sessionmaker() as db:
        try:
            await process_document(
                db,
                document_id=uuid.UUID(message.document_id),
                settings=settings,
                embedding_provider=embedding_provider,
            )
        except DocumentAlreadyClaimed:
            # Duplicate delivery of a job another worker already claimed --
            # at-least-once delivery means this is expected, not an error
            # (section 9.2). Fall through to delete the message below.
            logger.info(
                "job already claimed, treating as duplicate delivery",
                extra={"context": {"document_id": message.document_id, "job_id": message.job_id}},
            )
        except PermanentError as exc:
            # process_document already marked the document FAILED; delete
            # the message so it does not keep retrying an unfixable job.
            logger.error(
                "permanent ingestion failure",
                extra={"context": {"document_id": message.document_id, "error_code": exc.error_code}},
            )
        # RetryableError intentionally propagates uncaught -- the caller
        # leaves the message un-deleted so SQS redelivers it after the
        # visibility timeout expires.

    sqs.delete_message(receipt_handle=message.receipt_handle)


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(service="worker", level=settings.log_level)
    logger.info("AtlasDocs worker starting", extra={"context": {"environment": settings.environment}})

    while True:
        try:
            messages = sqs.receive_messages()
        except Exception:
            logger.exception("failed to poll queue; backing off")
            await asyncio.sleep(5)
            continue

        for message in messages:
            try:
                await _handle_message(message)
            except RetryableError as exc:
                logger.warning(
                    "retryable ingestion failure, message left for redelivery",
                    extra={"context": {"document_id": message.document_id, "error": str(exc)}},
                )
            except Exception:
                logger.exception(
                    "unexpected worker error; message left for redelivery",
                    extra={"context": {"document_id": message.document_id}},
                )


if __name__ == "__main__":
    asyncio.run(run_worker())
