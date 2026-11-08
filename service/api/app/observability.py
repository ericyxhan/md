"""Request IDs, structured logs, and lightweight audit helpers.

Every HTTP request receives an ``X-Request-ID``.  Incoming IDs are accepted
only when they match a small safe character set; otherwise a new ID is
generated.  The ID is stored in a context variable so service code and the
request logger can include it without threading it through every signature.

Log records are emitted as one JSON object per line on stderr.  They never
include authorization headers, tokens, query strings, or request bodies.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import uuid
from contextvars import ContextVar
from typing import Any

from .timeutils import utcnow_iso

LOGGER_NAME = "md_service"
REQUEST_ID_HEADER = "X-Request-ID"

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_JOB_PATH_RE = re.compile(
    r"/(?:api/v1|internal/v1)/jobs/([A-Za-z0-9][A-Za-z0-9_-]{0,63})(?:/|$)"
)
_RESERVED_FIELDS = frozenset({"timestamp", "level", "event", "logger"})

request_id_var: ContextVar[str | None] = ContextVar(
    "md_request_id", default=None
)
client_ip_var: ContextVar[str | None] = ContextVar(
    "md_client_ip", default=None
)


def normalize_request_id(value: str | None) -> str | None:
    """Return a safe caller-supplied request ID, or ``None``."""

    if value is None:
        return None
    candidate = value.strip()
    if not candidate or not _REQUEST_ID_RE.match(candidate):
        return None
    return candidate


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


def current_request_id() -> str | None:
    return request_id_var.get()


def current_client_ip() -> str | None:
    return client_ip_var.get()


def extract_job_id(path: str) -> str | None:
    match = _JOB_PATH_RE.search(path)
    if match is None or match.group(1) == "validate":
        return None
    return match.group(1)


class JsonFormatter(logging.Formatter):
    """Render one JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": utcnow_iso(),
            "level": record.levelname.lower(),
            "event": getattr(record, "event", record.getMessage()),
            "logger": record.name,
        }
        request_id = getattr(record, "request_id", None) or current_request_id()
        if request_id:
            payload["request_id"] = request_id
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            for key, value in fields.items():
                if key in _RESERVED_FIELDS or value is None:
                    continue
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )


def configure_logging(level_name: str = "INFO") -> None:
    """Configure the dedicated service logger idempotently."""

    level = getattr(logging, str(level_name).upper(), logging.INFO)
    logger = logging.getLogger(LOGGER_NAME)
    logger.disabled = False
    logger.setLevel(level)
    logger.propagate = False
    marker = "_md_service_handler"
    if any(getattr(handler, marker, False) for handler in logger.handlers):
        return
    handler = logging.StreamHandler(stream=sys.stderr)
    setattr(handler, marker, True)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)


def log_event(
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Emit a structured service event.

    ``fields`` are copied into the JSON object.  Callers must not pass tokens,
    authorization headers, query strings, file contents, or raw configs.
    """

    logging.getLogger(LOGGER_NAME).log(
        level,
        event,
        extra={"event": event, "fields": fields},
    )
