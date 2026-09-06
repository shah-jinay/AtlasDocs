"""Embedding provider interface (blueprint section 11).

Kept behind a `Protocol` so the project isn't coupled to one vendor, and so
a model change is forced to become a new `processing_version` rather than
silently mixing incompatible vectors (section 11.1) -- see
app.ingestion.pipeline where the provider's `model_name`/`dimension` are
persisted alongside the chunks they produced.

`MockEmbeddingProvider` is the default: deterministic, offline, and
dimension-matched to the initial migration, so `docker compose up` answers
real questions about real documents with zero API keys. It is a legitimate
retrieval baseline (semantically-blind bag-of-tokens hashing), not a stub
that fakes success -- recall against it will be worse than a real model,
which is exactly the kind of thing evaluation/run_eval.py is for.
"""
import hashlib
from typing import Protocol

import numpy as np

from app.core.config import Settings, get_settings


class EmbeddingProvider(Protocol):
    model_name: str
    dimension: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class MockEmbeddingProvider:
    """Deterministic hashed bag-of-words embedding. Same family of technique
    as feature hashing / the "hashing trick" -- no ML model, no network
    call, stable across runs and across processes.
    """

    model_name = "mock-hashing-v1"

    def __init__(self, dimension: int):
        self.dimension = dimension

    def _embed_one(self, text: str) -> list[float]:
        vector = np.zeros(self.dimension, dtype=np.float64)
        tokens = text.lower().split()
        if not tokens:
            return vector.tolist()
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector /= norm
        return vector.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)


class OpenAIEmbeddingProvider:
    """Real embeddings via OpenAI. Requires OPENAI_API_KEY and
    EMBEDDING_DIMENSION to match the model's native output size (1536 for
    text-embedding-3-small) -- changing this after data has been ingested
    requires a new migration and a new processing_version, per section 11.
    """

    def __init__(self, *, api_key: str, model: str, dimension: int):
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self.model_name = model
        self.dimension = dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(model=self.model_name, input=texts, dimensions=self.dimension)
        return [d.embedding for d in resp.data]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    settings = settings or get_settings()
    if settings.embedding_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("EMBEDDING_PROVIDER=openai requires OPENAI_API_KEY")
        return OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key, model=settings.embedding_model, dimension=settings.embedding_dimension
        )
    return MockEmbeddingProvider(dimension=settings.embedding_dimension)
