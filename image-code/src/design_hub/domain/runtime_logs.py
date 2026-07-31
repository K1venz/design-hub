from dataclasses import dataclass
from datetime import datetime
from typing import Literal

RuntimeLogLevel = Literal["info", "warning", "error"]
RuntimeLogServiceName = Literal["api", "worker"]


class RuntimeLogCorruptError(Exception):
    pass


@dataclass(frozen=True)
class RuntimeLogEntry:
    event_id: str
    timestamp: datetime
    level: RuntimeLogLevel
    service: RuntimeLogServiceName
    chain: str
    event: str
    action: str
    logger: str
    function: str
    trace_id: str | None = None
    request_id: str | None = None
    job_id: str | None = None
    item_id: str | None = None
    operation_id: str | None = None
    provider: str | None = None
    model: str | None = None
    status: str | None = None
    error_code: str | None = None
    error_type: str | None = None
    error_summary: str | None = None
    duration_ms: int | None = None
    prompt: str | None = None


@dataclass(frozen=True)
class RuntimeLogQuery:
    level: RuntimeLogLevel | None = None
    service: RuntimeLogServiceName | None = None
    chain: str | None = None
    trace_id: str | None = None
    job_id: str | None = None
    start: datetime | None = None
    end: datetime | None = None


@dataclass(frozen=True)
class RuntimeLogPage:
    items: tuple[RuntimeLogEntry, ...]
    total: int
    limit: int
    offset: int
