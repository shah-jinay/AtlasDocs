"""Structured JSON logging (blueprint section 21.1).

Emits one JSON object per line with a stable field set so logs are greppable
and CloudWatch-Logs-Insights-friendly in production. Never pass secrets,
presigned URLs, or full document text into `extra` -- see the security
checklist in section 19.
"""
import json
import logging
import sys
import time
from typing import Any

_REDACT_KEYS = {"password", "secret", "token", "authorization", "api_key", "presigned_url"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "service": getattr(record, "service", "atlasdocs"),
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.get("context", {}).items():
            if key.lower() in _REDACT_KEYS:
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(service: str, level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    old_factory = logging.getLogRecordFactory()

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = old_factory(*args, **kwargs)
        record.service = service
        return record

    logging.setLogRecordFactory(factory)


def log_with_context(logger: logging.Logger, level: int, message: str, **context: Any) -> None:
    logger.log(level, message, extra={"context": context})
