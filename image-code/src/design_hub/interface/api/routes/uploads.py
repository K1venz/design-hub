from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import Response

from design_hub.application.listing.upload_service import UploadService
from design_hub.domain.errors import NotFoundError
from design_hub.interface.api.deps import CurrentUserDep, CurrentUserSseDep
from design_hub.ports.upload_store import owns

router = APIRouter(prefix="/uploads", tags=["uploads"])


def _service(request: Request) -> UploadService:
    svc = request.app.state.upload_service
    assert isinstance(svc, UploadService)
    return svc


@router.post("")
async def upload_image(
    request: Request, user: CurrentUserDep, file: UploadFile
) -> dict[str, str]:
    """上传产品图（Bearer）：校验大小/格式 → 落本人命名空间 → 返回 {id, url}。"""
    data = await file.read()
    upload_id = await _service(request).save(
        data=data, content_type=file.content_type or "", user_id=user.user_id
    )
    return {"id": upload_id, "url": f"/uploads/{upload_id}"}


@router.get("/{upload_id:path}")
async def preview(
    upload_id: str, request: Request, user: CurrentUserSseDep
) -> Response:
    # 预览代理（不暴露 file://）；鉴权走 ?access_token= 支持 <img src>（ISSUE-0011）。
    # 仅本人可取（ISSUE-0032）：非本人命名空间 → 404，不泄露存在性。
    if not owns(upload_id, user.user_id):
        raise NotFoundError(f"上传图不存在：{upload_id}")
    data, content_type = await _service(request).load(upload_id)
    return Response(content=data, media_type=content_type)
