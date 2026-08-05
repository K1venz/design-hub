import pytest

from design_hub.application.chat.image_options import ChatImageOptions, ChatRenderTier
from design_hub.application.chat.ratio_intent import (
    ChatRatioDecision,
    ChatRatioSource,
)
from design_hub.application.chat.rendering_intent import (
    ChatRenderingContext,
    ChatRenderingDecision,
    SelectedChatImageOptionsDecorator,
    decide_chat_rendering,
)
from design_hub.domain.tasking import RenderTier


def test_standard_options_override_a_4k_phrase_and_ratio() -> None:
    decision = decide_chat_rendering(
        "生成 4K 竖版图片",
        auto_ratio="1:1",
        options=ChatImageOptions(
            render_tier=ChatRenderTier.STANDARD,
            ratio="3:4",
            count=3,
        ),
    )

    assert decision.render_tier is RenderTier.STANDARD
    assert decision.ratio.ratio == "3:4"


def test_standard_auto_ratio_still_understands_the_prompt() -> None:
    decision = decide_chat_rendering(
        "生成横版商品图",
        auto_ratio="1:1",
        options=ChatImageOptions(
            render_tier=ChatRenderTier.STANDARD,
            ratio="auto",
            count=None,
        ),
    )

    assert decision.ratio.ratio == "4:3"


def test_four_k_options_are_fixed_to_landscape_and_allow_platform_batch_count() -> None:
    options = ChatImageOptions(
        render_tier=ChatRenderTier.FOUR_K,
        ratio="16:9",
        count=7,
    )
    decision = decide_chat_rendering("生成海报", auto_ratio="3:4", options=options)

    assert decision.render_tier is RenderTier.FOUR_K
    assert decision.ratio.ratio == "16:9"


def test_invalid_count_fails_fast() -> None:
    with pytest.raises(ValueError):
        ChatImageOptions(
            render_tier=ChatRenderTier.FOUR_K,
            ratio="16:9",
            count=8,
        )


def test_gpt_four_k_rejects_ratio_outside_its_model_contract() -> None:
    with pytest.raises(ValueError, match="16:9"):
        ChatImageOptions(
            render_tier=ChatRenderTier.FOUR_K,
            ratio="3:4",
            count=1,
        ).validate_for(
            model_id="gpt-image-2",
            render_tier=RenderTier.FOUR_K,
            resolved_ratio="3:4",
            resolved_count=1,
        )


@pytest.mark.parametrize(
    "ratio",
    ["1:1", "3:2", "2:3", "3:4", "4:3", "9:16", "16:9", "4:5", "5:4", "1:2", "2:1"],
)
def test_gpt_image_2_standard_accepts_live_verified_chat_ratios(ratio: str) -> None:
    ChatImageOptions(
        render_tier=ChatRenderTier.STANDARD,
        ratio=ratio,
        count=3,
    ).validate_for(
        model_id="gpt-image-2",
        render_tier=RenderTier.STANDARD,
        resolved_ratio=ratio,
        resolved_count=3,
    )


def test_gpt_image_2_standard_rejects_unverified_chat_ratio() -> None:
    with pytest.raises(ValueError, match="21:9"):
        ChatImageOptions(
            render_tier=ChatRenderTier.STANDARD,
            ratio="21:9",
            count=1,
        ).validate_for(
            model_id="gpt-image-2",
            render_tier=RenderTier.STANDARD,
            resolved_ratio="21:9",
            resolved_count=1,
        )


def test_gpt_image_2_four_k_accepts_seven_results_at_fixed_ratio() -> None:
    ChatImageOptions(
        render_tier=ChatRenderTier.FOUR_K,
        ratio="16:9",
        count=7,
    ).validate_for(
        model_id="gpt-image-2",
        render_tier=RenderTier.FOUR_K,
        resolved_ratio="16:9",
        resolved_count=7,
    )


def test_nano_banana_accepts_two_k_four_by_five() -> None:
    options = ChatImageOptions(
        render_tier=ChatRenderTier.TWO_K,
        ratio="4:5",
        count=1,
    )

    options.validate_for(
        model_id="nano-banana-2",
        render_tier=RenderTier.TWO_K,
        resolved_ratio="4:5",
        resolved_count=1,
    )


def test_gpt_image_2_rejects_two_k() -> None:
    options = ChatImageOptions(
        render_tier=ChatRenderTier.TWO_K,
        ratio="4:5",
        count=1,
    )

    with pytest.raises(ValueError, match="2k"):
        options.validate_for(
            model_id="gpt-image-2",
            render_tier=RenderTier.TWO_K,
            resolved_ratio="4:5",
            resolved_count=1,
        )


class _StubRenderingResolver:
    def __init__(self) -> None:
        self.resolve_calls = 0
        self.note_calls = 0

    def resolve(self, context: ChatRenderingContext) -> ChatRenderingDecision:
        self.resolve_calls += 1
        return ChatRenderingDecision(
            RenderTier.STANDARD,
            ChatRatioDecision("1:1", ChatRatioSource.AUTO),
        )

    def ratio_note(self, context: ChatRenderingContext) -> ChatRatioDecision:
        self.note_calls += 1
        return ChatRatioDecision("1:1", ChatRatioSource.AUTO)


def test_auto_options_decorator_delegates_to_wrapped_resolver() -> None:
    wrapped = _StubRenderingResolver()
    decorator = SelectedChatImageOptionsDecorator(
        wrapped=wrapped,
        options=ChatImageOptions(
            render_tier=ChatRenderTier.AUTO,
            ratio="auto",
            count=None,
        ),
    )
    context = ChatRenderingContext(message="生成商品图", auto_ratio="1:1")

    assert decorator.resolve(context).ratio.ratio == "1:1"
    assert decorator.ratio_note(context).ratio == "1:1"
    assert wrapped.resolve_calls == 1
    assert wrapped.note_calls == 1


def test_explicit_options_decorator_enhances_wrapped_decision() -> None:
    wrapped = _StubRenderingResolver()
    decorator = SelectedChatImageOptionsDecorator(
        wrapped=wrapped,
        options=ChatImageOptions(
            render_tier=ChatRenderTier.STANDARD,
            ratio="3:4",
            count=3,
        ),
    )
    context = ChatRenderingContext(message="生成商品图", auto_ratio="1:1")

    decision = decorator.resolve(context)

    assert decision.render_tier is RenderTier.STANDARD
    assert decision.ratio.ratio == "3:4"
