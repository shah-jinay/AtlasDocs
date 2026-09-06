"""Request/response schemas (blueprint section 8, API Contract)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class UploadInitRequest(BaseModel):
    filename: str
    mime_type: str
    size_bytes: int = Field(gt=0)


class UploadInitResponse(BaseModel):
    document_id: uuid.UUID
    upload_url: str
    expires_in_seconds: int
    status: str


class CompleteUploadResponse(BaseModel):
    document_id: uuid.UUID
    status: str
    job_id: uuid.UUID


class DocumentResponse(BaseModel):
    document_id: uuid.UUID
    filename: str
    mime_type: str
    status: str
    size_bytes: int
    page_count: int | None
    chunk_count: int | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    processed_at: datetime | None

    @classmethod
    def from_model(cls, doc) -> "DocumentResponse":
        return cls(
            document_id=doc.id,
            filename=doc.filename,
            mime_type=doc.mime_type,
            status=doc.status,
            size_bytes=doc.size_bytes,
            page_count=doc.page_count,
            chunk_count=doc.chunk_count,
            error_code=doc.error_code,
            error_message=doc.error_message,
            created_at=doc.created_at,
            processed_at=doc.processed_at,
        )


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    document_ids: list[uuid.UUID] | None = None
    top_k: int | None = None
    eval_mode: bool = False


class CitationResponse(BaseModel):
    source_id: str
    document_id: uuid.UUID
    filename: str
    page_start: int | None
    page_end: int | None
    excerpt: str


class DebugRetrievedChunk(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    distance: float
    rank: int


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationResponse]
    request_id: uuid.UUID
    insufficient_evidence: bool
    debug_retrieved_chunks: list[DebugRetrievedChunk] | None = None
