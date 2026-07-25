from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import CursorResult, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.domain.models import ListingJobImage, ListingJobStart
from design_hub.infrastructure.db.models import (
    ListingImageRow,
    ListingJobInputRow,
    ListingJobRow,
)
from design_hub.ports.listing_history import ListingHistory

_IN_PROGRESS = "生成中"


class SqlAlchemyListingHistory(ListingHistory):
    """ListingHistory 的 DB 写实现（两阶段落库 ISSUE-0047）：入队建行 → 逐张增量 → 终态改状态。

    与海报流 JobRepository 彻底分开。每阶段独立事务（session-per-op），进行中行即刻可查。
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def start(self, job: ListingJobStart) -> None:
        async with self._session_factory() as session:
            row = ListingJobRow(
                id=job.job_id,
                user_id=job.user_id,
                prompt=job.prompt,
                modifiers=dict(job.modifiers),
                platform=job.modifiers.get("platform"),
                category=job.category,
                ratio=job.ratio,
                size=job.size,
                n=job.n,
                status=_IN_PROGRESS,
                total_cost=Decimal("0"),
                error=None,
                clone_mode=job.clone_mode,
                parent_job_id=job.parent_job_id,
                source_image_key=job.source_image_key,
                edit_mode=job.edit_mode,
                completed_at=None,
            )
            roles = job.input_roles or (None,) * len(job.upload_keys)
            row.inputs = [
                ListingJobInputRow(upload_key=key, role=role, ord=i)
                for i, (key, role) in enumerate(zip(job.upload_keys, roles, strict=True))
            ]
            session.add(row)
            await session.commit()

    async def add_images(self, job_id: str, images: tuple[ListingJobImage, ...]) -> None:
        if not images:
            return
        async with self._session_factory() as session:
            session.add_all(
                [
                    ListingImageRow(
                        job_id=job_id,
                        image_key=im.image_key,
                        seed=im.seed,
                        cost=im.cost,
                        status=im.status,
                        image_type=im.image_type,
                    )
                    for im in images
                ]
            )
            await session.commit()

    async def finalize(
        self, job_id: str, *, status: str, total_cost: Decimal, error: str | None
    ) -> None:
        async with self._session_factory() as session:
            row = await session.get(ListingJobRow, job_id)
            if row is None:
                # start 未建行即终态 = 契约破坏，fail-fast（不静默补建掩盖时序错误）
                raise RuntimeError(f"finalize 未找到 listing_job {job_id}（start 应已建行）")
            row.status = status
            row.total_cost = total_cost
            row.error = error
            row.completed_at = datetime.now(UTC)
            await session.commit()

    async def reap_stale(self, *, older_than: timedelta, error: str) -> int:
        cutoff = datetime.now(UTC) - older_than
        async with self._session_factory() as session:
            result = cast(
                "CursorResult[Any]",
                await session.execute(
                    update(ListingJobRow)
                    .where(
                        ListingJobRow.status == _IN_PROGRESS,
                        ListingJobRow.created_at < cutoff,
                    )
                    .values(status="失败", error=error, completed_at=datetime.now(UTC))
                ),
            )
            await session.commit()
            return result.rowcount
