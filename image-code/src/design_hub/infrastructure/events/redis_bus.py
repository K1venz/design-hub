import json
from collections.abc import AsyncIterator
from typing import Any

from redis.asyncio import Redis, from_url

from design_hub.domain.enums import TaskEventType
from design_hub.domain.models import TaskEvent
from design_hub.ports.events import EventPublisher, EventStream

_TERMINAL = {TaskEventType.TASK_COMPLETED, TaskEventType.TASK_FAILED}
_STREAM_TTL = 3600  # 秒：任务完成后流自动过期清理
_BLOCK_MS = 30000  # XREAD 阻塞窗口；超时无新事件则继续等（客户端断开会取消生成器）


def _stream(job_id: str) -> str:
    return f"job:events:{job_id}"


class RedisEventBus(EventPublisher, EventStream):
    """Redis Stream 事件总线：worker XADD 发布、SSE XREAD 订阅，跨进程桥接（PRD §6.3.1）。

    用 Stream 而非 Pub/Sub：事件持久化可回放——晚订阅/重连客户端从 "0" 读到该 job
    自始至终的全部事件，不丢 task_started（修 ISSUE-0010 pub/sub 竞态丢事件）。
    """

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
        stream = _stream(event.job_id)
        await self._redis.xadd(stream, {"payload": payload})
        await self._redis.expire(stream, _STREAM_TTL)

    async def subscribe(self, job_id: str) -> AsyncIterator[TaskEvent]:
        stream = _stream(job_id)
        last_id = "0"  # 从头回放：先补发历史，再 block 等后续新事件
        while True:
            result: Any = await self._redis.xread({stream: last_id}, block=_BLOCK_MS)
            if not result:
                continue  # block 超时无新事件，继续等
            for _key, entries in result:
                for entry_id, fields in entries:
                    last_id = entry_id
                    raw: dict[str, Any] = json.loads(fields["payload"])
                    event = TaskEvent(
                        job_id=raw["job_id"],
                        type=TaskEventType(raw["type"]),
                        data=raw["data"],
                    )
                    yield event
                    if event.type in _TERMINAL:
                        return

    async def aclose(self) -> None:
        await self._redis.aclose()
