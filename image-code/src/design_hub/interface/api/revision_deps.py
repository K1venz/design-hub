from typing import Annotated

from fastapi import Depends, Request

from design_hub.application.revision.revision_service import RevisionService


def get_revision_service(request: Request) -> RevisionService:
    svc = request.app.state.revision_service
    assert isinstance(svc, RevisionService)
    return svc


RevisionServiceDep = Annotated[RevisionService, Depends(get_revision_service)]
