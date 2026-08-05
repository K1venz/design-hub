from design_hub.domain.image_capabilities import image_model_capabilities
from design_hub.domain.tasking import RenderTier


def ratio_to_size(model_id: str, ratio: str) -> tuple[int, int]:
    return image_model_capabilities(model_id).output_for(
        RenderTier.STANDARD, ratio
    ).size


def generation_size(
    model_id: str, render_tier: RenderTier, ratio: str
) -> tuple[int, int]:
    return image_model_capabilities(model_id).output_for(
        render_tier, ratio
    ).size
