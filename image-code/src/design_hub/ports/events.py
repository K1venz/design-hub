from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from design_hub.domain.models import TaskEvent


class EventPublisher(ABC):
    """发布任务进度事件（worker 侧）。"""

    @abstractmethod
    async def publish(self, event: TaskEvent) -> None:
        ...


class EventStream(ABC):
    """订阅某任务的事件流（SSE 侧）。ISP：与发布分离。"""

    @abstractmethod
    def subscribe(self, job_id: str) -> AsyncIterator[TaskEvent]:
        ...
