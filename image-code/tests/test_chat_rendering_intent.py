import pytest

from design_hub.application.chat.ratio_intent import UnsupportedChatRatio
from design_hub.application.chat.rendering_intent import (
    ChatRenderingConflict,
    decide_chat_ratio_note,
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
    [
        "生成高清图片",
        "不要4K，生成横版",
        "不要生成 4K 图，按 4:3 生成",
        "不需要做成 4K，按 1:1 生成",
        "不用改成 4K，按 3:4 生成",
        "别用 4K，按 4:3 生成",
        "这不是 4K，按 9:16 生成",
        "无需 4 k，按 1:1 生成",
    ],
)
def test_vague_or_negated_4k_stays_standard(message: str) -> None:
    assert decide_chat_rendering(message, "1:1").model is ModelName.GPT_IMAGE_2


def test_positive_4k_clause_is_not_vetoed_by_a_separate_negated_clause() -> None:
    decision = decide_chat_rendering(
        "不要生成 4K 草稿，最终生成 4K 成品",
        auto_ratio="1:1",
    )

    assert decision.model is ModelName.GPT_IMAGE_2_4K
    assert decision.ratio.ratio == "16:9"


def test_negated_clause_with_duplicate_4k_tokens_stays_standard() -> None:
    decision = decide_chat_rendering(
        "不要生成 4K（3840×2160）图片，按 4:3 生成普通图",
        auto_ratio="1:1",
    )

    assert decision.model is ModelName.GPT_IMAGE_2
    assert decision.ratio.ratio == "4:3"


def test_4k_ratio_ignores_ratio_from_a_negated_clause() -> None:
    decision = decide_chat_rendering(
        "不要 4K 4:3 草稿，最终生成 4K 16:9 成品",
        auto_ratio="1:1",
    )

    assert decision.model is ModelName.GPT_IMAGE_2_4K
    assert decision.ratio.ratio == "16:9"


@pytest.mark.parametrize(
    "message",
    [
        "不要生成 4K 草稿但最终生成 4K 成品",
        "不要生成 4K 草稿但是最终生成 4K 成品",
        "不要生成 4K 草稿不过最终生成 4K 成品",
        "不要生成 4K 草稿然而最终生成 4K 成品",
        "不要生成 4K 草稿而是最终生成 4K 成品",
    ],
)
def test_contrast_clause_preserves_the_later_positive_4k_request(message: str) -> None:
    decision = decide_chat_rendering(message, auto_ratio="1:1")

    assert decision.model is ModelName.GPT_IMAGE_2_4K
    assert decision.ratio.ratio == "16:9"


def test_4k_ratio_ignores_ratio_before_an_unpunctuated_contrast() -> None:
    decision = decide_chat_rendering(
        "不要 4K 4:3 草稿但最终生成 4K 16:9 成品",
        auto_ratio="1:1",
    )

    assert decision.model is ModelName.GPT_IMAGE_2_4K
    assert decision.ratio.ratio == "16:9"


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


def test_4k_with_unsupported_ratio_preserves_supported_ratio_message() -> None:
    decision = decide_chat_rendering("生成 4K，比例 2:3", auto_ratio="1:1")

    assert decision.model is ModelName.GPT_IMAGE_2_4K
    with pytest.raises(
        UnsupportedChatRatio,
        match="当前支持的图片比例是 1:1 / 3:4 / 4:3 / 9:16 / 16:9",
    ):
        decision.ratio.require_supported()


def test_explicit_4k_ratio_note_is_sixteen_by_nine_before_tool_selection() -> None:
    decision = decide_chat_ratio_note("生成 4K，比例 4:3", auto_ratio="1:1")

    assert decision.ratio == "16:9"
