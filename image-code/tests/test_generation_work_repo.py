import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from design_hub.domain.errors import DataInvariantError
from design_hub.infrastructure.db.base import Base
from design_hub.infrastructure.db.models import (
    CostLedgerEntry,
    GenerationItemRow,
    ListingJobRow,
    OutboxEventRow,
)
from design_hub.infrastructure.ledger.sqlalchemy_ledger import SqlAlchemyLedgerRepository


async def _database() -> tuple[
    async_sessionmaker[AsyncSession],
    object,
]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


def _job(*, job_id: str = "job-1", idempotency_key: str = "request-1") -> ListingJobRow:
    return ListingJobRow(
        id=job_id,
        user_id="user-1",
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
