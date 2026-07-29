from typing import cast

from fastapi import APIRouter, Request

from design_hub.application.image_prompts.reverse_prompt import (
    ReversePromptRequest,
    ReversePromptResult,
    ReversePromptService,
)
from design_hub.interface.api.deps import CurrentUserDep

router = APIRouter(prefix="/image-prompts", tags=["image-prompts"])


def _service(request: Request) -> ReversePromptService:
    return cast(
        ReversePromptService,
        request.app.state.reverse_prompt_service,
    )


@router.post("/reverse", response_model=ReversePromptResult)
async def reverse_image_prompt(
    req: ReversePromptRequest,
    request: Request,
    user: CurrentUserDep,
) -> ReversePromptResult:
    return await _service(request).reverse(
        user_id=user.user_id,
        request=req,
    )
