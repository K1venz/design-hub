from dataclasses import dataclass

from redis.exceptions import RedisError

from design_hub.domain.enums import TaskEventType
from design_hub.domain.errors import DataInvariantError
from design_hub.domain.models import TaskEvent
from design_hub.domain.tasking import TaskMessage
from design_hub.ports.events import EventPublisher
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
    events: EventPublisher
    batch_size: int = 100

    def __post_init__(self) -> None:
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive")

    async def dispatch_once(self) -> DispatchResult:
        records = await self.repository.fetch_outbox_batch(limit=self.batch_size)
        published = 0
        failed = 0
        for record in records:
            try:
                if record.aggregate_type == "generation_item":
                    fields = self._task_fields(record.payload)
                    message = TaskMessage.from_redis_fields(fields)
                    redis_id = await self.broker.publish(message)
                elif record.aggregate_type == "listing_job_event":
                    event = self._job_event(record.payload)
                    published_id = await self.events.publish(event)
                    if not isinstance(published_id, str) or not published_id:
                        raise DataInvariantError(
                            "durable event publisher did not return a Redis id"
                        )
                    redis_id = published_id
                else:
                    raise DataInvariantError(
                        f"unsupported outbox aggregate type: {record.aggregate_type}"
                    )
            except RedisError as exc:
                await self.repository.record_outbox_failure(
                    record.event_id, str(exc)[:_MAX_ERROR_LENGTH]
                )
                failed += 1
                continue
            await self.repository.mark_outbox_published(record.event_id, redis_id)
            published += 1
        return DispatchResult(published=published, failed=failed)

    @staticmethod
    def _task_fields(payload: object) -> dict[str, str]:
        if not isinstance(payload, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in payload.items()
        ):
            raise DataInvariantError("task outbox payload must contain string fields")
        return payload

    @staticmethod
    def _job_event(payload: object) -> TaskEvent:
        if not isinstance(payload, dict):
            raise DataInvariantError("job event outbox payload must be an object")
        job_id = payload.get("job_id")
        event_type = payload.get("event_type")
        data = payload.get("data")
        if (
            not isinstance(job_id, str)
            or not isinstance(event_type, str)
            or not isinstance(data, dict)
            or not all(isinstance(key, str) for key in data)
        ):
            raise DataInvariantError("job event outbox payload is invalid")
        try:
            parsed_type = TaskEventType(event_type)
        except ValueError as exc:
            raise DataInvariantError(
                f"unsupported task event type: {event_type}"
            ) from exc
        return TaskEvent(job_id=job_id, type=parsed_type, data=data)
