from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from design_hub.infrastructure.db.models import ListingJobRow
from design_hub.ports.listing_query import (
    ListingHistoryQuery,
    ListingJobDetail,
    ListingJobImageView,
    ListingJobSummary,
)


class SqlAlchemyListingHistoryQuery(ListingHistoryQuery):
    """ListingHistory 读侧（ISSUE-0030）：按 user_id 隔离、时间倒序分页、详情含图+输入。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_jobs(
        self, *, user_id: str, limit: int, offset: int, q: str | None = None
    ) -> list[ListingJobSummary]:
        async with self._session_factory() as session:
            stmt = select(ListingJobRow).where(ListingJobRow.user_id == user_id)
            if q:
                like = f"%{q}%"  # 模糊匹配 prompt / platform（ISSUE-0032 搜索）
                stmt = stmt.where(
                    or_(ListingJobRow.prompt.ilike(like), ListingJobRow.platform.ilike(like))
                )
            stmt = (
                # created_at 秒级精度，加 id 次级保证全序、分页稳定（无跨页重/漏）
                stmt.order_by(desc(ListingJobRow.created_at), desc(ListingJobRow.id))
                .limit(limit)
                .offset(offset)
                .options(selectinload(ListingJobRow.images))
            )
            rows = list((await session.execute(stmt)).scalars().all())
        return [
            ListingJobSummary(
                job_id=r.id,
                status=r.status,
                platform=r.platform,
                ratio=r.ratio,
                n=r.n,
                total_cost=r.total_cost,
                created_at=r.created_at,
                first_image_key=(r.images[0].image_key if r.images else None),
                image_count=len(r.images),
            )
            for r in rows
        ]

    async def get_job(self, *, job_id: str, user_id: str) -> ListingJobDetail | None:
        async with self._session_factory() as session:
            stmt = (
                select(ListingJobRow)
                .where(ListingJobRow.id == job_id, ListingJobRow.user_id == user_id)
                .options(
                    selectinload(ListingJobRow.images), selectinload(ListingJobRow.inputs)
                )
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        inputs = sorted(row.inputs, key=lambda i: i.ord)
        return ListingJobDetail(
            job_id=row.id,
            prompt=row.prompt,
            modifiers={str(k): str(v) for k, v in row.modifiers.items()},
            platform=row.platform,
            ratio=row.ratio,
            size=row.size,
            n=row.n,
            status=row.status,
            total_cost=row.total_cost,
            error=row.error,
            created_at=row.created_at,
            completed_at=row.completed_at,
            images=tuple(
                ListingJobImageView(
                    image_key=im.image_key, seed=im.seed, cost=im.cost, status=im.status
                )
                for im in row.images
            ),
            input_keys=tuple(i.upload_key for i in inputs),
        )
