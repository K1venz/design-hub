"""成本聚合查询端口（DIP）。

CQRS 读侧：把"按 5 维聚合成本/张数/评分"的能力抽象成端口，
infrastructure 提供 SQLAlchemy 实现，application 用例只依赖本抽象。

口径：以 generated_image 为事实表（每张图一行 cost/score），按 generation_job
的 used_model/project_id/user_id/tier 维度分组。端口只产出**原始聚合数**，
占比/均价/达标率等衍生指标由用例计算（SRP）。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class OverviewAgg:
    """全局聚合（不分维度）。"""

    images: int
    cost: Decimal
    usable: int  # 评分 ≥ 4 星的图数
    scored: int  # 已评分（score 非空）的图数


@dataclass(frozen=True)
class ModelAgg:
    model: str
    jobs: int  # 调用次数（distinct job）
    images: int
    cost: Decimal


@dataclass(frozen=True)
class ProjectAgg:
    project_id: int | None  # None = 未挂项目的出图
    images: int
    cost: Decimal
    designers: int  # distinct user_id


@dataclass(frozen=True)
class DesignerAgg:
    user_id: str
    images: int
    cost: Decimal
    usable: int
    scored: int


@dataclass(frozen=True)
class TierAgg:
    tier: str
    images: int
    cost: Decimal


class CostQueryPort(ABC):
    """成本聚合查询端口。`since` 为时间窗起点（含），由用例按 period 计算。"""

    @abstractmethod
    async def overview(self, since: datetime) -> OverviewAgg:
        ...

    @abstractmethod
    async def by_model(self, since: datetime) -> list[ModelAgg]:
        ...

    @abstractmethod
    async def by_project(self, since: datetime) -> list[ProjectAgg]:
        ...

    @abstractmethod
    async def by_designer(self, since: datetime) -> list[DesignerAgg]:
        ...

    @abstractmethod
    async def by_tier(self, since: datetime) -> list[TierAgg]:
        ...
