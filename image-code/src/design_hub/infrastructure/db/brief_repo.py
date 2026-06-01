from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.domain.models import BriefRecord
from design_hub.infrastructure.db.models import Brief
from design_hub.ports.repositories import BriefRepository


def _to_record(row: Brief) -> BriefRecord:
    return BriefRecord(
        id=row.id,
        project_id=row.project_id,
        material_types=tuple(row.material_types),
        sizes=tuple(row.sizes),
        styles=tuple(row.styles),
        resolution=row.resolution,
        bleed=row.bleed,
        copy_text=row.copy_text,
        taboo=row.taboo,
        delivery=dict(row.delivery),
    )


class SqlAlchemyBriefRepository(BriefRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def upsert(
        self,
        *,
        project_id: int,
        material_types: Sequence[str] = (),
        sizes: Sequence[str] = (),
        styles: Sequence[str] = (),
        resolution: str | None = None,
        bleed: str | None = None,
        copy_text: str | None = None,
        taboo: str | None = None,
        delivery: Mapping[str, Any] | None = None,
    ) -> BriefRecord:
        async with self._session_factory() as session:
            row = await self._existing(session, project_id)
            if row is None:
                row = Brief(project_id=project_id)
                session.add(row)
            row.material_types = list(material_types)
            row.sizes = list(sizes)
            row.styles = list(styles)
            row.resolution = resolution
            row.bleed = bleed
            row.copy_text = copy_text
            row.taboo = taboo
            row.delivery = dict(delivery) if delivery is not None else {}
            await session.commit()
            await session.refresh(row)
            return _to_record(row)

    async def get(self, project_id: int) -> BriefRecord | None:
        async with self._session_factory() as session:
            row = await self._existing(session, project_id)
            return _to_record(row) if row is not None else None

    @staticmethod
    async def _existing(session: AsyncSession, project_id: int) -> Brief | None:
        stmt = select(Brief).where(Brief.project_id == project_id).order_by(Brief.id)
        return (await session.execute(stmt)).scalars().first()
