"""模型配置后台路由（薄，WP-H）。

GET /admin/models · PUT /admin/models/{name}（单价/启停热更，PRD §3.5）。
name 不存在 → NotFoundError → 404（边界映射）；单价为负 → ValueError → 400。

TODO(WP-G)：本组端点仅管理者可访问（PRD §6.3.3）。待 WP-G 鉴权落地后，
加 `Depends(require_role("管理者"))` 依赖；当前先不实现鉴权（端点裸露）。
"""

from fastapi import APIRouter

from design_hub.interface.admin_schemas import (
    ModelConfigCreate,
    ModelConfigOut,
    ModelConfigUpdate,
)
from design_hub.interface.api.admin_deps import ModelConfigServiceDep

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/models", response_model=list[ModelConfigOut])
async def list_models(svc: ModelConfigServiceDep) -> list[ModelConfigOut]:
    return [ModelConfigOut.of(r) for r in await svc.list()]


@router.post("/models", response_model=ModelConfigOut)
async def create_model(body: ModelConfigCreate, svc: ModelConfigServiceDep) -> ModelConfigOut:
    """新增模型配置（ISSUE-0057）。重名 → 409；单价负/空名 → 400。"""
    return ModelConfigOut.of(await svc.create(body.to_record()))


@router.put("/models/{name}", response_model=ModelConfigOut)
async def update_model(
    name: str, body: ModelConfigUpdate, svc: ModelConfigServiceDep
) -> ModelConfigOut:
    record = await svc.update(
        name, unit_cost=body.unit_cost, enabled=body.enabled, extra=body.extra,
        provider_type=body.provider_type, base_url=body.base_url,
        model=body.model, api_key_env=body.api_key_env,
    )
    return ModelConfigOut.of(record)


@router.put("/models/{name}/default", response_model=ModelConfigOut)
async def set_default_model(name: str, svc: ModelConfigServiceDep) -> ModelConfigOut:
    """设为默认出图模型（备用渠道切换=改默认，ISSUE-0057/0056 单点结构性解）。name 缺 → 404。"""
    return ModelConfigOut.of(await svc.set_default(name))


@router.delete("/models/{name}")
async def delete_model(name: str, svc: ModelConfigServiceDep) -> dict[str, bool]:
    """删模型配置（ISSUE-0057）。name 缺 → 404。"""
    await svc.delete(name)
    return {"ok": True}
