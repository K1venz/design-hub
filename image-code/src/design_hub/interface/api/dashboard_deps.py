from typing import Annotated

from fastapi import Depends, Request

from design_hub.application.dashboard.cost_report import CostReportService


def get_cost_report_service(request: Request) -> CostReportService:
    svc = request.app.state.cost_report_service
    assert isinstance(svc, CostReportService)
    return svc


CostReportServiceDep = Annotated[CostReportService, Depends(get_cost_report_service)]
