"""listing 出图请求 DTO（application 层命令契约）。

路由（interface）与 ChatOrchestrator（application）共用同一组 pydantic 请求模型，
经 ListingJobLauncher 走同一条校验链（#884⑤）。放 application 层使
orchestrator 可直接用它把 LLM tool args 解析出来（extra=forbid 等约束原样生效），
不违反依赖内指（interface→application→domain）。
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class ListingGenerateRequest(BaseModel):
    """listing 出图入参（两步流：图先经 POST /uploads，这里只带 upload_ids）。

    数量/范围/比例/下拉的具体边界在 launcher 同步 fail-fast 校验（统一 400），不靠 Pydantic 约束
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
    # 品类（PRD §3.12.11）：optional、默认 FOOD；选对应品类保真卡。未知品类 launcher fail-fast 400。
    category: str = "FOOD"


class CloneRequest(BaseModel):
    """爆款图复刻入参（PRD §3.13，POST /listing/clone）。

    双角色显式双字段（产品图==1 + 爆款参考图 1..2、合计 ≤3 自动满足）；喂图保序
    「产品前·参考后」=角色指认契约。统一要求 prompt **选填**（与单图/套图必填不同）。
    边界仍走 launcher fail-fast 统一 400（ISSUE-0024 口径）。
    """

    product_upload_ids: list[str]
    reference_upload_ids: list[str]
    clone_mode: str  # 参考风格 | 高度复刻（中文档位 key）
    ratio: str
    prompt: str = ""  # 统一复刻要求，选填（空=合法，模板+产品图已承载语义）
    modifiers: dict[str, str] = Field(default_factory=dict)
    category: str = "FOOD"


class EditRequest(BaseModel):
    """二次编辑入参（PRD §3.12.13/ISSUE-0040，POST /listing/edit）。

    生而 extra=forbid（E-⑥）：未知字段（含 overlay_texts/n/plan/category）→ 422。
    不收 category（R2：编辑组装无品类块、库无列，死参数不收）。
    prompt 必填走 schema 严校 422（E-⑤，#652/#654 拍定与 forbid 同层同码）；
    edit_mode/ratio 仍走 launcher fail-fast 400（域值校验，单一事实源在卡/映射表）。
    """

    model_config = ConfigDict(extra="forbid")

    source_image_key: str  # 唯一不透明 handle（listing 产出图 image_key；E-δ 案3）
    # 编辑指令（两档必填）：先 strip 再验长 → ""/"  " 都 422
    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    edit_mode: str = "delta"  # delta|full（默认微调，PM A.1；registry fail-fast→400）
    # 本轮叠加语境（R3 叠新）：effective = 父 modifiers | 本轮；落库与组装同用 effective
    modifiers: dict[str, str] = Field(default_factory=dict)
    # delta：必须缺省（继承父，显式传→400 矛盾输入）；full：None=继承父、显式=覆盖
    ratio: str | None = None
