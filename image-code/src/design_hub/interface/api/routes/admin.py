from fastapi import APIRouter

from design_hub.domain.enums import ModelType
from design_hub.interface.admin_schemas import (
    ModelCapabilityTestIn,
    ModelCapabilityTestOut,
    ModelConfigCreate,
    ModelConfigOut,
    ModelConfigUpdate,
)
from design_hub.interface.api.admin_deps import (
    ModelCapabilityServiceDep,
    ModelConfigServiceDep,
)
from design_hub.interface.api.deps import CurrentManagerDep

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/models", response_model=list[ModelConfigOut])
async def list_models(svc: ModelConfigServiceDep) -> list[ModelConfigOut]:
    defaults = {
        model_type: await svc.default_name(model_type)
        for model_type in ModelType
    }
    return [
        ModelConfigOut.of(
            record,
            is_default=record.name == defaults[record.model_type],
        )
        for record in await svc.list()
    ]


@router.post("/models", response_model=ModelConfigOut)
async def create_model(
    body: ModelConfigCreate,
    manager: CurrentManagerDep,
    svc: ModelConfigServiceDep,
) -> ModelConfigOut:
    return ModelConfigOut.of(await svc.create(actor_id=int(manager.user_id), **body.model_dump()))


@router.post("/models/test", response_model=ModelCapabilityTestOut)
async def test_model_capability(
    body: ModelCapabilityTestIn,
    manager: CurrentManagerDep,
    svc: ModelCapabilityServiceDep,
) -> ModelCapabilityTestOut:
    result = await svc.test(
        manager_id=manager.user_id,
        **body.model_dump(),
    )
    return ModelCapabilityTestOut(
        verification_proof=result.verification_proof,
        tested_at=result.tested_at,
        checks=list(result.checks),
    )


@router.put("/models/{name}", response_model=ModelConfigOut)
async def update_model(
    name: str,
    body: ModelConfigUpdate,
    manager: CurrentManagerDep,
    svc: ModelConfigServiceDep,
) -> ModelConfigOut:
    return ModelConfigOut.of(
        await svc.update(actor_id=int(manager.user_id), name=name, **body.model_dump())
    )


@router.put("/models/{name}/default", response_model=ModelConfigOut)
async def set_default_model(
    name: str,
    manager: CurrentManagerDep,
    svc: ModelConfigServiceDep,
) -> ModelConfigOut:
    return ModelConfigOut.of(
        await svc.set_default(actor_id=int(manager.user_id), name=name),
        is_default=True,
    )


@router.delete("/models/{name}")
async def delete_model(
    name: str,
    manager: CurrentManagerDep,
    svc: ModelConfigServiceDep,
) -> dict[str, bool]:
    await svc.delete(actor_id=int(manager.user_id), name=name)
    return {"ok": True}
