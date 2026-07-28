import asyncio
import time
from dataclasses import dataclass
from typing import Protocol

from redis.exceptions import RedisError

from design_hub.application.tasking.health import (
    QueueSnapshot,
    QueueSnapshotReader,
    RedisHealthState,
    RedisUnavailable,
)
from design_hub.infrastructure.monitoring.task_metrics import task_metrics

_GENERATION_STREAM = "design-hub:generation:v1"
_GENERATION_GROUP = "generation-workers-v1"


class RedisHealthClient(Protocol):
    async def ping(self) -> object: ...

    async def xinfo_groups(self, name: str) -> list[dict[str, object]]: ...


@dataclass(frozen=True)
class RedisQueueSnapshotReader(QueueSnapshotReader):
    client: RedisHealthClient
    rolling_item_seconds: float
    available_slots: int

    async def snapshot(self) -> QueueSnapshot:
        try:
            groups = await self.client.xinfo_groups(_GENERATION_STREAM)
        except RedisError as exc:
            raise RedisUnavailable(
                "generation queue metadata is unavailable"
            ) from exc
        group = next(
            (
                value
                for value in groups
                if value.get("name") == _GENERATION_GROUP
            ),
            None,
        )
        if group is None:
            depth = 0
            pending = 0
        else:
            pending = self._non_negative_int(group.get("pending"), "pending")
            lag_value = group.get("lag")
            lag = (
                0
                if lag_value is None
                else self._non_negative_int(lag_value, "lag")
            )
            depth = pending + lag
        task_metrics.set_stream(depth=depth, pending=pending)
        return QueueSnapshot(
            depth=depth,
            rolling_item_seconds=self.rolling_item_seconds,
            available_slots=self.available_slots,
        )

    @staticmethod
    def _non_negative_int(value: object, field: str) -> int:
        if not isinstance(value, int) or value < 0:
            raise TypeError(f"Redis group {field} must be a non-negative integer")
        return value


@dataclass(frozen=True)
class RedisHealthMonitor:
    client: RedisHealthClient
    state: RedisHealthState
    interval_seconds: float

    async def check_once(self) -> None:
        now = time.monotonic()
        try:
            await self.client.ping()
        except RedisError as exc:
            self.state.mark_unhealthy(type(exc).__name__, now=now)
            return
        self.state.mark_healthy(now=now)

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.check_once()
            try:
                await asyncio.wait_for(
                    stop.wait(),
                    timeout=self.interval_seconds,
                )
            except TimeoutError:
                continue
