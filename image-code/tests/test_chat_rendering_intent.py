import pytest

from design_hub.application.chat.rendering_intent import (
    ChatRenderingConflict,
    decide_chat_rendering,
)
from design_hub.domain.enums import ModelName


@pytest.mark.parametrize(
    "message",
    ["生成一张 4K 图", "做成 4 k", "超高清4K海报", "生成 3840×2160 图片"],
)
def test_explicit_4k_generation_selects_4k(message: str) -> None:
    decision = decide_chat_rendering(message, auto_ratio="1:1")

    assert decision.model is ModelName.GPT_IMAGE_2_4K
    assert decision.ratio.ratio == "16:9"


@pytest.mark.parametrize(
    "message",
    ["生成高清图片", "不要4K，生成横版", "无需 4 k，按 1:1 生成"],
)
def test_vague_or_negated_4k_stays_standard(message: str) -> None:
    assert decide_chat_rendering(message, "1:1").model is ModelName.GPT_IMAGE_2


@pytest.mark.parametrize("ratio", ["1:1", "3:4", "4:3", "9:16"])
def test_4k_conflicting_ratio_is_rejected_before_cost_confirm(ratio: str) -> None:
    with pytest.raises(ChatRenderingConflict, match="4K 当前仅支持 16:9 横版"):
        decide_chat_rendering(f"生成 4K，比例 {ratio}", auto_ratio="1:1")


def test_explicit_4k_accepts_explicit_sixteen_by_nine() -> None:
    decision = decide_chat_rendering("生成 4K，比例 16:9", auto_ratio="3:4")

    assert decision.model is ModelName.GPT_IMAGE_2_4K
    assert decision.ratio.ratio == "16:9"


def test_four_k_resolution_is_not_treated_as_an_unsupported_ratio() -> None:
    decision = decide_chat_rendering("生成 3840x2160 图片", auto_ratio="3:4")

    assert decision.model is ModelName.GPT_IMAGE_2_4K
    assert decision.ratio.require_supported() == "16:9"
