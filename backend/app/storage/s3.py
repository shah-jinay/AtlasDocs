"""S3-compatible object storage adapter (blueprint section 4.1, 8.1).

Points at MinIO locally and real S3 in AWS via the same boto3 client --
only `S3_ENDPOINT_URL` and credentials differ between environments. This is
the reason "durable S3 document store" on the resume is not a placeholder:
the exact code path that runs in this docker-compose stack is what would
run against a real bucket.

One MinIO-specific wrinkle real S3 doesn't have: the API/worker containers
reach MinIO at its docker-network hostname (`minio:9000`), but a presigned
URL is followed by the *browser* (or a local script), which can't resolve
that hostname -- only `localhost:9000` (the port docker-compose publishes
to the host). So presigned URLs are generated with a second, separately
configured "public" endpoint (`S3_PUBLIC_ENDPOINT_URL`), while every other
call (head_object, get_object, ensure_bucket) uses the container-internal
one. In real S3 both settings are simply left equal to the same public
endpoint, so this collapses into "one endpoint" outside of local dev.
"""
from dataclasses import dataclass
from functools import lru_cache

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings


def _make_client(endpoint_url: str | None, settings: Settings) -> BaseClient:
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=boto3.session.Config(s3={"addressing_style": "path" if settings.s3_force_path_style else "auto"}),
    )


@lru_cache
def _client() -> BaseClient:
    """Used for every server-side call (head/get/put/ensure_bucket) --
    addressed however the API/worker container itself reaches storage.
    """
    settings = get_settings()
    return _make_client(settings.s3_endpoint_url, settings)


@lru_cache
def _presign_client() -> BaseClient:
    """Used only to *generate* presigned URLs -- addressed however the
    eventual caller of that URL (browser, host script) reaches storage.
    Falls back to `s3_endpoint_url` when no public endpoint is configured
    (i.e. real AWS, where there's only one address anyway).
    """
    settings = get_settings()
    endpoint = settings.s3_public_endpoint_url or settings.s3_endpoint_url
    return _make_client(endpoint, settings)


@dataclass(frozen=True)
class ObjectMetadata:
    size_bytes: int
    content_type: str


def ensure_bucket(settings: Settings | None = None) -> None:
    """Idempotent bucket creation for local/dev bootstrapping. In AWS the
    bucket is created once by infra, not by the application; this no-ops
    (409) if it already exists.
    """
    settings = settings or get_settings()
    client = _client()
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except ClientError:
        client.create_bucket(Bucket=settings.s3_bucket)


def create_presigned_put(*, key: str, content_type: str, expires_seconds: int) -> str:
    return _presign_client().generate_presigned_url(
        "put_object",
        Params={"Bucket": get_settings().s3_bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=expires_seconds,
    )


def create_presigned_get(*, key: str, expires_seconds: int) -> str:
    return _presign_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": get_settings().s3_bucket, "Key": key},
        ExpiresIn=expires_seconds,
    )


def head_object(*, key: str) -> ObjectMetadata | None:
    """Verify the object actually landed in S3 before trusting a client's
    `/complete` call (blueprint section 5.1 step 5): never take "upload
    finished" on the client's word alone.
    """
    try:
        resp = _client().head_object(Bucket=get_settings().s3_bucket, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return None
        raise
    return ObjectMetadata(size_bytes=resp["ContentLength"], content_type=resp.get("ContentType", ""))


def get_object_bytes(*, key: str) -> bytes:
    resp = _client().get_object(Bucket=get_settings().s3_bucket, Key=key)
    return resp["Body"].read()


def put_object_bytes(*, key: str, data: bytes, content_type: str) -> None:
    """Used only by fixtures/tests and the local demo script -- the real
    upload path is always the browser PUTting directly to the presigned URL.
    """
    _client().put_object(Bucket=get_settings().s3_bucket, Key=key, Body=data, ContentType=content_type)


def delete_object(*, key: str) -> None:
    """S3 delete_object is idempotent -- deleting an already-gone or
    never-uploaded key is not an error, so callers (document deletion)
    don't need to check existence first.
    """
    _client().delete_object(Bucket=get_settings().s3_bucket, Key=key)
