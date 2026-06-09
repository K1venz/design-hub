from typing import Annotated

from fastapi import Depends, Request

from design_hub.application.project.customer_service import CustomerService


def get_customer_service(request: Request) -> CustomerService:
    svc = request.app.state.customer_service
    assert isinstance(svc, CustomerService)
    return svc


CustomerServiceDep = Annotated[CustomerService, Depends(get_customer_service)]
