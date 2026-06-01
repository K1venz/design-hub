"""成本仪表盘用例（PRD §3.11，5 维报表）。

SRP：本用例只做"时间窗 + 业务衍生指标"——占比、单张均价、达标率、档位
70/25/5 目标对比。聚合 SQL 归 infrastructure（CostQueryPort），用例依赖抽象（DIP）。

达标率 = 评分 ≥ 4 星图数 / 已评分图数（PRD §1.2 首次可用率口径，未评分不入分母）。
成本均价/占比按张计。
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from design_hub.domain.enums import Tier
from design_hub.ports.cost_query import CostQueryPort

_CENT = Decimal("0.0001")

# 档位预设占比（PRD §3.11：草稿/标准/精修 = 70/25/5）
_TARGET_SHARE: dict[Tier, float] = {
    Tier.DRAFT: 0.70,
    Tier.STANDARD: 0.25,
    Tier.REFINE: 0.05,
}


class Period(StrEnum):
    MONTH = "month"
    WEEK = "week"
    DAY = "day"


def period_start(period: Period, now: datetime) -> datetime:
    """时间窗起点（含），naive UTC，与 ledger/ORM 的朴素 DATETIME 对齐。"""
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period is Period.DAY:
        return midnight
    if period is Period.WEEK:
        return midnight - timedelta(days=now.weekday())  # 本周一
    return midnight.replace(day=1)  # 本月一号


def _avg(total: Decimal, n: int) -> Decimal:
    return (total / n).quantize(_CENT) if n else Decimal("0").quantize(_CENT)


def _rate(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def _share(part: Decimal, whole: Decimal) -> float:
    return round(float(part / whole), 4) if whole else 0.0


@dataclass(frozen=True)
class OverviewReport:
    total_images: int
    total_cost: Decimal
    avg_cost: Decimal  # 单张均价
    usable_rate: float  # 达标率


@dataclass(frozen=True)
class ModelReport:
    model: str
    call_count: int  # 调用次数
    image_count: int
    cost: Decimal
    cost_share: float  # 成本占比
    avg_cost: Decimal  # 单张均价


@dataclass(frozen=True)
class ProjectReport:
    project_id: int | None
    cost: Decimal
    image_count: int
    designer_count: int
    per_capita: float  # 人均效率（张/人）


@dataclass(frozen=True)
class DesignerReport:
    user_id: str
    image_count: int  # 个人产能
    cost: Decimal  # 成本消耗
    usable: int
    scored: int
    usable_rate: float  # 达标率


@dataclass(frozen=True)
class TierReport:
    tier: str
    image_count: int
    actual_share: float  # 实际占比
    target_share: float  # 预设占比（70/25/5）


@dataclass
class CostReportService:
    """成本仪表盘用例（依赖 CostQueryPort，DIP）。"""

    query: CostQueryPort

    @staticmethod
    def _since(period: Period) -> datetime:
        return period_start(period, datetime.now(UTC).replace(tzinfo=None))

    async def overview(self, period: Period) -> OverviewReport:
        agg = await self.query.overview(self._since(period))
        return OverviewReport(
            total_images=agg.images,
            total_cost=agg.cost,
            avg_cost=_avg(agg.cost, agg.images),
            usable_rate=_rate(agg.usable, agg.scored),
        )

    async def by_model(self, period: Period) -> list[ModelReport]:
        aggs = await self.query.by_model(self._since(period))
        grand = sum((a.cost for a in aggs), Decimal("0"))
        return [
            ModelReport(
                model=a.model,
                call_count=a.jobs,
                image_count=a.images,
                cost=a.cost,
                cost_share=_share(a.cost, grand),
                avg_cost=_avg(a.cost, a.images),
            )
            for a in aggs
        ]

    async def by_project(self, period: Period) -> list[ProjectReport]:
        aggs = await self.query.by_project(self._since(period))
        return [
            ProjectReport(
                project_id=a.project_id,
                cost=a.cost,
                image_count=a.images,
                designer_count=a.designers,
                per_capita=round(a.images / a.designers, 2) if a.designers else 0.0,
            )
            for a in aggs
        ]

    async def by_designer(self, period: Period) -> list[DesignerReport]:
        aggs = await self.query.by_designer(self._since(period))
        return [
            DesignerReport(
                user_id=a.user_id,
                image_count=a.images,
                cost=a.cost,
                usable=a.usable,
                scored=a.scored,
                usable_rate=_rate(a.usable, a.scored),
            )
            for a in aggs
        ]

    async def by_tier(self, period: Period) -> list[TierReport]:
        aggs = await self.query.by_tier(self._since(period))
        total = sum(a.images for a in aggs)
        by_tier = {a.tier: a for a in aggs}
        # 始终输出全部三档（缺失档位补 0），方便前端与 70/25/5 对照
        return [
            TierReport(
                tier=tier.value,
                image_count=(by_tier[tier.value].images if tier.value in by_tier else 0),
                actual_share=_share(
                    Decimal(by_tier[tier.value].images if tier.value in by_tier else 0),
                    Decimal(total),
                ),
                target_share=_TARGET_SHARE[tier],
            )
            for tier in Tier
        ]
