from typing import Annotated

from fastapi import Depends, Request

from design_hub.application.project.asset_service import AssetService
from design_hub.application.project.brief_service import BriefService
from design_hub.application.project.customer_service import CustomerService
from design_hub.application.project.project_generation_service import (
    ProjectGenerationService,
)
from design_hub.application.project.project_service import ProjectService


def get_customer_service(request: Request) -> CustomerService:
    svc = request.app.state.customer_service
    assert isinstance(svc, CustomerService)
    return svc


def get_project_service(request: Request) -> ProjectService:
    svc = request.app.state.project_service
    assert isinstance(svc, ProjectService)
    return svc


def get_brief_service(request: Request) -> BriefService:
    svc = request.app.state.brief_service
    assert isinstance(svc, BriefService)
    return svc


def get_asset_service(request: Request) -> AssetService:
    svc = request.app.state.asset_service
    assert isinstance(svc, AssetService)
    return svc


def get_project_generation_service(request: Request) -> ProjectGenerationService:
    svc = request.app.state.project_generation_service
    assert isinstance(svc, ProjectGenerationService)
    return svc


CustomerServiceDep = Annotated[CustomerService, Depends(get_customer_service)]
ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
BriefServiceDep = Annotated[BriefService, Depends(get_brief_service)]
AssetServiceDep = Annotated[AssetService, Depends(get_asset_service)]
ProjectGenerationServiceDep = Annotated[
    ProjectGenerationService, Depends(get_project_generation_service)
]
