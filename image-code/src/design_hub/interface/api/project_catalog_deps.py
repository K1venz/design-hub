from typing import Annotated

from fastapi import Depends, Request

from design_hub.application.project.catalog_service import ProjectCatalogService


def get_project_catalog_service(request: Request) -> ProjectCatalogService:
    svc = request.app.state.project_catalog_service
    assert isinstance(svc, ProjectCatalogService)
    return svc


ProjectCatalogServiceDep = Annotated[
    ProjectCatalogService, Depends(get_project_catalog_service)
]
