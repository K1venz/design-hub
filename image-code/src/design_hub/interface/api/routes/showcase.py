from fastapi import APIRouter

from design_hub.interface.api.deps import MediaSignerDep, ShowcaseServiceDep
from design_hub.interface.showcase_schemas import (
    ShowcaseDownloadOut,
    ShowcaseItemOut,
)

router = APIRouter(tags=["showcase"])


@router.get("/showcase", response_model=list[ShowcaseItemOut])
async def showcase(
    service: ShowcaseServiceDep,
    signer: MediaSignerDep,
) -> list[ShowcaseItemOut]:
    return [
        ShowcaseItemOut.of(item, signer)
        for item in await service.list_public()
    ]


@router.get(
    "/showcase/{image_id}/download",
    response_model=ShowcaseDownloadOut,
)
async def download_showcase_image(
    image_id: int,
    service: ShowcaseServiceDep,
    signer: MediaSignerDep,
) -> ShowcaseDownloadOut:
    key = await service.authorize_download(image_id)
    return ShowcaseDownloadOut(url=signer.generated_url(key))
