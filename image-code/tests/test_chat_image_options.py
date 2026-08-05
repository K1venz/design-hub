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


def test_four_k_options_are_fixed_to_one_landscape_image() -> None:
    options = ChatImageOptions(
        render_tier=ChatRenderTier.FOUR_K,
        ratio="16:9",
        count=1,
    )
    decision = decide_chat_rendering("生成海报", auto_ratio="3:4", options=options)

    assert decision.render_tier is RenderTier.FOUR_K
    assert decision.ratio.ratio == "16:9"


@pytest.mark.parametrize(
    ("ratio", "count"),
    [("3:4", 1), ("16:9", 2)],
)
def test_invalid_four_k_options_fail_fast(ratio: str, count: int) -> None:
    with pytest.raises(ValueError):
        ChatImageOptions(
            render_tier=ChatRenderTier.FOUR_K,
            ratio=ratio,
            count=count,
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
