from pydantic import BaseModel


class UploadResponse(BaseModel):
    """POST /uploads 响应：上传图 id + 预览代理 url（GET /uploads/{id}）。"""

    id: str
    url: str
