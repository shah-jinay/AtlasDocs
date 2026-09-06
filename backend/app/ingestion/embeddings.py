"""Batch embedding orchestration (blueprint section 11.1).

Batches by item count and estimated token count, retries transient
provider errors with exponential backoff + jitter, and never wraps these
calls in a DB transaction -- callers persist the returned vectors in a
separate, short transaction (see app.ingestion.pipeline).
"""
import logging

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential

from app.ingestion.chunker import approx_token_count
from app.rag.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)

_MAX_ITEMS_PER_BATCH = 64
_MAX_TOKENS_PER_BATCH = 8000


class EmbeddingProviderError(Exception):
    """Wraps transient provider failures so tenacity has a single type to
    retry on, regardless of which concrete SDK raised it.
    """


def _batches(texts: list[str]) -> list[list[str]]:
    batches: list[list[str]] = []
    current: list[str] = []
    current_tokens = 0
    for text in texts:
        tokens = approx_token_count(text)
        if current and (len(current) >= _MAX_ITEMS_PER_BATCH or current_tokens + tokens > _MAX_TOKENS_PER_BATCH):
            batches.append(current)
            current, current_tokens = [], 0
        current.append(text)
        current_tokens += tokens
    if current:
        batches.append(current)
    return batches


@retry(
    retry=retry_if_exception_type(EmbeddingProviderError),
    wait=wait_random_exponential(multiplier=1, max=20),
    stop=stop_after_attempt(5),
    reraise=True,
)
def _embed_batch(provider: EmbeddingProvider, batch: list[str]) -> list[list[float]]:
    try:
        return provider.embed_documents(batch)
    except Exception as exc:  # provider SDKs each raise their own exception types
        logger.warning("embedding batch failed, will retry", extra={"context": {"error": str(exc)}})
        raise EmbeddingProviderError(str(exc)) from exc


def embed_chunks(provider: EmbeddingProvider, texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for batch in _batches(texts):
        vectors.extend(_embed_batch(provider, batch))
    return vectors
