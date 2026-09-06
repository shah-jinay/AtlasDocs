"""One-shot local/dev bootstrapping: ensure the S3 bucket and SQS queues
exist before the API or worker starts serving traffic. In real AWS, infra
(Terraform/CloudFormation/manual) creates these once -- this module exists
purely so `docker compose up` is a single command with nothing to click
through in a console first.
"""
import logging

from app.core.logging import configure_logging
from app.queue import sqs
from app.storage import s3

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging(service="bootstrap")
    logger.info("ensuring bucket and queues exist")
    s3.ensure_bucket()
    sqs.ensure_queues()
    logger.info("bootstrap complete")


if __name__ == "__main__":
    main()
