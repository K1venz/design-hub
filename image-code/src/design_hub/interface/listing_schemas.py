from pydantic import BaseModel, Field


class ListingGenerateRequest(BaseModel):
    """listing 出图入参（两步流：图先经 POST /uploads，这里只带 upload_ids）。

    数量/范围/比例/下拉的具体边界在路由同步 fail-fast 校验（统一 400），不靠 Pydantic 约束
    （避免 422 与 spec 的 400 口径不一致，ISSUE-0024）。
    """

    upload_ids: list[str]
    prompt: str
    ratio: str
    n: int
    modifiers: dict[str, str] = Field(default_factory=dict)


class UploadResponse(BaseModel):
    """POST /uploads 响应：上传图 id + 预览代理 url（GET /uploads/{id}）。"""

    id: str
    url: str
