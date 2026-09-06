"""Central application settings.

All infrastructure adapters (storage, queue, embeddings, generation) read their
configuration from here. Keeping this as a single Pydantic settings object
means local development and AWS deployment differ only by environment
variables -- never by code path.
"""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- General ---
    environment: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"

    # --- Database ---
    database_url: str = "postgresql+asyncpg://atlasdocs:atlasdocs@localhost:5432/atlasdocs"
    db_pool_size: int = 10

    # --- Auth (demo-grade; see app.core.security for rationale) ---
    dev_api_keys: str = "dev-key-alice:alice,dev-key-bob:bob"

    # --- Object storage (S3-compatible; MinIO locally, S3 in AWS) ---
    s3_endpoint_url: str | None = "http://localhost:9000"
    # Only needed against MinIO in docker-compose, where the API/worker
    # containers and the eventual caller of a presigned URL (browser, host
    # script) resolve "minio" differently -- see app.storage.s3 module
    # docstring. Leave unset for real S3 (and for MinIO reached only from
    # the host, e.g. running the API outside Docker).
    s3_public_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_access_key: str = "atlasdocs"
    s3_secret_key: str = "atlasdocs-secret"
    s3_bucket: str = "atlasdocs-documents"
    s3_force_path_style: bool = True
    s3_presign_expires_seconds: int = 900

    # --- Queue (SQS-compatible; ElasticMQ locally, SQS in AWS) ---
    sqs_endpoint_url: str | None = "http://localhost:9324"
    sqs_region: str = "us-east-1"
    sqs_access_key: str = "atlasdocs"
    sqs_secret_key: str = "atlasdocs-secret"
    sqs_queue_url: str = "http://localhost:9324/queue/atlasdocs-ingestion"
    sqs_dlq_url: str = "http://localhost:9324/queue/atlasdocs-ingestion-dlq"
    sqs_wait_time_seconds: int = 10
    sqs_visibility_timeout_seconds: int = 300
    sqs_max_messages: int = 5

    # --- Embeddings ---
    # "mock" is deterministic and needs no API key -- the default so the
    # vertical slice runs zero-config. Set to "openai" for real embeddings.
    embedding_provider: Literal["mock", "openai"] = "mock"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 384
    openai_api_key: str | None = None

    # --- Generation (LLM) ---
    # "mock" answers extractively from retrieved context and needs no API key.
    # Set to "anthropic" to use a real Claude model for generation.
    generation_provider: Literal["mock", "anthropic"] = "mock"
    generation_model: str = "claude-sonnet-5"
    anthropic_api_key: str | None = None

    # --- Ingestion / retrieval tuning (see blueprint sections 10, 12) ---
    chunk_target_tokens: int = 600
    chunk_overlap_tokens: int = 80
    max_document_size_bytes: int = 25 * 1024 * 1024
    allowed_mime_types: tuple[str, ...] = (
        "application/pdf",
        "text/plain",
        "text/markdown",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    retrieval_candidate_k: int = 20
    retrieval_top_k: int = 6


@lru_cache
def get_settings() -> Settings:
    return Settings()
