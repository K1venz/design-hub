from fastapi import APIRouter

from design_hub.interface.api.deps import MediaSignerDep
from design_hub.interface.api.selection_deps import SelectionServiceDep
from design_hub.interface.selection_schemas import (
    ImageOut,
    KeepRequest,
    ScoreRequest,
    UsableRateOut,
)

# 薄控制器：HTTP↔用例 翻译，校验/业务在 SelectionService 内，错误经边界统一映射
router = APIRouter(prefix="/jobs", tags=["selection"])


@router.get("/{job_id}/images", response_model=list[ImageOut])
async def list_images(
    job_id: str, svc: SelectionServiceDep, signer: MediaSignerDep
) -> list[ImageOut]:
    return [ImageOut.of(i, signer) for i in await svc.list_images(job_id)]


@router.post("/{job_id}/images/{image_id}/score", response_model=ImageOut)
async def score_image(
    job_id: str,
    image_id: int,
    body: ScoreRequest,
    svc: SelectionServiceDep,
    signer: MediaSignerDep,
) -> ImageOut:
    # 分值非法→ValueError→400；任务/图不存在→NotFoundError→404
    return ImageOut.of(await svc.score(job_id, image_id, body.score), signer)


@router.post("/{job_id}/images/{image_id}/keep", response_model=ImageOut)
async def keep_image(
    job_id: str,
    image_id: int,
    body: KeepRequest,
    svc: SelectionServiceDep,
    signer: MediaSignerDep,
) -> ImageOut:
    return ImageOut.of(await svc.keep(job_id, image_id, kept=body.kept), signer)


@router.get("/{job_id}/usable-rate", response_model=UsableRateOut)
async def usable_rate(job_id: str, svc: SelectionServiceDep) -> UsableRateOut:
    return UsableRateOut.of(await svc.usable_rate(job_id))
