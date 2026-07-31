from dataclasses import dataclass
from datetime import UTC, datetime

from design_hub.domain.errors import NotFoundError
from design_hub.domain.runtime_logs import (
    RuntimeLogEntry,
    RuntimeLogPage,
    RuntimeLogQuery,
)
from design_hub.ports.runtime_logs import RuntimeLogRepository


@dataclass(frozen=True)
class RuntimeLogService:
    repository: RuntimeLogRepository

    def list(
        self,
        query: RuntimeLogQuery,
        *,
        limit: int,
        offset: int,
    ) -> RuntimeLogPage:
        if limit < 1 or limit > 200:
            raise ValueError("limit 必须在 1 到 200 之间")
        if offset < 0:
            raise ValueError("offset 不能为负数")
        return self.repository.list(
            self._normalized_query(query),
            limit=limit,
            offset=offset,
        )

    def get(self, event_id: str) -> RuntimeLogEntry:
        event_id = self._required_text(event_id, "event_id")
        entry = self.repository.get(event_id)
        if entry is None:
            raise NotFoundError("运行日志不存在")
        return entry

    def trace(self, event_id: str) -> tuple[RuntimeLogEntry, ...]:
        entry = self.get(event_id)
        if entry.trace_id is None:
            return (entry,)
        return self.repository.trace(entry.trace_id)

    @classmethod
    def _normalized_query(cls, query: RuntimeLogQuery) -> RuntimeLogQuery:
        start = cls._utc(query.start, "start")
        end = cls._utc(query.end, "end")
        if start is not None and end is not None and start > end:
            raise ValueError("start 不能晚于 end")
        return RuntimeLogQuery(
            level=query.level,
            service=query.service,
            chain=cls._optional_text(query.chain, "chain"),
            trace_id=cls._optional_text(query.trace_id, "trace_id"),
            job_id=cls._optional_text(query.job_id, "job_id"),
            start=start,
            end=end,
        )

    @staticmethod
    def _utc(value: datetime | None, field: str) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(f"{field} 必须包含时区")
        return value.astimezone(UTC)

    @staticmethod
    def _optional_text(value: str | None, field: str) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized or len(normalized) > 128:
            raise ValueError(f"{field} 无效")
        return normalized

    @classmethod
    def _required_text(cls, value: str, field: str) -> str:
        normalized = cls._optional_text(value, field)
        if normalized is None:
            raise ValueError(f"{field} 无效")
        return normalized
