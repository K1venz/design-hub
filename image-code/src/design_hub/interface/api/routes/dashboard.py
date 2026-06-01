"""成本仪表盘路由（薄）：dim 分派到用例，period 时间窗。

GET /dashboard/cost?dim=overview|model|project|designer|tier&period=month|week|day
非法 dim/period 由 StrEnum 校验 → 422。
"""

from enum import StrEnum

from fastapi import APIRouter

from design_hub.application.dashboard.cost_report import Period
from design_hub.interface.api.dashboard_deps import CostReportServiceDep
from design_hub.interface.dashboard_schemas import (
    DesignerOut,
    ModelOut,
    OverviewOut,
    ProjectOut,
    TierOut,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class Dimension(StrEnum):
    OVERVIEW = "overview"
    MODEL = "model"
    PROJECT = "project"
    DESIGNER = "designer"
    TIER = "tier"


_CostReport = OverviewOut | list[ModelOut] | list[ProjectOut] | list[DesignerOut] | list[TierOut]


@router.get("/cost")
async def cost(
    svc: CostReportServiceDep,
    dim: Dimension = Dimension.OVERVIEW,
    period: Period = Period.MONTH,
) -> _CostReport:
    if dim is Dimension.OVERVIEW:
        return OverviewOut.of(await svc.overview(period))
    if dim is Dimension.MODEL:
        return [ModelOut.of(r) for r in await svc.by_model(period)]
    if dim is Dimension.PROJECT:
        return [ProjectOut.of(r) for r in await svc.by_project(period)]
    if dim is Dimension.DESIGNER:
        return [DesignerOut.of(r) for r in await svc.by_designer(period)]
    return [TierOut.of(r) for r in await svc.by_tier(period)]
