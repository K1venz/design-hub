from typing import Annotated

from fastapi import Depends, Request

from design_hub.application.admin.admin_console_service import AdminConsoleService
from design_hub.application.admin.model_capability_service import (
    ModelCapabilityService,
)
from design_hub.application.admin.model_config_service import ModelConfigService
from design_hub.application.showcase.service import ShowcaseService


def get_model_config_service(request: Request) -> ModelConfigService:
    svc = request.app.state.model_config_service
    assert isinstance(svc, ModelConfigService)
    return svc


def get_admin_console_service(request: Request) -> AdminConsoleService:
    service = request.app.state.admin_console_service
    assert isinstance(service, AdminConsoleService)
    return service


def get_showcase_service(request: Request) -> ShowcaseService:
    service = request.app.state.showcase_service
    assert isinstance(service, ShowcaseService)
    return service


def get_model_capability_service(
    request: Request,
) -> ModelCapabilityService:
    service = request.app.state.model_capability_service
    assert isinstance(service, ModelCapabilityService)
    return service


ModelConfigServiceDep = Annotated[ModelConfigService, Depends(get_model_config_service)]
ModelCapabilityServiceDep = Annotated[
    ModelCapabilityService,
    Depends(get_model_capability_service),
]
AdminConsoleServiceDep = Annotated[
    AdminConsoleService,
    Depends(get_admin_console_service),
]
ShowcaseServiceDep = Annotated[ShowcaseService, Depends(get_showcase_service)]
