from design_hub.domain.gpt_image_2 import gpt_image_2_contract
from design_hub.domain.tasking import RenderTier


def ratio_to_size(ratio: str) -> tuple[int, int]:
    return gpt_image_2_contract(RenderTier.STANDARD).size_for_ratio(ratio)


def generation_size(render_tier: RenderTier, ratio: str) -> tuple[int, int]:
    return gpt_image_2_contract(render_tier).size_for_ratio(ratio)
