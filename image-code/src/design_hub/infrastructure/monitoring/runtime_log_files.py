import heapq
import json
import logging
import sys
import threading
from collections.abc import Iterator
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Literal, cast

import sentry_sdk

from design_hub.domain.runtime_logs import (
    RuntimeLogCorruptError,
    RuntimeLogEntry,
    RuntimeLogLevel,
    RuntimeLogPage,
    RuntimeLogQuery,
    RuntimeLogServiceName,
)

RuntimeLogService = Literal["api", "worker"]

_RUNTIME_LOG_FILENAMES = (
    "api.jsonl",
    "api.jsonl.1",
    "worker.jsonl",
    "worker.jsonl.1",
)
_error_report_lock = threading.Lock()
_error_reported = False


def is_business_chain_record(record: logging.LogRecord) -> bool:
    chain = getattr(record, "chain", None)
    action = getattr(record, "action", None)
    return (
        record.name.startswith("design_hub.")
        and isinstance(chain, str)
        and bool(chain)
        and isinstance(action, str)
        and bool(action)
    )


class BusinessChainFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return is_business_chain_record(record)


class RuntimeBusinessLogHandler(RotatingFileHandler):
    def handleError(self, record: logging.LogRecord) -> None:
        del record
        error = sys.exc_info()[1]
        if isinstance(error, BaseException):
            try:
                sentry_sdk.capture_exception(error)
            except Exception:
                pass
        global _error_reported
        with _error_report_lock:
            if _error_reported:
                return
            _error_reported = True
        try:
            sys.stderr.write("runtime business log write failed\n")
        except Exception:
            pass


def runtime_log_handler(
    directory: Path,
    service: RuntimeLogService,
    max_bytes: int,
) -> logging.Handler:
    directory.mkdir(parents=True, exist_ok=True)
    handler = RuntimeBusinessLogHandler(
        directory / f"{service}.jsonl",
        maxBytes=max_bytes,
        backupCount=1,
        encoding="utf-8",
    )
    handler.addFilter(BusinessChainFilter())
    return handler


class FileRuntimeLogRepository:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def list(
        self,
        query: RuntimeLogQuery,
        *,
        limit: int,
        offset: int,
    ) -> RuntimeLogPage:
        retained = offset + limit
        newest: list[tuple[datetime, str, int, RuntimeLogEntry]] = []
        total = 0
        for sequence, entry in enumerate(self._entries()):
            if not _matches(entry, query):
                continue
            total += 1
            candidate = (
                entry.timestamp,
                entry.event_id,
                sequence,
                entry,
            )
            if len(newest) < retained:
                heapq.heappush(newest, candidate)
            elif candidate[:3] > newest[0][:3]:
                heapq.heapreplace(newest, candidate)
        page = [item[3] for item in sorted(newest, reverse=True)]
        return RuntimeLogPage(
            items=tuple(page[offset:]),
            total=total,
            limit=limit,
            offset=offset,
        )

    def get(self, event_id: str) -> RuntimeLogEntry | None:
        for entry in self._entries():
            if entry.event_id == event_id:
                return entry
        return None

    def trace(self, trace_id: str) -> tuple[RuntimeLogEntry, ...]:
        entries = [
            entry
            for entry in self._entries()
            if entry.trace_id == trace_id
        ]
        entries.sort(key=lambda entry: (entry.timestamp, entry.event_id))
        return tuple(entries)

    def _entries(self) -> Iterator[RuntimeLogEntry]:
        for filename in _RUNTIME_LOG_FILENAMES:
            path = self._directory / filename
            if not path.exists():
                continue
            with path.open(encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, start=1):
                    if not line.strip():
                        continue
                    try:
                        yield _parse_entry(line)
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                        raise RuntimeLogCorruptError(
                            f"{filename}:{line_number}"
                        ) from None


def _parse_entry(line: str) -> RuntimeLogEntry:
    raw = json.loads(line)
    if not isinstance(raw, dict):
        raise TypeError("runtime log entry must be an object")
    timestamp_raw = _required_text(raw, "timestamp")
    timestamp = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("runtime log timestamp must include timezone")
    level_raw = _required_text(raw, "level")
    if level_raw not in {"info", "warning", "error"}:
        raise ValueError("invalid runtime log level")
    level = cast(RuntimeLogLevel, level_raw)
    service_raw = _required_text(raw, "service")
    if service_raw not in {"api", "worker"}:
        raise ValueError("invalid runtime log service")
    service = cast(RuntimeLogServiceName, service_raw)
    duration = raw.get("duration_ms")
    if duration is not None and (
        not isinstance(duration, int) or isinstance(duration, bool)
    ):
        raise TypeError("invalid runtime log duration")
    return RuntimeLogEntry(
        event_id=_required_text(raw, "event_id"),
        timestamp=timestamp,
        level=level,
        service=service,
        chain=_required_text(raw, "chain"),
        event=_required_text(raw, "event"),
        action=_required_text(raw, "action"),
        logger=_required_text(raw, "logger"),
        function=_required_text(raw, "function"),
        trace_id=_optional_text(raw, "trace_id"),
        request_id=_optional_text(raw, "request_id"),
        job_id=_optional_text(raw, "job_id"),
        item_id=_optional_text(raw, "item_id"),
        operation_id=_optional_text(raw, "operation_id"),
        provider=_optional_text(raw, "provider"),
        model=_optional_text(raw, "model"),
        status=_optional_text(raw, "status"),
        error_code=_optional_text(raw, "error_code"),
        error_type=_optional_text(raw, "error_type"),
        error_summary=_optional_text(raw, "error_summary"),
        duration_ms=duration,
        prompt=_optional_text(raw, "prompt"),
    )


def _required_text(raw: dict[str, object], field: str) -> str:
    value = raw[field]
    if not isinstance(value, str) or not value:
        raise TypeError(f"invalid runtime log field: {field}")
    return value


def _optional_text(raw: dict[str, object], field: str) -> str | None:
    value = raw.get(field)
    if value is not None and not isinstance(value, str):
        raise TypeError(f"invalid runtime log field: {field}")
    return value


def _matches(entry: RuntimeLogEntry, query: RuntimeLogQuery) -> bool:
    if query.level is not None and entry.level != query.level:
        return False
    if query.service is not None and entry.service != query.service:
        return False
    if query.chain is not None and entry.chain != query.chain:
        return False
    if query.trace_id is not None and entry.trace_id != query.trace_id:
        return False
    if query.job_id is not None and entry.job_id != query.job_id:
        return False
    if query.start is not None and entry.timestamp < query.start:
        return False
    if query.end is not None and entry.timestamp > query.end:
        return False
    return True
