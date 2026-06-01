from pathlib import PurePosixPath
from typing import Annotated

from fastapi import APIRouter, Form, UploadFile

from design_hub.domain.enums import AssetKind
from design_hub.interface.api.deps import UserIdDep
from design_hub.interface.api.project_deps import (
    AssetServiceDep,
    BriefServiceDep,
    ProjectGenerationServiceDep,
)
from design_hub.interface.project_schemas import (
    AssetOut,
    BriefOut,
    BriefUpsert,
    ProjectGenerateRequest,
    ProjectGenerateResponse,
)

# 与 projects.router 同前缀不同子路径；薄控制器，业务在用例内，错误经边界统一映射
router = APIRouter(prefix="/projects", tags=["brief"])


@router.put("/{project_id}/brief", response_model=BriefOut)
async def put_brief(project_id: int, body: BriefUpsert, svc: BriefServiceDep) -> BriefOut:
    return BriefOut.of(
        await svc.put(
            project_id,
            material_types=body.material_types,
            sizes=body.sizes,
            styles=body.styles,
            resolution=body.resolution,
            bleed=body.bleed,
            copy_text=body.copy_text,
            taboo=body.taboo,
            delivery=body.delivery,
        )
    )


@router.get("/{project_id}/brief", response_model=BriefOut)
async def get_brief(project_id: int, svc: BriefServiceDep) -> BriefOut:
    # 项目不存在 / 尚无需求单 → 用例抛 NotFoundError，边界映射 404
    return BriefOut.of(await svc.get(project_id))


@router.post("/{project_id}/assets", response_model=AssetOut)
async def upload_asset(
    project_id: int,
    svc: AssetServiceDep,
    file: UploadFile,
    kind: Annotated[AssetKind, Form()],
) -> AssetOut:
    data = await file.read()
    suffix = PurePosixPath(file.filename or "").suffix or ".png"
    return AssetOut.of(
        await svc.upload(project_id, kind=kind, data=data, suffix=suffix)
    )


@router.get("/{project_id}/assets", response_model=list[AssetOut])
async def list_assets(project_id: int, svc: AssetServiceDep) -> list[AssetOut]:
    return [AssetOut.of(a) for a in await svc.list(project_id)]


@router.post("/{project_id}/generate", response_model=ProjectGenerateResponse)
async def generate_under_project(
    project_id: int,
    body: ProjectGenerateRequest,
    svc: ProjectGenerationServiceDep,
    user_id: UserIdDep = "designer-anon",
) -> ProjectGenerateResponse:
    """项目下出图：合成域 Brief→复用 pipeline→落库挂 project_id+round_no。"""
    outcome = await svc.generate(project_id, body.to_config(), user_id=user_id)
    return ProjectGenerateResponse.of(outcome)
