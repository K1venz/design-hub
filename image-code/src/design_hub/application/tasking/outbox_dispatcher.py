import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from redis.exceptions import RedisError

from design_hub.domain.enums import TaskEventType
from design_hub.domain.errors import DataInvariantError
from design_hub.domain.models import TaskEvent
from design_hub.domain.tasking import TaskMessage
from design_hub.infrastructure.monitoring.task_metrics import task_metrics
from design_hub.ports.events import EventPublisher
from design_hub.ports.generation_work import GenerationWorkRepository
from design_hub.ports.task_broker import TaskBroker

_MAX_ERROR_LENGTH = 1000
logger = logging.getLogger(__name__)


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
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

    def __post_init__(self) -> None:
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive")

    async def dispatch_once(self) -> DispatchResult:
        stats = await self.repository.outbox_stats()
        oldest = stats.oldest_created_at
        if oldest is not None and oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=UTC)
        oldest_age = (
            max((datetime.now(UTC) - oldest).total_seconds(), 0)
            if oldest is not None
            else 0
        )
        task_metrics.set_outbox(
            pending=stats.pending,
            oldest_age_seconds=oldest_age,
        )
        records = await self.repository.fetch_outbox_batch(limit=self.batch_size)
        published = 0
        failed = 0
        for record in records:
            try:
                if record.aggregate_type == "generation_item":
                    fields = self._task_fields(record.payload)
                    message = TaskMessage.from_redis_fields(fields)
                    redis_id = await self.broker.publish(message)
                    log_context = {
                        "request_id": message.request_id,
                        "trace_id": message.trace_id,
                        "message_id": message.message_id,
                        "job_id": message.job_id,
                        "item_id": message.item_id,
                        "operation_id": message.operation_id,
                        "redis_id": redis_id,
                    }
                elif record.aggregate_type == "listing_job_event":
                    event = self._job_event(record.payload)
                    published_id = await self.events.publish(event)
                    if not isinstance(published_id, str) or not published_id:
                        raise DataInvariantError(
                            "durable event publisher did not return a Redis id"
                        )
                    redis_id = published_id
                    log_context = {
                        "job_id": event.job_id,
                        "redis_id": redis_id,
                    }
                else:
                    raise DataInvariantError(
                        f"unsupported outbox aggregate type: {record.aggregate_type}"
                    )
            except RedisError as exc:
                await self.repository.record_outbox_failure(
                    record.event_id, str(exc)[:_MAX_ERROR_LENGTH]
                )
                failed += 1
                exponent = min(record.publish_attempts, 4)
                await self.sleep(min(5.0, 0.5 * (2**exponent)))
                break
            await self.repository.mark_outbox_published(record.event_id, redis_id)
            logger.info("generation_outbox_published", extra=log_context)
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
