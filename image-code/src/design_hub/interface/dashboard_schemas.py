"""成本仪表盘 HTTP 输出 schema（边界翻译：用例 DTO → 传输层）。"""

from decimal import Decimal

from pydantic import BaseModel

from design_hub.application.dashboard.cost_report import (
    DesignerReport,
    ModelReport,
    OverviewReport,
    ProjectReport,
    TierReport,
)


class OverviewOut(BaseModel):
    total_images: int
    total_cost: Decimal
    avg_cost: Decimal
    usable_rate: float

    @classmethod
    def of(cls, r: OverviewReport) -> "OverviewOut":
        return cls(
            total_images=r.total_images,
            total_cost=r.total_cost,
            avg_cost=r.avg_cost,
            usable_rate=r.usable_rate,
        )


class ModelOut(BaseModel):
    model: str
    call_count: int
    image_count: int
    cost: Decimal
    cost_share: float
    avg_cost: Decimal

    @classmethod
    def of(cls, r: ModelReport) -> "ModelOut":
        return cls(
            model=r.model,
            call_count=r.call_count,
            image_count=r.image_count,
            cost=r.cost,
            cost_share=r.cost_share,
            avg_cost=r.avg_cost,
        )


class ProjectOut(BaseModel):
    project_id: int | None
    cost: Decimal
    image_count: int
    designer_count: int
    per_capita: float

    @classmethod
    def of(cls, r: ProjectReport) -> "ProjectOut":
        return cls(
            project_id=r.project_id,
            cost=r.cost,
            image_count=r.image_count,
            designer_count=r.designer_count,
            per_capita=r.per_capita,
        )


class DesignerOut(BaseModel):
    user_id: str
    image_count: int
    cost: Decimal
    usable: int
    scored: int
    usable_rate: float

    @classmethod
    def of(cls, r: DesignerReport) -> "DesignerOut":
        return cls(
            user_id=r.user_id,
            image_count=r.image_count,
            cost=r.cost,
            usable=r.usable,
            scored=r.scored,
            usable_rate=r.usable_rate,
        )


class TierOut(BaseModel):
    tier: str
    image_count: int
    actual_share: float
    target_share: float

    @classmethod
    def of(cls, r: TierReport) -> "TierOut":
        return cls(
            tier=r.tier,
            image_count=r.image_count,
            actual_share=r.actual_share,
            target_share=r.target_share,
        )
