import asyncio
from collections.abc import AsyncIterator

from design_hub.domain.enums import TaskEventType
from design_hub.domain.models import TaskEvent
from design_hub.ports.events import EventPublisher, EventStream

_TERMINAL = {TaskEventType.TASK_COMPLETED, TaskEventType.TASK_FAILED}


class InMemoryEventBus(EventPublisher, EventStream):
    """单进程内存事件总线（零基础设施验证用，LSP 可替换 Redis 版）。"""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[TaskEvent]]] = {}

    async def publish(self, event: TaskEvent) -> None:
        for queue in self._subscribers.get(event.job_id, []):
            await queue.put(event)

    async def subscribe(self, job_id: str) -> AsyncIterator[TaskEvent]:
        queue: asyncio.Queue[TaskEvent] = asyncio.Queue()
        self._subscribers.setdefault(job_id, []).append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
                if event.type in _TERMINAL:
                    break
        finally:
            self._subscribers[job_id].remove(queue)
