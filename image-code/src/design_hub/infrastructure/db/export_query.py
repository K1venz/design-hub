"""ExportQuery 的 SQLAlchemy 实现（WP-E，纯读，不碰 schema）。

generated_image ⋈ generation_job 取命名/归档元数据。候选序号 = 同 job 内按
image.id 升序的序号（1-based），由第二次查询按 job 分组计算。
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.infrastructure.db.models import GeneratedImageRow, GenerationJobRow
from design_hub.ports.exporter import ExportItem, ExportQuery


class SqlAlchemyExportQuery(ExportQuery):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def _candidate_ranks(
        self, session: AsyncSession, job_ids: set[str]
    ) -> dict[int, int]:
        """{image_id: 候选序号}，按 job 分组、image.id 升序 1-based。"""
        if not job_ids:
            return {}
        rows = (
            await session.execute(
                select(GeneratedImageRow.id, GeneratedImageRow.job_id)
                .where(GeneratedImageRow.job_id.in_(job_ids))
                .order_by(GeneratedImageRow.job_id, GeneratedImageRow.id)
            )
        ).all()
        ranks: dict[int, int] = {}
        counter: dict[str, int] = {}
        for image_id, job_id in rows:
            counter[job_id] = counter.get(job_id, 0) + 1
            ranks[image_id] = counter[job_id]
        return ranks

    async def items(self, image_ids: Sequence[int]) -> list[ExportItem]:
        if not image_ids:
            return []
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(
                        GeneratedImageRow.id,
                        GeneratedImageRow.url,
                        GeneratedImageRow.job_id,
                        GenerationJobRow.project_id,
                        GenerationJobRow.customer,
                        GenerationJobRow.subscene,
                        GenerationJobRow.tier,
                        GenerationJobRow.round_no,
                    )
                    .join(GenerationJobRow, GeneratedImageRow.job_id == GenerationJobRow.id)
                    .where(GeneratedImageRow.id.in_(image_ids))
                )
            ).all()
            ranks = await self._candidate_ranks(session, {r[2] for r in rows})
        return [
            ExportItem(
                image_id=int(r[0]),
                source_url=str(r[1]),
                project_id=(int(r[3]) if r[3] is not None else None),
                customer=str(r[4]),
                subscene=str(r[5]),
                tier=str(r[6]),
                round_no=int(r[7]),
                candidate_no=ranks[int(r[0])],
            )
            for r in rows
        ]

    async def one(self, image_id: int) -> ExportItem | None:
        items = await self.items([image_id])
        return items[0] if items else None
