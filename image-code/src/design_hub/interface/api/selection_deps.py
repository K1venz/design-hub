from typing import Annotated

from fastapi import Depends, Request

from design_hub.application.selection.selection_service import SelectionService


def get_selection_service(request: Request) -> SelectionService:
    svc = request.app.state.selection_service
    assert isinstance(svc, SelectionService)
    return svc


SelectionServiceDep = Annotated[SelectionService, Depends(get_selection_service)]
