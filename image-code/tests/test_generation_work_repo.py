import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from design_hub.domain.enums import ModelName
from design_hub.domain.errors import BudgetExceeded, DataInvariantError
from design_hub.domain.models import ListingJobStart
from design_hub.domain.tasking import (
    GenerationItemSpec,
    OperationType,
    ReferenceSnapshot,
    ReferenceSource,
    RenderTier,
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
from design_hub.infrastructure.ledger.sqlalchemy_ledger import SqlAlchemyLedgerRepository
from design_hub.ports.generation_work import (
    IdempotencyConflict,
    JobSubmission,
)


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
                email="user@example.com",
                password_hash="hash",
                name="User",
                role="设计师",
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False), engine


def _job(*, job_id: str = "job-1", idempotency_key: str = "request-1") -> ListingJobRow:
    return ListingJobRow(
        id=job_id,
        user_id="1",
        idempotency_key=idempotency_key,
        request_fingerprint=f"fingerprint:{job_id}",
        prompt="red package",
        modifiers={},
        ratio="1:1",
        size="1024x1024",
        n=1,
        status="生成中",
        total_cost=Decimal("0"),
    )


def test_generation_item_and_outbox_snapshot_roundtrip() -> None:
    async def run() -> None:
        session_factory, engine = await _database()
        try:
            async with session_factory() as session:
                session.add(_job())
                session.add(
                    GenerationItemRow(
                        id="item-1",
                        job_id="job-1",
                        sequence=1,
                        image_type="白底",
                        render_tier="standard",
                        operation_type="generate_image",
                        final_prompt="faithful product on white",
                        model="gpt-image-2",
                        ratio="1:1",
                        size="1024x1024",
                        quality=None,
                        seed=0,
                        reference_snapshot=[
                            {
                                "source": "upload",
                                "object_key": "user-1/product.png",
                                "role": "product",
                                "order": 0,
                            }
                        ],
                        reserved_cost=Decimal("0.05"),
                        status="queued",
                        operation_id="operation-1",
                        worker_id=None,
                        provider=None,
                        provider_task_id=None,
                        lease_expires_at=None,
                        heartbeat_at=None,
                        attempt_count=0,
                        error_code=None,
                        error_detail=None,
                    )
                )
                session.add(
                    OutboxEventRow(
                        id="event-1",
                        aggregate_type="generation_item",
                        aggregate_id="item-1",
                        event_type="generation_item.queued",
                        payload={"message_id": "message-1", "item_id": "item-1"},
                        publish_attempts=0,
                    )
                )
                await session.commit()

            async with session_factory() as session:
                item = await session.get(GenerationItemRow, "item-1")
                outbox = await session.get(OutboxEventRow, "event-1")
                assert item is not None
                assert item.final_prompt == "faithful product on white"
                assert item.reference_snapshot[0]["object_key"] == "user-1/product.png"
                assert item.reserved_cost == Decimal("0.0500")
                assert outbox is not None
                assert outbox.payload == {"message_id": "message-1", "item_id": "item-1"}
                assert outbox.published_at is None
                assert outbox.redis_id is None
        finally:
            await engine.dispose()  # type: ignore[attr-defined]

    asyncio.run(run())


def test_job_sequence_operation_and_idempotency_constraints_are_unique() -> None:
    async def run() -> None:
        session_factory, engine = await _database()
        try:
            async with session_factory() as session:
                session.add_all([_job(), _job(job_id="job-2")])
                with pytest.raises(IntegrityError):
                    await session.commit()
                await session.rollback()

            async with session_factory() as session:
                session.add_all([_job(), _job(job_id="job-2", idempotency_key="request-2")])
                await session.commit()
                first = GenerationItemRow(
                    id="item-1",
                    job_id="job-1",
                    sequence=1,
                    image_type=None,
                    render_tier="standard",
                    operation_type="generate_image",
                    final_prompt="one",
                    model="gpt-image-2",
                    ratio="1:1",
                    size="1024x1024",
                    quality=None,
                    seed=0,
                    reference_snapshot=[],
                    reserved_cost=Decimal("0.05"),
                    status="waiting",
                    operation_id="operation-1",
                    attempt_count=0,
                )
                session.add(first)
                await session.commit()

                session.add(
                    GenerationItemRow(
                        id="item-2",
                        job_id="job-1",
                        sequence=1,
                        image_type=None,
                        render_tier="standard",
                        operation_type="generate_image",
                        final_prompt="two",
                        model="gpt-image-2",
                        ratio="1:1",
                        size="1024x1024",
                        quality=None,
                        seed=1,
                        reference_snapshot=[],
                        reserved_cost=Decimal("0.05"),
                        status="waiting",
                        operation_id="operation-2",
                        attempt_count=0,
                    )
                )
                with pytest.raises(IntegrityError):
                    await session.commit()
        finally:
            await engine.dispose()  # type: ignore[attr-defined]

    asyncio.run(run())


def test_ledger_operation_is_idempotent_but_mismatch_fails_fast() -> None:
    async def run() -> None:
        session_factory, engine = await _database()
        ledger = SqlAlchemyLedgerRepository(session_factory)
        try:
            await ledger.reserve("user-1", Decimal("0.05"), operation_id="reserve:item-1")
            await ledger.reserve("user-1", Decimal("0.05"), operation_id="reserve:item-1")
            async with session_factory() as session:
                count = await session.scalar(select(func.count()).select_from(CostLedgerEntry))
                assert count == 1

            with pytest.raises(DataInvariantError):
                await ledger.reserve(
                    "user-1", Decimal("0.06"), operation_id="reserve:item-1"
                )
            with pytest.raises(DataInvariantError):
                await ledger.reserve(
                    "user-2", Decimal("0.05"), operation_id="reserve:item-1"
                )
        finally:
            await engine.dispose()  # type: ignore[attr-defined]

    asyncio.run(run())


def test_ledger_rows_keep_operation_timestamp_and_amount() -> None:
    async def run() -> None:
        session_factory, engine = await _database()
        ledger = SqlAlchemyLedgerRepository(session_factory)
        try:
            await ledger.rollback("user-1", Decimal("0.05"), operation_id="refund:item-1")
            async with session_factory() as session:
                row = (await session.execute(select(CostLedgerEntry))).scalar_one()
                assert row.operation_id == "refund:item-1"
                assert row.amount == Decimal("-0.0500")
                assert isinstance(row.created_at, datetime)
                assert row.created_at.replace(tzinfo=UTC).tzinfo is UTC
        finally:
            await engine.dispose()  # type: ignore[attr-defined]

    asyncio.run(run())


def _submission(
    *,
    job_id: str = "job-submit-1",
    idempotency_key: str = "idem-1",
    request_fingerprint: str = "a" * 64,
    operation_ids: tuple[str, ...] = ("operation-1", "operation-2"),
) -> JobSubmission:
    job = ListingJobStart(
        job_id=job_id,
        user_id="1",
        prompt="red package",
        modifiers={},
        ratio="1:1",
        size="1024x1024",
        n=len(operation_ids),
        upload_keys=("user-1/product.png",),
    )
    references = (
        ReferenceSnapshot(
            source=ReferenceSource.UPLOAD,
            object_key="user-1/product.png",
            role="product",
            order=0,
        ),
    )
    items = tuple(
        GenerationItemSpec(
            item_id=f"item-{index}",
            operation_id=operation_id,
            sequence=index,
            image_type=None,
            operation_type=OperationType.GENERATE_IMAGE,
            render_tier=RenderTier.STANDARD,
            final_prompt=f"prompt {index}",
            model=ModelName.GPT_IMAGE_2,
            ratio="1:1",
            size=(1024, 1024),
            quality=None,
            seed=index - 1,
            references=references,
            reserved_cost=Decimal("0.05"),
        )
        for index, operation_id in enumerate(operation_ids, start=1)
    )
    return JobSubmission(
        job=job,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        items=items,
        trace_id="trace-1",
        request_id="request-1",
    )


def test_submit_atomically_creates_job_items_reserves_and_first_outbox() -> None:
    async def run() -> None:
        session_factory, engine = await _database()
        repo = SqlAlchemyGenerationWorkRepository(session_factory)
        try:
            result = await repo.submit(_submission())
            assert result.job_id == "job-submit-1"
            assert result.replayed is False
            async with session_factory() as session:
                items = (
                    await session.execute(
                        select(GenerationItemRow).order_by(GenerationItemRow.sequence)
                    )
                ).scalars().all()
                assert [item.status for item in items] == ["queued", "waiting"]
                assert [item.operation_id for item in items] == [
                    "operation-1",
                    "operation-2",
                ]
                reserves = (
                    await session.execute(
                        select(CostLedgerEntry).order_by(CostLedgerEntry.operation_id)
                    )
                ).scalars().all()
                assert [row.operation_id for row in reserves] == [
                    "reserve:operation-1",
                    "reserve:operation-2",
                ]
                outboxes = (await session.execute(select(OutboxEventRow))).scalars().all()
                assert len(outboxes) == 1
                assert outboxes[0].aggregate_id == "item-1"
                assert outboxes[0].payload["item_id"] == "item-1"
        finally:
            await engine.dispose()  # type: ignore[attr-defined]

    asyncio.run(run())


def test_submit_enforces_budget_before_creating_any_generation_rows() -> None:
    async def run() -> None:
        session_factory, engine = await _database()
        repo = SqlAlchemyGenerationWorkRepository(session_factory)
        try:
            async with session_factory() as session:
                session.add(
                    CostLedgerEntry(
                        operation_id="existing-monthly-spend",
                        user_id="1",
                        amount=Decimal("200"),
                    )
                )
                await session.commit()

            with pytest.raises(BudgetExceeded, match="用户本月配额"):
                await repo.submit(_submission())

            async with session_factory() as session:
                assert (
                    await session.scalar(
                        select(func.count()).select_from(ListingJobRow)
                    )
                    == 0
                )
                assert (
                    await session.scalar(
                        select(func.count()).select_from(GenerationItemRow)
                    )
                    == 0
                )
                assert (
                    await session.scalar(
                        select(func.count()).select_from(OutboxEventRow)
                    )
                    == 0
                )
                ledger_count = await session.scalar(
                    select(func.count()).select_from(CostLedgerEntry)
                )
                assert ledger_count == 1
        finally:
            await engine.dispose()  # type: ignore[attr-defined]

    asyncio.run(run())


def test_submit_replays_same_request_and_rejects_changed_fingerprint() -> None:
    async def run() -> None:
        session_factory, engine = await _database()
        repo = SqlAlchemyGenerationWorkRepository(session_factory)
        try:
            first = await repo.submit(_submission())
            replay = await repo.submit(_submission(job_id="job-submit-2"))
            assert replay.job_id == first.job_id
            assert replay.replayed is True
            with pytest.raises(IdempotencyConflict):
                await repo.submit(
                    _submission(
                        job_id="job-submit-3",
                        request_fingerprint="b" * 64,
                    )
                )
        finally:
            await engine.dispose()  # type: ignore[attr-defined]

    asyncio.run(run())


def test_submit_rolls_back_every_row_when_item_insert_fails() -> None:
    async def run() -> None:
        session_factory, engine = await _database()
        repo = SqlAlchemyGenerationWorkRepository(session_factory)
        try:
            with pytest.raises(IntegrityError):
                await repo.submit(
                    _submission(operation_ids=("duplicate", "duplicate"))
                )
            async with session_factory() as session:
                assert await session.scalar(select(func.count()).select_from(ListingJobRow)) == 0
                assert (
                    await session.scalar(select(func.count()).select_from(GenerationItemRow))
                    == 0
                )
                assert (
                    await session.scalar(select(func.count()).select_from(CostLedgerEntry))
                    == 0
                )
                assert await session.scalar(select(func.count()).select_from(OutboxEventRow)) == 0
        finally:
            await engine.dispose()  # type: ignore[attr-defined]

    asyncio.run(run())
