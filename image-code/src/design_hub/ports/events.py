from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol

from design_hub.domain.models import TaskEvent


class EventPublisher(ABC):
    """发布任务进度事件（任务执行侧）。"""

    @abstractmethod
    async def publish(self, event: TaskEvent) -> str | None:
        ...


@dataclass(frozen=True)
class ReplayableEvent:
    redis_id: str
    event: TaskEvent


class ReplayableEventStream(Protocol):
    async def read(
        self, *, job_id: str, after_id: str, block_ms: int
    ) -> tuple[ReplayableEvent, ...]: ...
