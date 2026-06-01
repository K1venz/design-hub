from typing import Annotated

from fastapi import Depends, Request

from design_hub.application.admin.model_config_service import ModelConfigService


def get_model_config_service(request: Request) -> ModelConfigService:
    svc = request.app.state.model_config_service
    assert isinstance(svc, ModelConfigService)
    return svc


ModelConfigServiceDep = Annotated[ModelConfigService, Depends(get_model_config_service)]
