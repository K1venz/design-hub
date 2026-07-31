from fastapi import APIRouter

from design_hub.interface.api.admin_deps import ModelConfigServiceDep
from design_hub.interface.api.deps import CurrentUserDep
from design_hub.interface.model_schemas import ImageModelCatalogItemOut

router = APIRouter(prefix="/models", tags=["models"])


@router.get("/image", response_model=list[ImageModelCatalogItemOut])
async def list_image_models(
    _user: CurrentUserDep,
    svc: ModelConfigServiceDep,
) -> list[ImageModelCatalogItemOut]:
    return [ImageModelCatalogItemOut.model_validate(item) for item in await svc.image_catalog()]
