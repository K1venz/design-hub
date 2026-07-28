import logging
import re
import sys
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any, TextIO, cast
from uuid import uuid4

import sentry_sdk
import structlog
from fastapi import FastAPI, Request, Response
from sentry_sdk.types import Event
from structlog.contextvars import (
    bind_contextvars,
    clear_contextvars,
    merge_contextvars,
)
from structlog.typing import EventDict, Processor, WrappedLogger

_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")
_URL_QUERY = re.compile(r"(https?://[^\s?]+)\?[^\s]+", re.IGNORECASE)
_REDIS_CREDENTIALS = re.compile(
    r"(rediss?://)[^@\s/]+@", re.IGNORECASE
)
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_OPENAI_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{6,}")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|signature|password)=([^\s&]+)"
)
_ALLOWED_LOG_KEYS = frozenset(
    {
        "event",
        "level",
        "logger",
        "timestamp",
        "request_id",
        "trace_id",
        "message_id",
        "redis_id",
        "job_id",
        "item_id",
        "operation_id",
        "provider",
        "provider_task_id",
        "worker_id",
        "status",
        "error_code",
        "error_type",
        "error_summary",
        "duration_ms",
        "queue_depth",
        "outbox_age_seconds",
        "publish_attempts",
    }
)
_SENTRY_EXTRA_KEYS = frozenset(
    {
        "request_id",
        "trace_id",
        "job_id",
        "item_id",
        "operation_id",
        "provider",
        "error_code",
    }
)
_SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "proxy-authorization",
    }
)


def _safe_text(value: str) -> str:
    value = _REDIS_CREDENTIALS.sub(r"\1[REDACTED]@", value)
    value = _URL_QUERY.sub(r"\1?[REDACTED]", value)
    value = _BEARER.sub("Bearer [REDACTED]", value)
    value = _OPENAI_KEY.sub("sk-[REDACTED]", value)
    value = _SECRET_ASSIGNMENT.sub(r"\1=[REDACTED]", value)
    return value[:1000]


def sanitize_event(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    del logger, method_name
    sanitized: EventDict = {}
    for key in _ALLOWED_LOG_KEYS:
        value = event_dict.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            sanitized[key] = _safe_text(value)
        elif isinstance(value, (int, float, bool)):
            sanitized[key] = value
        else:
            sanitized[key] = str(value)[:200]
    return sanitized


def configure_logging(
    *,
    level: int = logging.INFO,
    stream: TextIO | None = None,
) -> None:
    shared: list[Processor] = [
        merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    structlog.configure(
        processors=[
            *shared,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[
            structlog.stdlib.ExtraAdder(),
            *shared,
        ],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            sanitize_event,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
    )
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def install_request_context(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        supplied = request.headers.get("X-Request-ID")
        request_id = (
            supplied
            if supplied is not None and _REQUEST_ID.fullmatch(supplied)
            else uuid4().hex
        )
        trace_id = request_id
        clear_contextvars()
        bind_contextvars(request_id=request_id, trace_id=trace_id)
        request.state.request_id = request_id
        request.state.trace_id = trace_id
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            clear_contextvars()


def scrub_sentry_event(
    event: Event,
    hint: dict[str, Any],
) -> Event:
    del hint
    mutable_event = cast(MutableMapping[str, Any], event)
    request = mutable_event.get("request")
    if isinstance(request, MutableMapping):
        headers = request.get("headers")
        if isinstance(headers, MutableMapping):
            request["headers"] = {
                str(key): value
                for key, value in headers.items()
                if str(key).lower() not in _SENSITIVE_HEADERS
            }
        request.pop("query_string", None)
        request.pop("data", None)
        request.pop("cookies", None)

    extra = mutable_event.get("extra")
    if isinstance(extra, MutableMapping):
        mutable_event["extra"] = {
            str(key): _safe_text(str(value))
            for key, value in extra.items()
            if str(key) in _SENTRY_EXTRA_KEYS
        }

    exception = mutable_event.get("exception")
    if isinstance(exception, MutableMapping):
        values = exception.get("values")
        if isinstance(values, list):
            for value in values:
                if not isinstance(value, MutableMapping):
                    continue
                exception_type = value.get("type")
                value["value"] = (
                    str(exception_type)
                    if exception_type is not None
                    else "Unhandled exception"
                )
                stacktrace = value.get("stacktrace")
                if isinstance(stacktrace, MutableMapping):
                    frames = stacktrace.get("frames")
                    if isinstance(frames, list):
                        for frame in frames:
                            if isinstance(frame, MutableMapping):
                                frame.pop("vars", None)

    mutable_event.pop("logentry", None)
    return event


def set_sentry_task_context(
    *,
    request_id: str,
    job_id: str,
    item_id: str,
    provider: str,
    error_code: str,
) -> None:
    for key, value in (
        ("request_id", request_id),
        ("job_id", job_id),
        ("item_id", item_id),
        ("provider", provider),
        ("error_code", error_code),
    ):
        sentry_sdk.set_tag(key, value)


def capture_task_exception(
    error: Exception,
    *,
    request_id: str,
    job_id: str,
    item_id: str,
    provider: str,
    error_code: str,
) -> None:
    set_sentry_task_context(
        request_id=request_id,
        job_id=job_id,
        item_id=item_id,
        provider=provider,
        error_code=error_code,
    )
    sentry_sdk.capture_exception(error)
