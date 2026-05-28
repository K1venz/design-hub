from fastapi import APIRouter

from design_hub.interface.api.deps import EngineDep, UserIdDep
from design_hub.interface.schemas import (
    CostPreviewResponse,
    GenerateRequest,
    GenerateResponse,
)

router = APIRouter(prefix="/generate", tags=["generation"])


@router.post("", response_model=GenerateResponse)
async def generate(
    req: GenerateRequest,
    engine: EngineDep,
    user_id: UserIdDep = "designer-anon",
) -> GenerateResponse:
    """出图：薄控制器，只做 HTTP↔用例 翻译，业务在 pipeline 内。"""
    result = await engine.pipeline.run(req.to_brief(), user_id=user_id)
    return GenerateResponse.from_result(result)


@router.post("/cost-preview", response_model=CostPreviewResponse)
async def cost_preview(
    req: GenerateRequest,
    engine: EngineDep,
    user_id: UserIdDep = "designer-anon",
) -> CostPreviewResponse:
    """出图前成本预估（PRD §3.10），只读不预扣。"""
    preview = await engine.preview.preview(req.to_brief(), user_id)
    return CostPreviewResponse.from_preview(preview)
