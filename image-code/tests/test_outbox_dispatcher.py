import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from design_hub.application.tasking.health import (
    AdmissionRejected,
    QueueAdmissionController,
    RedisHealthState,
    RedisUnavailable,
)
from design_hub.application.tasking.outbox_dispatcher import OutboxDispatcher
from design_hub.domain.tasking import OperationType, TaskMessage
from design_hub.ports.generation_work import OutboxRecord


def _message() -> TaskMessage:
    return TaskMessage(
        schema_version=1,
        message_id="message-1",
        trace_id="trace-1",
        request_id="request-1",
        job_id="job-1",
        item_id="item-1",
        operation_id="operation-1",
        operation_type=OperationType.GENERATE_IMAGE,
        user_id="1",
        created_at=datetime(2026, 7, 28, tzinfo=UTC),
    )


class _OutboxRepository:
    def __init__(self, records: tuple[OutboxRecord, ...]) -> None:
        self.records = records
        self.actions: list[tuple[str, str, str | None]] = []
        self.mark_error: Exception | None = None

    async def fetch_outbox_batch(self, *, limit: int) -> tuple[OutboxRecord, ...]:
        self.actions.append(("fetch", str(limit), None))
        return self.records

    async def mark_outbox_published(self, event_id: str, redis_id: str) -> None:
        self.actions.append(("mark", event_id, redis_id))
        if self.mark_error is not None:
            raise self.mark_error
        self.records = tuple(record for record in self.records if record.event_id != event_id)

    async def record_outbox_failure(self, event_id: str, error: str) -> None:
        self.actions.append(("failure", event_id, error))


class _Broker:
    def __init__(self) -> None:
        self.messages: list[TaskMessage] = []
        self.error: Exception | None = None

    async def publish(self, message: TaskMessage) -> str:
        self.messages.append(message)
        if self.error is not None:
            raise self.error
        return "20-0"


def _record() -> OutboxRecord:
    return OutboxRecord(
        event_id="event-1",
        payload=_message().to_redis_fields(),
        created_at=datetime(2026, 7, 28, tzinfo=UTC),
        publish_attempts=0,
    )


def test_dispatcher_publishes_before_marking_database_row() -> None:
    async def run() -> None:
        repository = _OutboxRepository((_record(),))
        broker = _Broker()
        dispatcher = OutboxDispatcher(repository=repository, broker=broker, batch_size=100)

        result = await dispatcher.dispatch_once()

        assert result.published == 1
        assert broker.messages == [_message()]
        assert repository.actions == [
            ("fetch", "100", None),
            ("mark", "event-1", "20-0"),
        ]

    asyncio.run(run())


def test_crash_after_publish_republishes_same_message_id() -> None:
    async def run() -> None:
        repository = _OutboxRepository((_record(),))
        broker = _Broker()
        repository.mark_error = RuntimeError("database disconnected")
        dispatcher = OutboxDispatcher(repository=repository, broker=broker, batch_size=10)

        with pytest.raises(RuntimeError, match="database disconnected"):
            await dispatcher.dispatch_once()
        repository.mark_error = None
        await dispatcher.dispatch_once()

        assert [message.message_id for message in broker.messages] == [
            "message-1",
            "message-1",
        ]

    asyncio.run(run())


def test_redis_failure_is_recorded_with_bounded_detail() -> None:
    async def run() -> None:
        repository = _OutboxRepository((_record(),))
        broker = _Broker()
        broker.error = RedisConnectionError("x" * 5000)
        dispatcher = OutboxDispatcher(repository=repository, broker=broker, batch_size=10)

        result = await dispatcher.dispatch_once()

        assert result.failed == 1
        action = repository.actions[-1]
        assert action[:2] == ("failure", "event-1")
        assert action[2] is not None and len(action[2]) == 1000

    asyncio.run(run())


def test_health_rejects_never_checked_unhealthy_and_stale_redis() -> None:
    health = RedisHealthState(stale_after_seconds=6)
    with pytest.raises(RedisUnavailable):
        health.require_available(now=10)
    health.mark_healthy(now=10)
    health.require_available(now=15)
    with pytest.raises(RedisUnavailable):
        health.require_available(now=17)
    health.mark_unhealthy("connection refused", now=18)
    with pytest.raises(RedisUnavailable, match="connection refused"):
        health.require_available(now=18)


@dataclass(frozen=True)
class _AdmissionCase:
    depth: int
    expected_state: str


@pytest.mark.parametrize(
    "case",
    [
        _AdmissionCase(depth=100, expected_state="normal"),
        _AdmissionCase(depth=300, expected_state="high_peak"),
        _AdmissionCase(depth=800, expected_state="confirmation_required"),
    ],
)
def test_admission_uses_wait_estimate(case: _AdmissionCase) -> None:
    controller = QueueAdmissionController(
        soft_wait_seconds=300,
        confirm_wait_seconds=900,
        hard_depth=2000,
    )
    result = controller.evaluate(
        queue_depth=case.depth,
        rolling_item_seconds=60,
        available_slots=50,
    )
    assert result.state == case.expected_state
    assert result.estimated_wait_seconds == case.depth * 60 // 50


def test_admission_rejects_hard_depth_and_invalid_capacity() -> None:
    controller = QueueAdmissionController(
        soft_wait_seconds=300,
        confirm_wait_seconds=900,
        hard_depth=2000,
    )
    with pytest.raises(AdmissionRejected):
        controller.evaluate(
            queue_depth=2000,
            rolling_item_seconds=60,
            available_slots=50,
        )
    with pytest.raises(ValueError):
        controller.evaluate(
            queue_depth=1,
            rolling_item_seconds=60,
            available_slots=0,
        )
