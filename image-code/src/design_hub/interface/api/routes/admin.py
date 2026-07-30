"""模型配置后台路由（薄，WP-H）。

GET /admin/models · PUT /admin/models/{name}（单价/启停热更，PRD §3.5）。
name 不存在 → NotFoundError → 404（边界映射）；单价为负 → ValueError → 400。
"""

from fastapi import APIRouter

from design_hub.interface.admin_schemas import (
    ModelConfigCreate,
    ModelConfigOut,
    ModelConfigUpdate,
)
from design_hub.interface.api.admin_deps import ModelConfigServiceDep
from design_hub.interface.api.deps import CurrentManagerDep

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/models", response_model=list[ModelConfigOut])
async def list_models(svc: ModelConfigServiceDep) -> list[ModelConfigOut]:
    return [ModelConfigOut.of(r) for r in await svc.list()]


@router.post("/models", response_model=ModelConfigOut)
async def create_model(
    body: ModelConfigCreate,
    manager: CurrentManagerDep,
    svc: ModelConfigServiceDep,
) -> ModelConfigOut:
    """新增模型配置（ISSUE-0057）。重名 → 409；单价负/空名 → 400。"""
    return ModelConfigOut.of(
        await svc.create(
            actor_id=int(manager.user_id),
            record=body.to_record(),
        )
    )


@router.put("/models/{name}", response_model=ModelConfigOut)
async def update_model(
    name: str,
    body: ModelConfigUpdate,
    manager: CurrentManagerDep,
    svc: ModelConfigServiceDep,
) -> ModelConfigOut:
    record = await svc.update(
        actor_id=int(manager.user_id), name=name,
        unit_cost=body.unit_cost, enabled=body.enabled, extra=body.extra,
        provider_type=body.provider_type, base_url=body.base_url,
        model=body.model, api_key_env=body.api_key_env,
    )
    return ModelConfigOut.of(record)


@router.put("/models/{name}/default", response_model=ModelConfigOut)
async def set_default_model(
    name: str,
    manager: CurrentManagerDep,
    svc: ModelConfigServiceDep,
) -> ModelConfigOut:
    """设为默认出图模型（备用渠道切换=改默认，ISSUE-0057/0056 单点结构性解）。name 缺 → 404。"""
    return ModelConfigOut.of(
        await svc.set_default(
            actor_id=int(manager.user_id),
            name=name,
        )
    )


@router.delete("/models/{name}")
async def delete_model(
    name: str,
    manager: CurrentManagerDep,
    svc: ModelConfigServiceDep,
) -> dict[str, bool]:
    """删模型配置（ISSUE-0057）。name 缺 → 404。"""
    await svc.delete(actor_id=int(manager.user_id), name=name)
    return {"ok": True}
