# 注解延迟求值，根除方法名 `list` 遮蔽内置类型的隐患（ISSUE-0004，与端口同治）
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.domain.enums import AssetKind
from design_hub.domain.models import AssetRecord
from design_hub.infrastructure.db.models import Asset
from design_hub.ports.repositories import AssetRepository


def _to_record(row: Asset) -> AssetRecord:
    return AssetRecord(
        id=row.id,
        project_id=row.project_id,
        kind=AssetKind(row.kind),
        url=row.url,
    )


class SqlAlchemyAssetRepository(AssetRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create(self, *, project_id: int, kind: AssetKind, url: str) -> AssetRecord:
        async with self._session_factory() as session:
            row = Asset(project_id=project_id, kind=kind.value, url=url)
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _to_record(row)

    async def get_many(self, asset_ids: Sequence[int]) -> list[AssetRecord]:
        if not asset_ids:
            return []
        async with self._session_factory() as session:
            stmt = select(Asset).where(Asset.id.in_(asset_ids)).order_by(Asset.id)
            rows = (await session.execute(stmt)).scalars().all()
            return [_to_record(r) for r in rows]

    async def list(self, *, project_id: int) -> list[AssetRecord]:
        async with self._session_factory() as session:
            stmt = select(Asset).where(Asset.project_id == project_id).order_by(Asset.id)
            rows = (await session.execute(stmt)).scalars().all()
            return [_to_record(r) for r in rows]
