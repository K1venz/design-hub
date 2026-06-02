"""ProjectCatalogQuery 的 SQLAlchemy 实现（ISSUE-0012，纯读，不碰 schema）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.infrastructure.db.models import GeneratedImageRow, GenerationJobRow
from design_hub.ports.project_catalog import ProjectCatalogQuery, ProjectImage, ProjectJob


class SqlAlchemyProjectCatalogQuery(ProjectCatalogQuery):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def jobs(self, project_id: int, *, round_no: int | None = None) -> list[ProjectJob]:
        stmt = select(GenerationJobRow).where(GenerationJobRow.project_id == project_id)
        if round_no is not None:
            stmt = stmt.where(GenerationJobRow.round_no == round_no)
        stmt = stmt.order_by(GenerationJobRow.created_at.desc(), GenerationJobRow.id)
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [
            ProjectJob(
                job_id=r.id,
                round_no=r.round_no,
                subscene=r.subscene,
                family=r.family,
                tier=r.tier,
                category=r.category,
                used_model=r.used_model,
                candidate_count=r.candidate_count,
                total_cost=r.total_cost,
                status=r.status,
                created_at=r.created_at,
            )
            for r in rows
        ]

    async def images(
        self, project_id: int, *, round_no: int | None = None, kept: bool | None = None
    ) -> list[ProjectImage]:
        stmt = (
            select(
                GeneratedImageRow.id,
                GeneratedImageRow.job_id,
                GeneratedImageRow.url,
                GeneratedImageRow.seed,
                GeneratedImageRow.score,
                GeneratedImageRow.kept,
                GenerationJobRow.round_no,
                GenerationJobRow.subscene,
            )
            .join(GenerationJobRow, GeneratedImageRow.job_id == GenerationJobRow.id)
            .where(GenerationJobRow.project_id == project_id)
        )
        if round_no is not None:
            stmt = stmt.where(GenerationJobRow.round_no == round_no)
        if kept is not None:
            stmt = stmt.where(GeneratedImageRow.kept == kept)
        stmt = stmt.order_by(GeneratedImageRow.id)
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return [
            ProjectImage(
                image_id=int(r[0]),
                job_id=str(r[1]),
                url=str(r[2]),
                seed=int(r[3]),
                score=(int(r[4]) if r[4] is not None else None),
                kept=bool(r[5]),
                round_no=int(r[6]),
                subscene=str(r[7]),
            )
            for r in rows
        ]
