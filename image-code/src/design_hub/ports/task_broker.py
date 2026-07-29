from dataclasses import dataclass
from typing import Protocol

from design_hub.domain.tasking import TaskMessage


@dataclass(frozen=True)
class Delivery:
    redis_id: str
    message: TaskMessage


class TaskBroker(Protocol):
    async def ensure_group(self) -> None: ...

    async def publish(self, message: TaskMessage) -> str: ...

    async def read(
        self, *, consumer: str, count: int, block_ms: int
    ) -> tuple[Delivery, ...]: ...

    async def autoclaim(
        self, *, consumer: str, min_idle_ms: int, count: int
    ) -> tuple[Delivery, ...]: ...

    async def ack(self, redis_id: str) -> None: ...

    async def close(self) -> None: ...
