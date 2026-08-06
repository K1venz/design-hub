import logging
import re
import sys
import traceback
from collections.abc import Awaitable, Callable, MutableMapping
from pathlib import Path
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

from design_hub.infrastructure.monitoring.runtime_log_files import (
    RuntimeLogService,
    runtime_log_handler,
)

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
        "endpoint_kind",
        "queue_depth",
        "outbox_age_seconds",
        "publish_attempts",
    }
)
_RUNTIME_LOG_KEYS = _ALLOWED_LOG_KEYS | frozenset(
    {
        "event_id",
        "service",
        "chain",
        "action",
        "function",
        "model",
        "prompt",
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
    return _redact_text(value)[:1000]


def _redact_text(value: str) -> str:
    value = _REDIS_CREDENTIALS.sub(r"\1[REDACTED]@", value)
    value = _URL_QUERY.sub(r"\1?[REDACTED]", value)
    value = _BEARER.sub("Bearer [REDACTED]", value)
    value = _OPENAI_KEY.sub("sk-[REDACTED]", value)
    value = _SECRET_ASSIGNMENT.sub(r"\1=[REDACTED]", value)
    return value


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


def add_runtime_context(
    service: RuntimeLogService,
) -> Processor:
    def processor(
        logger: WrappedLogger,
        method_name: str,
        event_dict: EventDict,
    ) -> EventDict:
        del logger, method_name
        record = event_dict.get("_record")
        if isinstance(record, logging.LogRecord):
            event_dict["function"] = record.funcName
        event_dict["service"] = service
        event_dict["event_id"] = uuid4().hex
        return event_dict

    return processor


def sanitize_runtime_event(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    del logger, method_name
    sanitized: EventDict = {}
    for key in _RUNTIME_LOG_KEYS:
        value = event_dict.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            sanitized[key] = (
                _redact_text(value) if key == "prompt" else _safe_text(value)
            )
        elif isinstance(value, (int, float, bool)):
            sanitized[key] = value
        else:
            sanitized[key] = str(value)[:200]
    return sanitized


def add_safe_exception_context(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    del logger, method_name
    exc_info = event_dict.pop("exc_info", None)
    record = event_dict.get("_record")
    if exc_info is None and isinstance(record, logging.LogRecord):
        exc_info = record.exc_info
    if exc_info is True:
        exc_info = sys.exc_info()
    if not isinstance(exc_info, tuple) or len(exc_info) != 3:
        return event_dict

    exception_type, _exception, exception_traceback = exc_info
    type_name = getattr(exception_type, "__name__", None)
    if isinstance(type_name, str):
        event_dict["error_type"] = type_name
    if exception_traceback is not None:
        frames = traceback.extract_tb(exception_traceback)[-8:]
        event_dict["error_summary"] = " > ".join(
            f"{frame.filename.rsplit('/', 1)[-1]}:{frame.lineno}:{frame.name}"
            for frame in frames
        )
    return event_dict


def configure_logging(
    *,
    level: int = logging.INFO,
    stream: TextIO | None = None,
    runtime_log_dir: Path | None = None,
    service: RuntimeLogService | None = None,
    runtime_log_max_bytes: int = 50 * 1024 * 1024,
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
    stdout_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[
            structlog.stdlib.ExtraAdder(),
            *shared,
        ],
        processors=[
            add_safe_exception_context,
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            sanitize_event,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
    )
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(stdout_formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    if runtime_log_dir is not None or service is not None:
        if runtime_log_dir is None or service is None:
            raise ValueError(
                "runtime_log_dir and service must be configured together"
            )
        runtime_handler = runtime_log_handler(
            runtime_log_dir,
            service,
            runtime_log_max_bytes,
        )
        runtime_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                foreign_pre_chain=[
                    structlog.stdlib.ExtraAdder(),
                    *shared,
                ],
                processors=[
                    add_safe_exception_context,
                    add_runtime_context(service),
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    sanitize_runtime_event,
                    structlog.processors.JSONRenderer(ensure_ascii=False),
                ],
            )
        )
        root.addHandler(runtime_handler)
    root.setLevel(level)
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True


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
