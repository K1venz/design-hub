from typing import Protocol

from design_hub.domain.runtime_logs import (
    RuntimeLogEntry,
    RuntimeLogPage,
    RuntimeLogQuery,
)


class RuntimeLogRepository(Protocol):
    def list(
        self,
        query: RuntimeLogQuery,
        *,
        limit: int,
        offset: int,
    ) -> RuntimeLogPage: ...

    def get(self, event_id: str) -> RuntimeLogEntry | None: ...

    def trace(self, trace_id: str) -> tuple[RuntimeLogEntry, ...]: ...
