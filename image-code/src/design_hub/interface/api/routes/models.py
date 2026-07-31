from fastapi import APIRouter

from design_hub.domain.enums import ModelType
from design_hub.interface.api.admin_deps import ModelConfigServiceDep
from design_hub.interface.api.deps import CurrentUserDep
from design_hub.interface.model_schemas import ModelCatalogItemOut

router = APIRouter(prefix="/models", tags=["models"])


@router.get("/image", response_model=list[ModelCatalogItemOut])
async def list_image_models(
    _user: CurrentUserDep,
    svc: ModelConfigServiceDep,
) -> list[ModelCatalogItemOut]:
    return [
        ModelCatalogItemOut.model_validate(item)
        for item in await svc.catalog(ModelType.IMAGE)
    ]


@router.get("/chat", response_model=list[ModelCatalogItemOut])
async def list_chat_models(
    _user: CurrentUserDep,
    svc: ModelConfigServiceDep,
) -> list[ModelCatalogItemOut]:
    return [
        ModelCatalogItemOut.model_validate(item)
        for item in await svc.catalog(ModelType.CHAT)
    ]
