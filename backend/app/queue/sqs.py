"""SQS-compatible queue adapter (blueprint section 4.1, 9.1).

Points at ElasticMQ locally and real SQS in AWS via the same boto3 client.
Standard queues are at-least-once, so every consumer of this module MUST be
idempotent -- see app.ingestion.pipeline.claim_and_process, which uses a
compare-and-set document status transition for exactly that reason.
"""
import json
from dataclasses import dataclass
from functools import lru_cache

import boto3
from botocore.client import BaseClient

from app.core.config import get_settings


@lru_cache
def _client() -> BaseClient:
    settings = get_settings()
    return boto3.client(
        "sqs",
        endpoint_url=settings.sqs_endpoint_url,
        region_name=settings.sqs_region,
        aws_access_key_id=settings.sqs_access_key,
        aws_secret_access_key=settings.sqs_secret_key,
    )


@dataclass(frozen=True)
class QueueMessage:
    receipt_handle: str
    job_id: str
    document_id: str
    attempt: int


def send_ingestion_job(*, job_id: str, document_id: str, attempt: int = 0) -> None:
    _client().send_message(
        QueueUrl=get_settings().sqs_queue_url,
        MessageBody=json.dumps({"job_id": job_id, "document_id": document_id, "attempt": attempt}),
    )


def receive_messages(*, max_messages: int | None = None, wait_time_seconds: int | None = None) -> list[QueueMessage]:
    settings = get_settings()
    resp = _client().receive_message(
        QueueUrl=settings.sqs_queue_url,
        MaxNumberOfMessages=max_messages or settings.sqs_max_messages,
        WaitTimeSeconds=wait_time_seconds if wait_time_seconds is not None else settings.sqs_wait_time_seconds,
        VisibilityTimeout=settings.sqs_visibility_timeout_seconds,
    )
    messages = []
    for raw in resp.get("Messages", []):
        body = json.loads(raw["Body"])
        messages.append(
            QueueMessage(
                receipt_handle=raw["ReceiptHandle"],
                job_id=body["job_id"],
                document_id=body["document_id"],
                attempt=body.get("attempt", 0),
            )
        )
    return messages


def delete_message(*, receipt_handle: str) -> None:
    _client().delete_message(QueueUrl=get_settings().sqs_queue_url, ReceiptHandle=receipt_handle)


def extend_visibility(*, receipt_handle: str, seconds: int) -> None:
    """Heartbeat for jobs that legitimately run longer than the static
    visibility timeout, instead of setting an excessively long static value
    (blueprint section 9.1).
    """
    _client().change_message_visibility(
        QueueUrl=get_settings().sqs_queue_url, ReceiptHandle=receipt_handle, VisibilityTimeout=seconds
    )


def queue_depth() -> int:
    """Backing metric for worker autoscaling (blueprint section 17.3) and
    for the load test's "SQS visible messages" column (section 16.2).
    """
    resp = _client().get_queue_attributes(
        QueueUrl=get_settings().sqs_queue_url, AttributeNames=["ApproximateNumberOfMessagesVisible"]
    )
    return int(resp["Attributes"]["ApproximateNumberOfMessagesVisible"])


def ensure_queues() -> None:
    """Idempotent queue creation for local/dev bootstrapping. ElasticMQ can
    also predefine queues from its own config file (see
    infra/elasticmq.conf) -- this is a defensive second path so the app is
    self-sufficient even against a broker with no preset config.
    """
    settings = get_settings()
    client = _client()
    dlq_name = settings.sqs_dlq_url.rsplit("/", 1)[-1]
    queue_name = settings.sqs_queue_url.rsplit("/", 1)[-1]
    existing = client.list_queues().get("QueueUrls", [])

    if not any(dlq_name in url for url in existing):
        client.create_queue(QueueName=dlq_name)

    if not any(queue_name in url for url in existing):
        attributes = {}
        try:
            dlq_arn = client.get_queue_attributes(
                QueueUrl=settings.sqs_dlq_url, AttributeNames=["QueueArn"]
            )["Attributes"]["QueueArn"]
            attributes["RedrivePolicy"] = json.dumps({"deadLetterTargetArn": dlq_arn, "maxReceiveCount": "5"})
        except Exception:
            # Some SQS-compatible brokers don't support redrive policy;
            # still create the main queue so the vertical slice keeps working.
            pass
        client.create_queue(QueueName=queue_name, Attributes=attributes)
