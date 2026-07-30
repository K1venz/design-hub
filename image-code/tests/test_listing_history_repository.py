import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from design_hub.domain.models import ListingJobImage, ListingJobStart
from design_hub.infrastructure.db.base import Base
from design_hub.infrastructure.db.listing_history_repo import SqlAlchemyListingHistory
from design_hub.infrastructure.db.listing_query_repo import SqlAlchemyListingHistoryQuery
from design_hub.infrastructure.db.models import GenerationItemRow, ListingImageRow
from design_hub.interface.listing_history_schemas import ListingJobDetailOut
from design_hub.ports.media_url_signer import MediaUrlSigner


async def _repositories() -> tuple[
    SqlAlchemyListingHistory,
    SqlAlchemyListingHistoryQuery,
    async_sessionmaker[AsyncSession],
]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    return (
        SqlAlchemyListingHistory(sessions),
        SqlAlchemyListingHistoryQuery(sessions),
        sessions,
    )


def _job(job_id: str = "job-1", **values: object) -> ListingJobStart:
    fields: dict[str, object] = {
        "job_id": job_id,
        "user_id": "user-1",
        "prompt": "商品主图",
        "modifiers": {"platform": "抖音电商"},
        "ratio": "1:1",
        "size": "1024x1024",
        "n": 2,
        "upload_keys": ("user-1/product.png",),
    }
    fields.update(values)
    return ListingJobStart(**fields)  # type: ignore[arg-type]


def test_job_lifecycle_is_queryable_and_preserves_partial_failure() -> None:
    async def run() -> None:
        history, query, _sessions = await _repositories()
        await history.start(_job())
        running = await query.get_job(job_id="job-1", user_id="user-1")
        assert running is not None
        assert running.status == "生成中"
        assert running.images == ()
        assert await query.get_job(job_id="job-1", user_id="other") is None

        await history.add_images(
            "job-1",
            (
                ListingJobImage(
                    image_key="success.png",
                    seed=1,
                    cost=Decimal("0.05"),
                    status="成功",
                    image_type="白底",
                ),
                ListingJobImage(
                    image_key="",
                    seed=-1,
                    cost=Decimal("0"),
                    status="失败",
                    image_type="卖点",
                ),
            ),
        )
        await history.finalize(
            "job-1",
            status="部分完成",
            total_cost=Decimal("0.05"),
            error="卖点：provider_failed",
        )

        completed = await query.get_job(job_id="job-1", user_id="user-1")
        assert completed is not None
        assert completed.status == "部分完成"
        assert completed.completed_at is not None
        assert [image.status for image in completed.images] == ["成功", "失败"]
        summary = (await query.list_jobs(user_id="user-1", limit=10, offset=0))[0]
        assert summary.image_count == 1
        assert summary.first_image_key == "success.png"

    asyncio.run(run())


def test_repository_rejects_finalize_without_start() -> None:
    async def run() -> None:
        history, _query, _sessions = await _repositories()
        with pytest.raises(RuntimeError):
            await history.finalize(
                "missing",
                status="完成",
                total_cost=Decimal("0"),
                error=None,
            )

    asyncio.run(run())


def test_failed_image_sentinel_cannot_be_resolved_as_edit_source() -> None:
    async def run() -> None:
        history, query, _sessions = await _repositories()
        await history.start(_job("root", n=1))
        await history.add_images(
            "root",
            (
                ListingJobImage(
                    image_key="success.png",
                    seed=1,
                    cost=Decimal("0.05"),
                    status="成功",
                    image_type="白底",
                ),
                ListingJobImage(
                    image_key="",
                    seed=-1,
                    cost=Decimal("0"),
                    status="失败",
                    image_type="卖点",
                ),
            ),
        )
        await history.finalize(
            "root",
            status="部分完成",
            total_cost=Decimal("0.05"),
            error="卖点：provider_failed",
        )

        source = await query.resolve_generated_image_source(
            source_image_key="success.png",
            user_id="user-1",
        )
        assert source is not None
        assert source.parent_job_id == "root"
        assert await query.resolve_generated_image_source(
            source_image_key="",
            user_id="user-1",
        ) is None

    asyncio.run(run())


def test_history_derives_background_replace_label_from_generation_item() -> None:
    async def run() -> None:
        history, query, sessions = await _repositories()
        await history.start(
            _job(
                "background",
                n=1,
                input_roles=("product",),
            )
        )
        async with sessions.begin() as session:
            session.add(
                GenerationItemRow(
                    id="item-background",
                    job_id="background",
                    sequence=1,
                    image_type=None,
                    render_tier="standard",
                    operation_type="replace_background",
                    final_prompt="replace the background",
                    model="gpt-image-2",
                    ratio="1:1",
                    size="1024x1024",
                    quality=None,
                    seed=0,
                    reference_snapshot=[],
                    reserved_cost=Decimal("0.05"),
                    status="queued",
                    operation_id="operation-background",
                    attempt_count=0,
                )
            )

        summary = (
            await query.list_jobs(
                user_id="user-1",
                limit=10,
                offset=0,
            )
        )[0]
        detail = await query.get_job(
            job_id="background",
            user_id="user-1",
        )

        assert summary.operation_type == "replace_background"
        assert detail is not None
        assert detail.operation_type == "replace_background"

    asyncio.run(run())


class _Signer(MediaUrlSigner):
    def generated_url(self, key: str) -> str:
        return f"https://generated.example/{key}"

    def upload_url(self, key: str) -> str:
        return f"https://uploads.example/{key}"


def test_blocked_image_is_unavailable_in_history_and_source_resolution() -> None:
    async def run() -> None:
        history, query, sessions = await _repositories()
        await history.start(_job("blocked-job", n=1))
        await history.add_images(
            "blocked-job",
            (
                ListingJobImage(
                    image_key="blocked.png",
                    seed=1,
                    cost=Decimal("0.05"),
                    status="成功",
                    image_type="白底",
                ),
            ),
        )
        await history.finalize(
            "blocked-job",
            status="完成",
            total_cost=Decimal("0.05"),
            error=None,
        )
        async with sessions.begin() as session:
            await session.execute(
                update(ListingImageRow)
                .where(ListingImageRow.image_key == "blocked.png")
                .values(
                    moderation_status="blocked",
                    moderation_reason="illegal",
                    moderation_note="internal only",
                )
            )

        summary = (
            await query.list_jobs(
                user_id="user-1",
                limit=10,
                offset=0,
            )
        )[0]
        detail = await query.get_job(
            job_id="blocked-job",
            user_id="user-1",
        )
        source = await query.resolve_generated_image_source(
            source_image_key="blocked.png",
            user_id="user-1",
        )

        assert summary.first_image_key is None
        assert detail is not None
        assert detail.images[0].available is False
        output = ListingJobDetailOut.of(detail, _Signer())
        assert output.images[0].url is None
        assert output.images[0].available is False
        assert not hasattr(output.images[0], "moderation_reason")
        assert source is None

    asyncio.run(run())


def test_blocked_edit_source_no_longer_receives_preview_url() -> None:
    async def run() -> None:
        history, query, sessions = await _repositories()
        await history.start(_job("root", n=1))
        await history.add_images(
            "root",
            (
                ListingJobImage(
                    image_key="source.png",
                    seed=1,
                    cost=Decimal("0.05"),
                    status="成功",
                ),
            ),
        )
        await history.finalize(
            "root",
            status="完成",
            total_cost=Decimal("0.05"),
            error=None,
        )
        await history.start(
            _job(
                "edit",
                n=1,
                parent_job_id="root",
                source_image_key="source.png",
                edit_mode="delta",
            )
        )
        async with sessions.begin() as session:
            await session.execute(
                update(ListingImageRow)
                .where(
                    ListingImageRow.job_id == "root",
                    ListingImageRow.image_key == "source.png",
                )
                .values(moderation_status="blocked")
            )

        detail = await query.get_job(
            job_id="edit",
            user_id="user-1",
        )

        assert detail is not None
        assert detail.source_image_key == "source.png"
        assert detail.source_image_available is False
        assert ListingJobDetailOut.of(
            detail,
            _Signer(),
        ).source_image_url is None

    asyncio.run(run())
