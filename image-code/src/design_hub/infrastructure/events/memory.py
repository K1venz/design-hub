import asyncio
from collections.abc import AsyncIterator

from design_hub.domain.enums import TaskEventType
from design_hub.domain.models import TaskEvent
from design_hub.ports.events import EventPublisher, EventStream

_TERMINAL = {TaskEventType.TASK_COMPLETED, TaskEventType.TASK_FAILED}


class InMemoryEventBus(EventPublisher, EventStream):
    """单进程内存事件总线（零基础设施验证用，LSP 可替换 Redis 版）。

    与 Redis Stream 版一致：按 job 缓存历史，订阅时先回放再收实时，晚订阅不丢事件
    （与 ISSUE-0010 同口径）。
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[TaskEvent]]] = {}
        self._history: dict[str, list[TaskEvent]] = {}

    async def publish(self, event: TaskEvent) -> None:
        self._history.setdefault(event.job_id, []).append(event)
        for queue in self._subscribers.get(event.job_id, []):
            await queue.put(event)

    async def subscribe(self, job_id: str) -> AsyncIterator[TaskEvent]:
        queue: asyncio.Queue[TaskEvent] = asyncio.Queue()
        # 先注册队列再快照历史（其间无 await，原子）：避免回放与实时之间漏发/重发
        self._subscribers.setdefault(job_id, []).append(queue)
        history = list(self._history.get(job_id, []))
        try:
            for event in history:
                yield event
                if event.type in _TERMINAL:
                    return
            while True:
                event = await queue.get()
                yield event
                if event.type in _TERMINAL:
                    break
        finally:
            self._subscribers[job_id].remove(queue)
