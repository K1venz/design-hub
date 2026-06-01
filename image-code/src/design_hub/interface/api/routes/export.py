"""导出归档路由（薄，WP-E）。

POST /projects/{id}/export   多格式导出 + 批量改尺寸 + zip + 命名归档
POST /images/{image_id}/resize  单图改尺寸
图不存在→NotFoundError 404；参数非法/跨项目→ValueError 400（边界映射）。
"""

from fastapi import APIRouter

from design_hub.interface.api.export_deps import ExportServiceDep
from design_hub.interface.export_schemas import (
    ExportRequest,
    ExportResponse,
    ResizeRequest,
    ResizeResponse,
)

router = APIRouter(tags=["export"])


@router.post("/projects/{project_id}/export", response_model=ExportResponse)
async def export_project(
    project_id: int, body: ExportRequest, svc: ExportServiceDep
) -> ExportResponse:
    result = await svc.export(
        project_id=project_id,
        image_ids=body.image_ids,
        formats=body.formats,
        resize=((body.resize.w, body.resize.h) if body.resize is not None else None),
        zip=body.zip,
    )
    return ExportResponse.of(result)


@router.post("/images/{image_id}/resize", response_model=ResizeResponse)
async def resize_image(
    image_id: int, body: ResizeRequest, svc: ExportServiceDep
) -> ResizeResponse:
    url = await svc.resize_image(image_id=image_id, width=body.w, height=body.h, fmt=body.format)
    return ResizeResponse(url=url)
