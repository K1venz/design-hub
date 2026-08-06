"""Opt-in recovery tests against dedicated, migrated MySQL and Redis instances.

These tests flush the selected Redis database and create/delete rows in the
selected MySQL schema. Never point the variables at shared or production data.
"""

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import delete, update

from design_hub.application.tasking.outbox_dispatcher import OutboxDispatcher
from design_hub.application.tasking.worker import GenerationWorker
from design_hub.domain.enums import TaskEventType
from design_hub.domain.models import GeneratedImage, ListingJobStart, ReferenceImage
from design_hub.domain.tasking import (
    GenerationItemSpec,
    GenerationItemStatus,
    OperationType,
    RenderTier,
    TaskMessage,
)
from design_hub.infrastructure.db.generation_work_repo import (
    SqlAlchemyGenerationWorkRepository,
)
from design_hub.infrastructure.db.models import (
    AppUser,
    CostLedgerEntry,
    GenerationItemRow,
    ListingJobRow,
    OutboxEventRow,
)
from design_hub.infrastructure.db.session import create_engine, create_session_factory
from design_hub.infrastructure.queue.redis_streams import (
    RedisJobEventStream,
    RedisStreamClient,
    RedisTaskBroker,
)
from design_hub.ports.events import EventPublisher
from design_hub.ports.generation_work import GenerationWorkItem, JobSubmission
from design_hub.ports.provider_execution import ImmediateResult, ProviderRequest

_DB_URL = os.getenv("STAGE_A_TEST_DB_URL")
_REDIS_URL = os.getenv("STAGE_A_TEST_REDIS_URL")

pytestmark = pytest.mark.skipif(
    not (_DB_URL and _REDIS_URL),
    reason=(
        "set STAGE_A_TEST_DB_URL and STAGE_A_TEST_REDIS_URL to dedicated, "
        "migrated test services"
    ),
)


@dataclass(frozen=True)
class _Run:
    user_id: int
    job_id: str
    item_ids: tuple[str, ...]
    operation_ids: tuple[str, ...]
    idempotency_key: str


def _new_run(item_count: int) -> _Run:
    token = uuid4().hex
    return _Run(
        user_id=1_000_000_000 + uuid4().int % 1_000_000_000,
        job_id=token,
        item_ids=tuple(uuid4().hex for _ in range(item_count)),
        operation_ids=tuple(uuid4().hex for _ in range(item_count)),
        idempotency_key=f"it:{token}",
    )


def _submission(run: _Run, *, job_id: str | None = None) -> JobSubmission:
    items = tuple(
        GenerationItemSpec(
            item_id=item_id,
            operation_id=operation_id,
            sequence=index,
            image_type=None,
            operation_type=OperationType.GENERATE_IMAGE,
            render_tier=RenderTier.STANDARD,
            final_prompt=f"integration prompt {index}",
            model="gpt-image-2",
            ratio="1:1",
            size=(1024, 1024),
            quality=None,
            seed=index - 1,
            references=(),
            reserved_cost=Decimal("0.05"),
        )
        for index, (item_id, operation_id) in enumerate(
            zip(run.item_ids, run.operation_ids, strict=True),
            start=1,
        )
    )
    return JobSubmission(
        job=ListingJobStart(
            job_id=job_id or run.job_id,
            user_id=str(run.user_id),
            prompt="integration recovery",
            modifiers={},
            ratio="1:1",
            size="1024x1024",
            n=len(items),
            upload_keys=(),
        ),
        idempotency_key=run.idempotency_key,
        request_fingerprint="a" * 64,
        items=items,
        trace_id=f"trace:{run.job_id}",
        request_id=f"request:{run.job_id}",
    )


async def _seed_user(sessions, run: _Run) -> None:  # type: ignore[no-untyped-def]
    async with sessions() as session:
        session.add(
            AppUser(
                id=run.user_id,
                email=f"{run.job_id}@integration.invalid",
                password_hash="not-used",
                name="Stage A integration",
                role="设计师",
            )
        )
        await session.commit()


async def _cleanup(sessions, redis: Redis, run: _Run) -> None:  # type: ignore[type-arg]
    async with sessions() as session:
        await session.execute(
            delete(OutboxEventRow).where(
                OutboxEventRow.aggregate_id.in_((run.job_id, *run.item_ids))
            )
        )
        await session.execute(
            delete(CostLedgerEntry).where(
                CostLedgerEntry.user_id == str(run.user_id)
            )
        )
        await session.execute(
            delete(ListingJobRow).where(ListingJobRow.id == run.job_id)
        )
        await session.execute(delete(AppUser).where(AppUser.id == run.user_id))
        await session.commit()
    await redis.flushdb()


def _redis(url: str) -> Redis:  # type: ignore[type-arg]
    return Redis.from_url(url, decode_responses=True)


def _broker(redis: Redis) -> RedisTaskBroker:  # type: ignore[type-arg]
    return RedisTaskBroker(cast(RedisStreamClient, redis))


class _NeverExecutor:
    reference_mode = "bytes"

    async def submit(
        self, request: ProviderRequest, *, operation_id: str
    ) -> ImmediateResult:
        raise AssertionError("terminal duplicate must not call provider")

    async def resume(
        self, provider_task_id: str, request: ProviderRequest
    ) -> GeneratedImage:
        raise AssertionError("terminal duplicate must not resume provider")


class _ResumeExecutor(_NeverExecutor):
    def __init__(self, provider_task_id: str) -> None:
        self.provider_task_id = provider_task_id
        self.resumes = 0

    async def resume(
        self, provider_task_id: str, request: ProviderRequest
    ) -> GeneratedImage:
        assert provider_task_id == self.provider_task_id
        self.resumes += 1
        return GeneratedImage(
            image_key=f"{provider_task_id}.png",
            url=f"mock://{provider_task_id}.png",
            seed=0,
            latency_ms=5,
            cost=Decimal("0.05"),
        )


class _BlockingExecutor(_NeverExecutor):
    def __init__(self) -> None:
        self.gate = asyncio.Event()
        self.started = asyncio.Event()
        self.submits = 0

    async def submit(
        self, request: ProviderRequest, *, operation_id: str
    ) -> ImmediateResult:
        self.submits += 1
        self.started.set()
        await self.gate.wait()
        return ImmediateResult(
            GeneratedImage(
                image_key=f"{operation_id}.png",
                url=f"mock://{operation_id}.png",
                seed=0,
                latency_ms=50,
                cost=Decimal("0.05"),
            )
        )


class _NoReferences:
    async def materialize(
        self, work: GenerationWorkItem, reference_mode: str
    ) -> tuple[ReferenceImage, ...]:
        return ()


class _NoSlots:
    async def acquire(self, *, worker_id: str, item_id: str) -> bool:
        raise AssertionError("recovery must not acquire a new provider slot")

    async def release(self, *, worker_id: str, item_id: str) -> bool:
        return True

    async def refresh(self, *, worker_id: str, item_id: str) -> bool:
        return True


class _AvailableSlots(_NoSlots):
    async def acquire(self, *, worker_id: str, item_id: str) -> bool:
        return True


class _ExecutorResolver:
    def __init__(self, executor) -> None:  # type: ignore[no-untyped-def]
        self.executor = executor

    async def resolve(self, model_id: str, render_tier: RenderTier):  # type: ignore[no-untyped-def]
        return self.executor


class _FailFirstAck:
    def __init__(self, broker: RedisTaskBroker) -> None:
        self.broker = broker
        self.failed = False

    async def ack(self, redis_id: str) -> None:
        if not self.failed:
            self.failed = True
            raise RedisConnectionError("simulated connection loss before ACK")
        await self.broker.ack(redis_id)

    async def renew(self, *, consumer: str, redis_id: str) -> bool:
        return await self.broker.renew(consumer=consumer, redis_id=redis_id)


def _worker(
    *,
    repository: SqlAlchemyGenerationWorkRepository,
    broker,
    executor,
    worker_id: str,
    heartbeat_seconds: float = 15,
    slots=None,
) -> GenerationWorker:  # type: ignore[no-untyped-def]
    return GenerationWorker(
        repository=repository,
        broker=broker,
        executor_resolver=_ExecutorResolver(executor),
        materializer=_NoReferences(),
        slots_for=lambda _model, _tier: slots or _NoSlots(),
        worker_id=worker_id,
        lease_seconds=30,
        heartbeat_seconds=heartbeat_seconds,
    )


def _message(token: str) -> TaskMessage:
    return TaskMessage(
        schema_version=1,
        message_id=f"message:{token}",
        trace_id=f"trace:{token}",
        request_id=f"request:{token}",
        job_id=f"job:{token}",
        item_id=f"item:{token}",
        operation_id=f"operation:{token}",
        operation_type=OperationType.GENERATE_IMAGE,
        user_id="1",
        created_at=datetime.now(UTC),
    )


async def _pending_owner(redis: Redis, redis_id: str) -> str:  # type: ignore[type-arg]
    entries = await redis.xpending_range(
        "design-hub:generation:v1",
        "generation-workers-v1",
        min=redis_id,
        max=redis_id,
        count=1,
    )
    assert len(entries) == 1
    owner = entries[0]["consumer"]
    assert isinstance(owner, str)
    return owner


def test_delivery_renewal_preserves_current_redis_owner() -> None:
    async def run() -> None:
        assert _REDIS_URL is not None
        redis = _redis(_REDIS_URL)
        try:
            await redis.flushdb()
            broker = _broker(redis)
            await broker.ensure_group()
            await broker.publish(_message(uuid4().hex))
            (delivery,) = await broker.read(
                consumer="worker-a",
                count=1,
                block_ms=100,
            )

            await asyncio.sleep(0.05)
            assert await broker.renew(
                consumer="worker-a",
                redis_id=delivery.redis_id,
            )
            assert await broker.autoclaim(
                consumer="worker-b",
                min_idle_ms=25,
                count=1,
            ) == ()

            await asyncio.sleep(0.05)
            (recovered,) = await broker.autoclaim(
                consumer="worker-b",
                min_idle_ms=25,
                count=1,
            )
            assert recovered.redis_id == delivery.redis_id
            assert not await broker.renew(
                consumer="worker-a",
                redis_id=delivery.redis_id,
            )
            assert await _pending_owner(redis, delivery.redis_id) == "worker-b"
        finally:
            await redis.flushdb()
            await redis.aclose()

    asyncio.run(run())


def test_two_deliveries_renew_without_crossing_redis_ownership() -> None:
    async def run() -> None:
        assert _REDIS_URL is not None
        redis = _redis(_REDIS_URL)
        try:
            await redis.flushdb()
            broker = _broker(redis)
            await broker.ensure_group()
            await broker.publish(_message(uuid4().hex))
            (delivery_a,) = await broker.read(
                consumer="worker-a",
                count=1,
                block_ms=100,
            )
            await broker.publish(_message(uuid4().hex))
            (delivery_b,) = await broker.read(
                consumer="worker-b",
                count=1,
                block_ms=100,
            )

            assert await broker.renew(
                consumer="worker-a",
                redis_id=delivery_a.redis_id,
            )
            assert await broker.renew(
                consumer="worker-b",
                redis_id=delivery_b.redis_id,
            )
            assert not await broker.renew(
                consumer="worker-a",
                redis_id=delivery_b.redis_id,
            )
            assert await _pending_owner(redis, delivery_a.redis_id) == "worker-a"
            assert await _pending_owner(redis, delivery_b.redis_id) == "worker-b"
        finally:
            await redis.flushdb()
            await redis.aclose()

    asyncio.run(run())


def test_generation_longer_than_reclaim_window_calls_provider_once() -> None:
    async def run() -> None:
        assert _DB_URL is not None and _REDIS_URL is not None
        run_id = _new_run(1)
        engine = create_engine(_DB_URL)
        sessions = create_session_factory(engine)
        redis = _redis(_REDIS_URL)
        try:
            await redis.flushdb()
            await _seed_user(sessions, run_id)
            repository = SqlAlchemyGenerationWorkRepository(sessions)
            broker = _broker(redis)
            events = RedisJobEventStream(cast(RedisStreamClient, redis))
            await broker.ensure_group()
            await repository.submit(_submission(run_id))
            dispatcher = OutboxDispatcher(
                repository=repository,
                broker=broker,
                events=cast(EventPublisher, events),
            )
            await dispatcher.dispatch_once()
            (delivery,) = await broker.read(
                consumer="long-worker",
                count=1,
                block_ms=100,
            )
            executor = _BlockingExecutor()
            worker = _worker(
                repository=repository,
                broker=broker,
                executor=executor,
                worker_id="long-worker",
                heartbeat_seconds=0.01,
                slots=_AvailableSlots(),
            )

            process_task = asyncio.create_task(worker.process(delivery))
            await executor.started.wait()
            await asyncio.sleep(0.05)
            assert await broker.autoclaim(
                consumer="recovery-worker",
                min_idle_ms=25,
                count=1,
            ) == ()
            executor.gate.set()
            await process_task

            assert executor.submits == 1
        finally:
            await _cleanup(sessions, redis, run_id)
            await redis.aclose()
            await engine.dispose()

    asyncio.run(run())


def test_pending_survives_consumer_and_client_restart_then_cancels_once() -> None:
    async def run() -> None:
        assert _DB_URL is not None and _REDIS_URL is not None
        run_id = _new_run(2)
        engine = create_engine(_DB_URL)
        sessions = create_session_factory(engine)
        redis = _redis(_REDIS_URL)
        try:
            await redis.flushdb()
            await _seed_user(sessions, run_id)
            repository = SqlAlchemyGenerationWorkRepository(sessions)
            broker = _broker(redis)
            events = RedisJobEventStream(cast(RedisStreamClient, redis))
            await broker.ensure_group()
            await repository.submit(_submission(run_id))
            dispatcher = OutboxDispatcher(
                repository=repository,
                broker=broker,
                events=cast(EventPublisher, events),
            )
            assert (await dispatcher.dispatch_once()).published == 1
            (delivery,) = await broker.read(
                consumer="dead-consumer",
                count=1,
                block_ms=100,
            )

            replay = await SqlAlchemyGenerationWorkRepository(sessions).submit(
                _submission(run_id, job_id=uuid4().hex)
            )
            assert replay.replayed is True
            assert replay.job_id == run_id.job_id

            await redis.aclose()
            redis = _redis(_REDIS_URL)
            broker = _broker(redis)
            events = RedisJobEventStream(cast(RedisStreamClient, redis))
            (recovered,) = await broker.autoclaim(
                consumer="recovery-consumer",
                min_idle_ms=0,
                count=10,
            )
            assert recovered.redis_id == delivery.redis_id

            await repository.cancel_item(run_id.item_ids[0], str(run_id.user_id))
            await repository.cancel_item(run_id.item_ids[1], str(run_id.user_id))
            dispatcher = OutboxDispatcher(
                repository=repository,
                broker=broker,
                events=cast(EventPublisher, events),
            )
            await dispatcher.dispatch_once()

            terminal_worker = _worker(
                repository=repository,
                broker=broker,
                executor=_NeverExecutor(),
                worker_id="terminal-recovery",
            )
            await terminal_worker.process(recovered)
            queued = await broker.read(
                consumer="terminal-recovery",
                count=10,
                block_ms=100,
            )
            for queued_delivery in queued:
                await terminal_worker.process(queued_delivery)

            await broker.publish(recovered.message)
            duplicate = await broker.read(
                consumer="terminal-recovery",
                count=1,
                block_ms=100,
            )
            await terminal_worker.process(duplicate[0])

            await dispatcher.dispatch_once()
            replayed_events = await RedisJobEventStream(
                cast(RedisStreamClient, redis)
            ).read(job_id=run_id.job_id, after_id="0-0", block_ms=100)
            event_types = [entry.event.type for entry in replayed_events]
            assert event_types.count(TaskEventType.IMAGE_FAILED) == 2
            assert event_types.count(TaskEventType.TASK_FAILED) == 1
        finally:
            await _cleanup(sessions, redis, run_id)
            await redis.aclose()
            await engine.dispose()

    asyncio.run(run())


def test_async_provider_resume_and_commit_before_ack_are_recoverable() -> None:
    async def run() -> None:
        assert _DB_URL is not None and _REDIS_URL is not None
        run_id = _new_run(1)
        engine = create_engine(_DB_URL)
        sessions = create_session_factory(engine)
        redis = _redis(_REDIS_URL)
        try:
            await redis.flushdb()
            await _seed_user(sessions, run_id)
            repository = SqlAlchemyGenerationWorkRepository(sessions)
            broker = _broker(redis)
            events = RedisJobEventStream(cast(RedisStreamClient, redis))
            await broker.ensure_group()
            await repository.submit(_submission(run_id))
            dispatcher = OutboxDispatcher(
                repository=repository,
                broker=broker,
                events=cast(EventPublisher, events),
            )
            await dispatcher.dispatch_once()
            (delivery,) = await broker.read(
                consumer="dead-worker",
                count=1,
                block_ms=100,
            )
            await repository.claim(run_id.item_ids[0], "dead-worker", 30)
            await repository.mark_submitting(run_id.item_ids[0], "dead-worker")
            provider_task_id = f"provider:{run_id.item_ids[0]}"
            await repository.mark_submitted(
                run_id.item_ids[0],
                "dead-worker",
                provider_task_id,
            )
            async with sessions() as session:
                await session.execute(
                    update(GenerationItemRow)
                    .where(GenerationItemRow.id == run_id.item_ids[0])
                    .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
                )
                await session.commit()

            await redis.aclose()
            redis = _redis(_REDIS_URL)
            broker = _broker(redis)
            events = RedisJobEventStream(cast(RedisStreamClient, redis))
            dispatcher = OutboxDispatcher(
                repository=repository,
                broker=broker,
                events=cast(EventPublisher, events),
            )
            (recovered,) = await broker.autoclaim(
                consumer="resume-worker",
                min_idle_ms=0,
                count=1,
            )
            executor = _ResumeExecutor(provider_task_id)
            first_worker = _worker(
                repository=repository,
                broker=_FailFirstAck(broker),
                executor=executor,
                worker_id="resume-worker",
            )
            with pytest.raises(RedisConnectionError):
                await first_worker.process(recovered)

            committed = await repository.load_item(run_id.item_ids[0])
            assert committed.status is GenerationItemStatus.GENERATED
            assert executor.resumes == 1

            redelivered = await broker.autoclaim(
                consumer="ack-recovery",
                min_idle_ms=0,
                count=1,
            )
            await _worker(
                repository=repository,
                broker=broker,
                executor=_NeverExecutor(),
                worker_id="ack-recovery",
            ).process(redelivered[0])

            await dispatcher.dispatch_once()
            job_events = await events.read(
                job_id=run_id.job_id,
                after_id="0-0",
                block_ms=100,
            )
            types = [entry.event.type for entry in job_events]
            assert TaskEventType.IMAGE_GENERATED in types
            assert types.count(TaskEventType.TASK_COMPLETED) == 1
            image_index = types.index(TaskEventType.IMAGE_GENERATED)
            terminal_index = types.index(TaskEventType.TASK_COMPLETED)
            assert image_index < terminal_index
            image_event = job_events[image_index].event
            assert image_event.data["item_id"]
            assert image_event.data["image_key"]
            assert "url" not in image_event.data
        finally:
            await _cleanup(sessions, redis, run_id)
            await redis.aclose()
            await engine.dispose()

    asyncio.run(run())
