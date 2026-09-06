"""Document control-plane endpoints (blueprint sections 5.1, 8.1, 8.2, 8.4)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    CompleteUploadResponse,
    DocumentResponse,
    UploadInitRequest,
    UploadInitResponse,
)
from app.core.config import Settings, get_settings
from app.core.security import User, current_user
from app.db import repositories
from app.db.session import get_db
from app.queue import sqs
from app.storage import s3

router = APIRouter(prefix="/v1/documents", tags=["documents"])


def _validate_upload(body: UploadInitRequest, settings: Settings) -> None:
    if body.mime_type not in settings.allowed_mime_types:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Unsupported mime_type '{body.mime_type}'. Allowed: {settings.allowed_mime_types}",
        )
    if body.size_bytes > settings.max_document_size_bytes:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"File exceeds maximum size of {settings.max_document_size_bytes} bytes",
        )
    if not body.filename or "/" in body.filename or "\\" in body.filename:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid filename")


@router.post("/uploads", response_model=UploadInitResponse, status_code=status.HTTP_201_CREATED)
async def create_upload(
    body: UploadInitRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UploadInitResponse:
    _validate_upload(body, settings)
    document = await repositories.create_uploading_document(
        db, owner_id=user.id, filename=body.filename, mime_type=body.mime_type, size_bytes=body.size_bytes
    )
    url = s3.create_presigned_put(
        key=document.s3_key, content_type=body.mime_type, expires_seconds=settings.s3_presign_expires_seconds
    )
    return UploadInitResponse(
        document_id=document.id,
        upload_url=url,
        expires_in_seconds=settings.s3_presign_expires_seconds,
        status=document.status,
    )


@router.post("/{document_id}/complete", response_model=CompleteUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def complete_upload(
    document_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> CompleteUploadResponse:
    document = await repositories.get_document(db, document_id=document_id, owner_id=user.id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    # Verify the object actually landed in S3 before queueing (section 5.1
    # step 5) -- never trust the client's word that the PUT succeeded.
    metadata = s3.head_object(key=document.s3_key)
    if metadata is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Upload not found in storage yet; retry once the PUT has completed"
        )

    job = await repositories.mark_queued(db, document=document)
    sqs.send_ingestion_job(job_id=str(job.id), document_id=str(document.id), attempt=job.attempt)
    return CompleteUploadResponse(document_id=document.id, status="QUEUED", job_id=job.id)


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> list[DocumentResponse]:
    docs = await repositories.list_documents(db, owner_id=user.id)
    return [DocumentResponse.from_model(d) for d in docs]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> DocumentResponse:
    doc = await repositories.get_document(db, document_id=document_id, owner_id=user.id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return DocumentResponse.from_model(doc)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> None:
    # get_document's owner_id filter is the authorization check here --
    # a document that exists but belongs to someone else looks identical
    # to one that doesn't exist at all.
    doc = await repositories.get_document(db, document_id=document_id, owner_id=user.id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    # Best-effort: the object may already be gone (delete_object is
    # idempotent) or never landed (a document stuck in UPLOADING) -- either
    # way the DB soft-delete below is what actually makes it disappear from
    # the user's document list and stop being retrievable.
    s3.delete_object(key=doc.s3_key)
    await repositories.mark_deleted(db, document_id=document_id)
