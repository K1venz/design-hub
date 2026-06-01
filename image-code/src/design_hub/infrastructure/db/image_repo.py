# 注解延迟求值：根除方法名遮蔽内置类型的隐患（参见 ISSUE-0004）
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.domain.errors import NotFoundError
from design_hub.domain.models import GeneratedImageRecord
from design_hub.infrastructure.db.models import GeneratedImageRow, GenerationJobRow
from design_hub.ports.image_repository import GeneratedImageRepository


def _to_record(row: GeneratedImageRow) -> GeneratedImageRecord:
    return GeneratedImageRecord(
        id=row.id,
        job_id=row.job_id,
        url=row.url,
        seed=row.seed,
        latency_ms=row.latency_ms,
        cost=row.cost,
        score=row.score,
        kept=row.kept,
    )


class SqlAlchemyGeneratedImageRepository(GeneratedImageRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def job_exists(self, job_id: str) -> bool:
        async with self._session_factory() as session:
            stmt = select(GenerationJobRow.id).where(GenerationJobRow.id == job_id).limit(1)
            return (await session.execute(stmt)).scalar_one_or_none() is not None

    async def list_by_job(self, job_id: str) -> list[GeneratedImageRecord]:
        async with self._session_factory() as session:
            stmt = (
                select(GeneratedImageRow)
                .where(GeneratedImageRow.job_id == job_id)
                .order_by(GeneratedImageRow.id)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [_to_record(r) for r in rows]

    async def get(self, image_id: int) -> GeneratedImageRecord | None:
        async with self._session_factory() as session:
            row = await session.get(GeneratedImageRow, image_id)
            return _to_record(row) if row is not None else None

    async def set_score(self, image_id: int, score: int) -> GeneratedImageRecord:
        async with self._session_factory() as session:
            row = await session.get(GeneratedImageRow, image_id)
            if row is None:
                raise NotFoundError(f"候选图 {image_id} 不存在")
            row.score = score
            await session.commit()
            await session.refresh(row)
            return _to_record(row)

    async def set_kept(self, image_id: int, *, kept: bool) -> GeneratedImageRecord:
        async with self._session_factory() as session:
            row = await session.get(GeneratedImageRow, image_id)
            if row is None:
                raise NotFoundError(f"候选图 {image_id} 不存在")
            row.kept = kept
            await session.commit()
            await session.refresh(row)
            return _to_record(row)
