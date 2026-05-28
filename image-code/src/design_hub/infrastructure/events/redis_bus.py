import json
from collections.abc import AsyncIterator
from typing import Any

from redis.asyncio import Redis, from_url

from design_hub.domain.enums import TaskEventType
from design_hub.domain.models import TaskEvent
from design_hub.ports.events import EventPublisher, EventStream

_TERMINAL = {TaskEventType.TASK_COMPLETED, TaskEventType.TASK_FAILED}


def _channel(job_id: str) -> str:
    return f"job:events:{job_id}"


class RedisEventBus(EventPublisher, EventStream):
    """Redis Pub/Sub 事件总线：worker 发布、SSE 订阅，跨进程桥接（PRD §6.3.1）。"""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @classmethod
    def from_url(cls, url: str) -> "RedisEventBus":
        client: Redis = from_url(url, decode_responses=True)
        return cls(client)

    async def publish(self, event: TaskEvent) -> None:
        payload = json.dumps(
            {"job_id": event.job_id, "type": event.type.value, "data": event.data}
        )
        await self._redis.publish(_channel(event.job_id), payload)

    async def subscribe(self, job_id: str) -> AsyncIterator[TaskEvent]:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(_channel(job_id))
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                raw: dict[str, Any] = json.loads(message["data"])
                event = TaskEvent(
                    job_id=raw["job_id"],
                    type=TaskEventType(raw["type"]),
                    data=raw["data"],
                )
                yield event
                if event.type in _TERMINAL:
                    break
        finally:
            await pubsub.unsubscribe(_channel(job_id))
            await pubsub.aclose()

    async def aclose(self) -> None:
        await self._redis.aclose()
