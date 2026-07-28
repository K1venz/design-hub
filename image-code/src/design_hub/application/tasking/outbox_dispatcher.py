from dataclasses import dataclass

from redis.exceptions import RedisError

from design_hub.domain.tasking import TaskMessage
from design_hub.ports.generation_work import GenerationWorkRepository
from design_hub.ports.task_broker import TaskBroker

_MAX_ERROR_LENGTH = 1000


@dataclass(frozen=True)
class DispatchResult:
    published: int
    failed: int


@dataclass
class OutboxDispatcher:
    repository: GenerationWorkRepository
    broker: TaskBroker
    batch_size: int = 100

    def __post_init__(self) -> None:
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive")

    async def dispatch_once(self) -> DispatchResult:
        records = await self.repository.fetch_outbox_batch(limit=self.batch_size)
        published = 0
        failed = 0
        for record in records:
            message = TaskMessage.from_redis_fields(record.payload)
            try:
                redis_id = await self.broker.publish(message)
            except RedisError as exc:
                await self.repository.record_outbox_failure(
                    record.event_id, str(exc)[:_MAX_ERROR_LENGTH]
                )
                failed += 1
                continue
            await self.repository.mark_outbox_published(record.event_id, redis_id)
            published += 1
        return DispatchResult(published=published, failed=failed)
