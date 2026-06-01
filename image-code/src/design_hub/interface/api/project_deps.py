from typing import Annotated

from fastapi import Depends, Request

from design_hub.application.project.customer_service import CustomerService
from design_hub.application.project.project_service import ProjectService


def get_customer_service(request: Request) -> CustomerService:
    svc = request.app.state.customer_service
    assert isinstance(svc, CustomerService)
    return svc


def get_project_service(request: Request) -> ProjectService:
    svc = request.app.state.project_service
    assert isinstance(svc, ProjectService)
    return svc


CustomerServiceDep = Annotated[CustomerService, Depends(get_customer_service)]
ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
