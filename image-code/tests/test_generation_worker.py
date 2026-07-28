import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from design_hub.application.tasking.worker import GenerationWorker
from design_hub.domain.enums import ModelName
from design_hub.domain.models import GeneratedImage, ListingJobStart, ReferenceImage
from design_hub.domain.tasking import (
    GenerationItemSpec,
    GenerationItemStatus,
    OperationType,
    ReferenceSnapshot,
    ReferenceSource,
    RenderTier,
    TaskMessage,
)
from design_hub.infrastructure.db.base import Base
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
from design_hub.ports.generation_work import (
    ConcurrentTaskMutation,
    GenerationWorkItem,
    JobSubmission,
)
from design_hub.ports.provider_execution import (
    ImmediateResult,
    ProviderRequest,
    SubmissionUncertain,
    SubmittedTask,
)
from design_hub.ports.task_broker import Delivery


def _spec() -> GenerationItemSpec:
    return GenerationItemSpec(
        item_id="item-1",
        operation_id="operation-1",
        sequence=1,
        image_type=None,
        operation_type=OperationType.GENERATE_IMAGE,
        render_tier=RenderTier.STANDARD,
        final_prompt="faithful product",
        model=ModelName.GPT_IMAGE_2,
        ratio="1:1",
        size=(1024, 1024),
        quality=None,
        seed=0,
        references=(),
        reserved_cost=Decimal("0.05"),
    )


def _work(status: GenerationItemStatus = GenerationItemStatus.QUEUED) -> GenerationWorkItem:
    return GenerationWorkItem(
        job_id="job-1",
        user_id="1",
        spec=_spec(),
        status=status,
        provider_task_id=None,
        worker_id=None,
    )


def _delivery() -> Delivery:
    message = TaskMessage(
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
    return Delivery(redis_id="10-0", message=message)


def _image() -> GeneratedImage:
    return GeneratedImage(
        image_key="result.png",
        url="mock://result.png",
        seed=0,
        latency_ms=10,
        cost=Decimal("0.05"),
    )


class _Repository:
    def __init__(self, work: GenerationWorkItem) -> None:
        self.work = work
        self.actions: list[str] = []

    async def load_item(self, item_id: str) -> GenerationWorkItem:
        self.actions.append("load")
        return self.work

    async def claim(self, item_id: str, worker_id: str, lease_seconds: int) -> None:
        self.actions.append("claim")
        status = self.work.status
        if status in {
            GenerationItemStatus.QUEUED,
            GenerationItemStatus.CLAIMED,
        }:
            status = GenerationItemStatus.CLAIMED
        self.work = replace(
            self.work,
            status=status,
            worker_id=worker_id,
        )

    async def mark_submitting(self, item_id: str, worker_id: str) -> None:
        self.actions.append("submitting")
        self.work = replace(self.work, status=GenerationItemStatus.SUBMITTING)

    async def mark_submitted(
        self, item_id: str, worker_id: str, provider_task_id: str
    ) -> None:
        self.actions.append("submitted")
        self.work = replace(
            self.work,
            status=GenerationItemStatus.SUBMITTED,
            provider_task_id=provider_task_id,
        )

    async def mark_processing(self, item_id: str, worker_id: str) -> None:
        self.actions.append("processing")
        self.work = replace(self.work, status=GenerationItemStatus.PROCESSING)

    async def mark_storing(self, item_id: str, worker_id: str) -> None:
        self.actions.append("storing")
        self.work = replace(self.work, status=GenerationItemStatus.STORING)

    async def complete_item(
        self, item_id: str, worker_id: str, image: GeneratedImage
    ) -> None:
        self.actions.append("complete")
        self.work = replace(self.work, status=GenerationItemStatus.GENERATED)

    async def fail_item(
        self, item_id: str, worker_id: str, error_code: str, error_detail: str
    ) -> None:
        self.actions.append(f"failed:{error_code}")
        self.work = replace(self.work, status=GenerationItemStatus.FAILED)

    async def mark_submission_uncertain(
        self, item_id: str, worker_id: str, error_detail: str
    ) -> None:
        self.actions.append("uncertain")
        self.work = replace(
            self.work,
            status=GenerationItemStatus.SUBMISSION_UNCERTAIN,
        )

    async def heartbeat(
        self, item_id: str, worker_id: str, lease_seconds: int
    ) -> None:
        self.actions.append("heartbeat")


class _Broker:
    def __init__(self, repository: _Repository) -> None:
        self.repository = repository
        self.acks: list[str] = []

    async def ack(self, redis_id: str) -> None:
        assert self.repository.work.status in {
            GenerationItemStatus.GENERATED,
            GenerationItemStatus.FAILED,
            GenerationItemStatus.SUBMISSION_UNCERTAIN,
            GenerationItemStatus.CANCELLED,
            GenerationItemStatus.TIMED_OUT,
        }
        self.acks.append(redis_id)


class _Executor:
    reference_mode = "bytes"

    def __init__(
        self,
        result: SubmittedTask | ImmediateResult | None = None,
        error: Exception | None = None,
        delay_seconds: float = 0,
    ) -> None:
        self.result = result or ImmediateResult(_image())
        self.error = error
        self.delay_seconds = delay_seconds
        self.submits = 0
        self.resumes = 0

    async def submit(
        self, request: ProviderRequest, *, operation_id: str
    ) -> SubmittedTask | ImmediateResult:
        self.submits += 1
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.error is not None:
            raise self.error
        return self.result

    async def resume(
        self, provider_task_id: str, request: ProviderRequest
    ) -> GeneratedImage:
        self.resumes += 1
        return _image()


class _Materializer:
    async def materialize(
        self, work: GenerationWorkItem, reference_mode: str
    ) -> tuple[ReferenceImage, ...]:
        return (ReferenceImage(data=b"product"),)


class _Slots:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def acquire(self, *, worker_id: str, item_id: str) -> bool:
        self.actions.append("acquire")
        return True

    async def release(self, *, worker_id: str, item_id: str) -> bool:
        self.actions.append("release")
        return True

    async def refresh(self, *, worker_id: str, item_id: str) -> bool:
        self.actions.append("refresh")
        return True


def _worker(
    repository: _Repository,
    executor: _Executor,
    *,
    heartbeat_seconds: float = 15,
    slot_refresh_seconds: float = 10,
) -> tuple[GenerationWorker, _Broker, _Slots]:
    broker = _Broker(repository)
    slots = _Slots()
    worker = GenerationWorker(
        repository=repository,
        broker=broker,
        executor_for=lambda _model: executor,
        materializer=_Materializer(),
        slots_for=lambda _model, _tier: slots,
        worker_id="worker-1",
        lease_seconds=30,
        heartbeat_seconds=heartbeat_seconds,
        slot_refresh_seconds=slot_refresh_seconds,
    )
    return worker, broker, slots


def test_immediate_result_commits_terminal_before_ack() -> None:
    async def run() -> None:
        repository = _Repository(_work())
        executor = _Executor()
        worker, broker, slots = _worker(repository, executor)

        await worker.process(_delivery())

        assert repository.actions == [
            "load",
            "claim",
            "submitting",
            "storing",
            "complete",
        ]
        assert broker.acks == ["10-0"]
        assert slots.actions == ["acquire", "release"]

    asyncio.run(run())


def test_submitted_task_is_persisted_then_resumed_without_second_submit() -> None:
    async def run() -> None:
        repository = _Repository(_work())
        executor = _Executor(result=SubmittedTask("provider-task-1"))
        worker, broker, _slots = _worker(repository, executor)

        await worker.process(_delivery())

        assert repository.actions == [
            "load",
            "claim",
            "submitting",
            "submitted",
            "processing",
            "storing",
            "complete",
        ]
        assert executor.submits == 1
        assert executor.resumes == 1
        assert broker.acks == ["10-0"]

    asyncio.run(run())


def test_duplicate_terminal_delivery_acks_without_provider_call() -> None:
    async def run() -> None:
        repository = _Repository(_work(GenerationItemStatus.GENERATED))
        executor = _Executor()
        worker, broker, slots = _worker(repository, executor)

        await worker.process(_delivery())

        assert repository.actions == ["load"]
        assert executor.submits == 0
        assert slots.actions == []
        assert broker.acks == ["10-0"]

    asyncio.run(run())


def test_ambiguous_sync_timeout_marks_uncertain_and_never_retries() -> None:
    async def run() -> None:
        repository = _Repository(_work())
        executor = _Executor(error=SubmissionUncertain("unknown"))
        worker, broker, _slots = _worker(repository, executor)

        await worker.process(_delivery())

        assert repository.actions == [
            "load",
            "claim",
            "submitting",
            "uncertain",
        ]
        assert executor.submits == 1
        assert broker.acks == ["10-0"]

    asyncio.run(run())


def test_stale_claim_is_taken_over_before_provider_submit() -> None:
    async def run() -> None:
        repository = _Repository(_work(GenerationItemStatus.CLAIMED))
        executor = _Executor()
        worker, broker, _slots = _worker(repository, executor)

        await worker.process(_delivery())

        assert repository.actions == [
            "load",
            "claim",
            "submitting",
            "storing",
            "complete",
        ]
        assert executor.submits == 1
        assert broker.acks == ["10-0"]

    asyncio.run(run())


def test_persisted_provider_task_resumes_without_resubmission() -> None:
    async def run() -> None:
        work = replace(
            _work(GenerationItemStatus.SUBMITTED),
            provider_task_id="provider-existing",
            worker_id="dead-worker",
        )
        repository = _Repository(work)
        executor = _Executor()
        worker, broker, slots = _worker(repository, executor)

        await worker.process(_delivery())

        assert repository.actions == [
            "load",
            "claim",
            "processing",
            "storing",
            "complete",
        ]
        assert executor.submits == 0
        assert executor.resumes == 1
        assert slots.actions == []
        assert broker.acks == ["10-0"]

    asyncio.run(run())


def test_long_provider_submit_refreshes_database_and_slot_leases() -> None:
    async def run() -> None:
        repository = _Repository(_work())
        executor = _Executor(delay_seconds=0.03)
        worker, broker, slots = _worker(
            repository,
            executor,
            heartbeat_seconds=0.005,
            slot_refresh_seconds=0.005,
        )

        await worker.process(_delivery())

        assert "heartbeat" in repository.actions
        assert "refresh" in slots.actions
        assert broker.acks == ["10-0"]

    asyncio.run(run())


async def _database() -> tuple[
    async_sessionmaker[AsyncSession],
    object,
]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(
            AppUser.__table__.insert().values(
                id=1,
                email="worker@example.com",
                password_hash="hash",
                name="Worker Test",
                role="设计师",
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False), engine


def _submission(item_count: int = 3) -> JobSubmission:
    references = (
        ReferenceSnapshot(
            source=ReferenceSource.UPLOAD,
            object_key="1/product.png",
            role="product",
            order=0,
        ),
    )
    items = tuple(
        GenerationItemSpec(
            item_id=f"item-{index}",
            operation_id=f"operation-{index}",
            sequence=index,
            image_type=None,
            operation_type=OperationType.GENERATE_IMAGE,
            render_tier=RenderTier.STANDARD,
            final_prompt=f"prompt {index}",
            model=ModelName.GPT_IMAGE_2,
            ratio="1:1",
            size=(1024, 1024),
            quality=None,
            seed=index,
            references=references,
            reserved_cost=Decimal("0.05"),
        )
        for index in range(1, item_count + 1)
    )
    return JobSubmission(
        job=ListingJobStart(
            job_id="job-worker",
            user_id="1",
            prompt="product",
            modifiers={},
            ratio="1:1",
            size="1024x1024",
            n=item_count,
            upload_keys=("1/product.png",),
        ),
        idempotency_key="worker-request",
        request_fingerprint="f" * 64,
        items=items,
        trace_id="trace-worker",
        request_id="request-worker",
    )


async def _to_submitted(
    repository: SqlAlchemyGenerationWorkRepository,
    item_id: str,
    worker_id: str,
) -> None:
    await repository.claim(item_id, worker_id, 30)
    await repository.mark_submitting(item_id, worker_id)
    await repository.mark_submitted(item_id, worker_id, f"provider-{item_id}")


async def _complete(
    repository: SqlAlchemyGenerationWorkRepository,
    item_id: str,
    worker_id: str,
    *,
    cost: Decimal,
) -> None:
    await repository.mark_processing(item_id, worker_id)
    await repository.mark_storing(item_id, worker_id)
    await repository.complete_item(
        item_id,
        worker_id,
        GeneratedImage(
            image_key=f"{item_id}.png",
            url=f"mock://{item_id}.png",
            seed=1,
            latency_ms=20,
            cost=cost,
        ),
    )


def test_repository_claim_is_cas_and_expired_lease_can_be_taken_over() -> None:
    async def run() -> None:
        session_factory, engine = await _database()
        repository = SqlAlchemyGenerationWorkRepository(session_factory)
        try:
            await repository.submit(_submission(1))
            await repository.claim("item-1", "worker-a", 30)
            with pytest.raises(ConcurrentTaskMutation):
                await repository.claim("item-1", "worker-b", 30)

            async with session_factory() as session:
                row = await session.get(GenerationItemRow, "item-1")
                assert row is not None
                row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
                await session.commit()

            await repository.claim("item-1", "worker-b", 30)
            work = await repository.load_item("item-1")
            assert work.worker_id == "worker-b"
            async with session_factory() as session:
                row = await session.get(GenerationItemRow, "item-1")
                assert row is not None
                assert row.attempt_count == 2
        finally:
            await engine.dispose()  # type: ignore[attr-defined]

    asyncio.run(run())


def test_repository_pipelines_two_items_and_releases_next_atomically() -> None:
    async def run() -> None:
        session_factory, engine = await _database()
        repository = SqlAlchemyGenerationWorkRepository(session_factory)
        try:
            await repository.submit(_submission())
            await _to_submitted(repository, "item-1", "worker-a")

            async with session_factory() as session:
                rows = (
                    await session.execute(
                        select(GenerationItemRow).order_by(GenerationItemRow.sequence)
                    )
                ).scalars().all()
                assert [row.status for row in rows] == [
                    "submitted",
                    "queued",
                    "waiting",
                ]

            await _to_submitted(repository, "item-2", "worker-b")
            async with session_factory() as session:
                third = await session.get(GenerationItemRow, "item-3")
                assert third is not None
                assert third.status == "waiting"

            await _complete(
                repository,
                "item-1",
                "worker-a",
                cost=Decimal("0.07"),
            )
            async with session_factory() as session:
                third = await session.get(GenerationItemRow, "item-3")
                assert third is not None
                assert third.status == "queued"
                events = (
                    await session.execute(
                        select(OutboxEventRow)
                        .where(
                            OutboxEventRow.aggregate_type == "generation_item"
                        )
                        .order_by(OutboxEventRow.created_at)
                    )
                ).scalars().all()
                assert [event.aggregate_id for event in events] == [
                    "item-1",
                    "item-2",
                    "item-3",
                ]
        finally:
            await engine.dispose()  # type: ignore[attr-defined]

    asyncio.run(run())


def test_cost_reconcile_refund_and_job_terminal_aggregation_are_idempotent() -> None:
    async def run() -> None:
        session_factory, engine = await _database()
        repository = SqlAlchemyGenerationWorkRepository(session_factory)
        try:
            await repository.submit(_submission(2))
            await _to_submitted(repository, "item-1", "worker-a")
            await _complete(
                repository,
                "item-1",
                "worker-a",
                cost=Decimal("0.07"),
            )

            await repository.claim("item-2", "worker-b", 30)
            await repository.mark_submitting("item-2", "worker-b")
            await repository.fail_item(
                "item-2",
                "worker-b",
                "provider_error",
                "safe summary",
            )

            async with session_factory() as session:
                ledger = (
                    await session.execute(
                        select(CostLedgerEntry).order_by(CostLedgerEntry.operation_id)
                    )
                ).scalars().all()
                amounts = {
                    row.operation_id: row.amount
                    for row in ledger
                }
                assert amounts["reconcile:item-1"] == Decimal("0.0200")
                assert amounts["refund:item-2"] == Decimal("-0.0500")
                assert len(amounts) == 4

                job = await session.get(ListingJobRow, "job-worker")
                assert job is not None
                assert job.status == "部分完成"
                assert job.total_cost == Decimal("0.0700")
                assert job.completed_at is not None

                job_events = (
                    await session.execute(
                        select(OutboxEventRow).where(
                            OutboxEventRow.aggregate_type
                            == "listing_job_event"
                        )
                    )
                ).scalars().all()
                terminal = [
                    event
                    for event in job_events
                    if event.payload["event_type"]
                    in {"task_completed", "task_failed"}
                ]
                assert len(terminal) == 1

            with pytest.raises(ConcurrentTaskMutation):
                await repository.fail_item(
                    "item-2",
                    "worker-b",
                    "provider_error",
                    "duplicate",
                )
        finally:
            await engine.dispose()  # type: ignore[attr-defined]

    asyncio.run(run())


def test_cancel_before_submission_refunds_and_finishes_job() -> None:
    async def run() -> None:
        session_factory, engine = await _database()
        repository = SqlAlchemyGenerationWorkRepository(session_factory)
        try:
            await repository.submit(_submission(1))
            await repository.cancel_item("item-1", "1")

            async with session_factory() as session:
                item = await session.get(GenerationItemRow, "item-1")
                job = await session.get(ListingJobRow, "job-worker")
                refund = await session.scalar(
                    select(CostLedgerEntry).where(
                        CostLedgerEntry.operation_id == "refund:item-1"
                    )
                )
                assert item is not None
                assert item.status == "cancelled"
                assert refund is not None
                assert refund.amount == Decimal("-0.0500")
                assert job is not None
                assert job.status == "失败"
                assert job.completed_at is not None
        finally:
            await engine.dispose()  # type: ignore[attr-defined]

    asyncio.run(run())
