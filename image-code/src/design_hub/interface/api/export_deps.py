from typing import Annotated

from fastapi import Depends, Request

from design_hub.application.export.export_service import ExportService


def get_export_service(request: Request) -> ExportService:
    svc = request.app.state.export_service
    assert isinstance(svc, ExportService)
    return svc


ExportServiceDep = Annotated[ExportService, Depends(get_export_service)]
