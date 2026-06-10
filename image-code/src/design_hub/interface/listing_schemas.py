from pydantic import BaseModel, Field


class ListingGenerateRequest(BaseModel):
    """listing 出图入参（两步流：图先经 POST /uploads，这里只带 upload_ids）。

    数量/范围/比例/下拉的具体边界在路由同步 fail-fast 校验（统一 400），不靠 Pydantic 约束
    （避免 422 与 spec 的 400 口径不一致，ISSUE-0024）。
    """

    upload_ids: list[str]
    prompt: str
    ratio: str
    # 单图流张数（与 plan 显式互斥：恰好带其一，PRD §3.12.14）
    n: int | None = None
    # 套图配比（图型→张数，中文 key 白底/场景/卖点；Σ 3..10），带 plan 走套图编排
    plan: dict[str, int] | None = None
    # 卖点图可选图上文案（≤2 条、每条 ≤12 字；仅 plan 含卖点时合法；verbatim 锁定压图）
    overlay_texts: list[str] | None = None
    modifiers: dict[str, str] = Field(default_factory=dict)
    # 品类（PRD §3.12.11）：optional、默认 FOOD；选对应品类保真卡。未知品类路由 fail-fast 400。
    category: str = "FOOD"


class CloneRequest(BaseModel):
    """爆款图复刻入参（PRD §3.13，POST /listing/clone）。

    双角色显式双字段（产品图==1 + 爆款参考图 1..2、合计 ≤3 自动满足）；喂图保序
    「产品前·参考后」=角色指认契约。统一要求 prompt **选填**（与单图/套图必填不同）。
    边界仍走路由 fail-fast 统一 400（ISSUE-0024 口径）。
    """

    product_upload_ids: list[str]
    reference_upload_ids: list[str]
    clone_mode: str  # 参考风格 | 高度复刻（中文档位 key）
    ratio: str
    prompt: str = ""  # 统一复刻要求，选填（空=合法，模板+产品图已承载语义）
    modifiers: dict[str, str] = Field(default_factory=dict)
    category: str = "FOOD"


class UploadResponse(BaseModel):
    """POST /uploads 响应：上传图 id + 预览代理 url（GET /uploads/{id}）。"""

    id: str
    url: str
