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
    # 品类（PRD §3.12.11）：optional、默认 FOOD；选对应品类保真卡。未知品类路由 fail-fast 400。
    category: str = "FOOD"


class UploadResponse(BaseModel):
    """POST /uploads 响应：上传图 id + 预览代理 url（GET /uploads/{id}）。"""

    id: str
    url: str
