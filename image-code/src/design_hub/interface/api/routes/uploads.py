from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import Response

from design_hub.application.listing.upload_service import UploadService
from design_hub.interface.api.deps import CurrentUserDep, CurrentUserSseDep

router = APIRouter(prefix="/uploads", tags=["uploads"])


def _service(request: Request) -> UploadService:
    svc = request.app.state.upload_service
    assert isinstance(svc, UploadService)
    return svc


@router.post("")
async def upload_image(
    request: Request, _user: CurrentUserDep, file: UploadFile
) -> dict[str, str]:
    """上传产品图（Bearer）：校验大小/格式 → 返回 {id, url}（url 为后端预览代理路径）。"""
    data = await file.read()
    upload_id = await _service(request).save(data=data, content_type=file.content_type or "")
    return {"id": upload_id, "url": f"/uploads/{upload_id}"}


@router.get("/{upload_id}")
async def preview(
    upload_id: str, request: Request, _user: CurrentUserSseDep
) -> Response:
    # 预览经后端代理（不暴露 file://）；鉴权走 ?access_token= 以支持 <img src>（同 SSE，ISSUE-0011）
    data, content_type = await _service(request).load(upload_id)
    return Response(content=data, media_type=content_type)
