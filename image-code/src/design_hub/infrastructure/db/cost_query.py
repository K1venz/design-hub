"""CostQueryPort 的 SQLAlchemy 实现：5 维聚合查询（纯读，不碰 schema）。

事实表 generated_image ⋈ generation_job：
- 成本/张数：sum(image.cost) / count(image)
- 维度：job.used_model / project_id / user_id / tier
- 评分：usable = score≥4 计数，scored = score 非空计数（达标率分母）
时间窗：按 generated_image.created_at >= since 过滤。
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.infrastructure.db.models import GeneratedImageRow, GenerationJobRow
from design_hub.ports.cost_query import (
    CostQueryPort,
    DesignerAgg,
    ModelAgg,
    OverviewAgg,
    ProjectAgg,
    TierAgg,
)

_CENT = Decimal("0.0001")  # 与 Numeric(10, 4) 对齐


def _money(value: object) -> Decimal:
    # sqlite 的 sum 返回 float、MySQL 返回 Decimal，统一量化到 4 位
    return Decimal(str(value)).quantize(_CENT)


class SqlAlchemyCostQuery(CostQueryPort):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def overview(self, since: datetime) -> OverviewAgg:
        stmt = select(
            func.count(GeneratedImageRow.id),
            func.coalesce(func.sum(GeneratedImageRow.cost), 0),
            func.coalesce(func.sum(case((GeneratedImageRow.score >= 4, 1), else_=0)), 0),
            func.coalesce(
                func.sum(case((GeneratedImageRow.score.is_not(None), 1), else_=0)), 0
            ),
        ).where(GeneratedImageRow.created_at >= since)
        async with self._session_factory() as session:
            row = (await session.execute(stmt)).one()
        return OverviewAgg(
            images=int(row[0]), cost=_money(row[1]), usable=int(row[2]), scored=int(row[3])
        )

    async def by_model(self, since: datetime) -> list[ModelAgg]:
        stmt = (
            select(
                GenerationJobRow.used_model,
                func.count(func.distinct(GenerationJobRow.id)),
                func.count(GeneratedImageRow.id),
                func.coalesce(func.sum(GeneratedImageRow.cost), 0),
            )
            .select_from(GeneratedImageRow)
            .join(GenerationJobRow, GeneratedImageRow.job_id == GenerationJobRow.id)
            .where(GeneratedImageRow.created_at >= since)
            .group_by(GenerationJobRow.used_model)
            .order_by(GenerationJobRow.used_model)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return [
            ModelAgg(model=str(r[0]), jobs=int(r[1]), images=int(r[2]), cost=_money(r[3]))
            for r in rows
        ]

    async def by_project(self, since: datetime) -> list[ProjectAgg]:
        stmt = (
            select(
                GenerationJobRow.project_id,
                func.count(GeneratedImageRow.id),
                func.coalesce(func.sum(GeneratedImageRow.cost), 0),
                func.count(func.distinct(GenerationJobRow.user_id)),
            )
            .select_from(GeneratedImageRow)
            .join(GenerationJobRow, GeneratedImageRow.job_id == GenerationJobRow.id)
            .where(GeneratedImageRow.created_at >= since)
            .group_by(GenerationJobRow.project_id)
            .order_by(GenerationJobRow.project_id)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return [
            ProjectAgg(
                project_id=(int(r[0]) if r[0] is not None else None),
                images=int(r[1]),
                cost=_money(r[2]),
                designers=int(r[3]),
            )
            for r in rows
        ]

    async def by_designer(self, since: datetime) -> list[DesignerAgg]:
        stmt = (
            select(
                GenerationJobRow.user_id,
                func.count(GeneratedImageRow.id),
                func.coalesce(func.sum(GeneratedImageRow.cost), 0),
                func.coalesce(func.sum(case((GeneratedImageRow.score >= 4, 1), else_=0)), 0),
                func.coalesce(
                    func.sum(case((GeneratedImageRow.score.is_not(None), 1), else_=0)), 0
                ),
            )
            .select_from(GeneratedImageRow)
            .join(GenerationJobRow, GeneratedImageRow.job_id == GenerationJobRow.id)
            .where(GeneratedImageRow.created_at >= since)
            .group_by(GenerationJobRow.user_id)
            .order_by(GenerationJobRow.user_id)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return [
            DesignerAgg(
                user_id=str(r[0]),
                images=int(r[1]),
                cost=_money(r[2]),
                usable=int(r[3]),
                scored=int(r[4]),
            )
            for r in rows
        ]

    async def by_tier(self, since: datetime) -> list[TierAgg]:
        stmt = (
            select(
                GenerationJobRow.tier,
                func.count(GeneratedImageRow.id),
                func.coalesce(func.sum(GeneratedImageRow.cost), 0),
            )
            .select_from(GeneratedImageRow)
            .join(GenerationJobRow, GeneratedImageRow.job_id == GenerationJobRow.id)
            .where(GeneratedImageRow.created_at >= since)
            .group_by(GenerationJobRow.tier)
            .order_by(GenerationJobRow.tier)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return [TierAgg(tier=str(r[0]), images=int(r[1]), cost=_money(r[2])) for r in rows]
