import pytest

from design_hub.application.chat.ratio_intent import (
    ChatRatioSource,
    UnsupportedChatRatio,
    decide_chat_ratio,
)


@pytest.mark.parametrize("text", ["做横版主图", "生成一张横图", "改成横向构图"])
def test_landscape_wording_maps_to_four_by_three(text: str) -> None:
    decision = decide_chat_ratio(text, "1:1")

    assert decision.ratio == "4:3"
    assert decision.source is ChatRatioSource.ORIENTATION
    assert decision.changes_edit_ratio is True


def test_explicit_supported_ratio_overrides_landscape_and_upload() -> None:
    decision = decide_chat_ratio("做横版 16:9 主图", "3:4")

    assert decision.ratio == "16:9"
    assert decision.source is ChatRatioSource.EXPLICIT


def test_upload_ratio_is_used_without_text_ratio() -> None:
    decision = decide_chat_ratio("做一张高级主图", "4:3")

    assert decision.ratio == "4:3"
    assert decision.source is ChatRatioSource.AUTO
    assert decision.changes_edit_ratio is False


@pytest.mark.parametrize("text", ["按 4x3 出图", "按 4×3 出图", "按 4比3 出图"])
def test_accepts_common_explicit_ratio_separators(text: str) -> None:
    decision = decide_chat_ratio(text, "1:1")

    assert decision.ratio == "4:3"
    assert decision.source is ChatRatioSource.EXPLICIT


def test_unsupported_explicit_ratio_is_preserved_as_user_facing_error() -> None:
    decision = decide_chat_ratio("按 2:3 出图", "1:1")

    with pytest.raises(UnsupportedChatRatio, match="1:1 / 3:2 / 3:4 / 4:3 / 9:16 / 16:9"):
        decision.require_supported()


def test_invalid_auto_ratio_fails_fast() -> None:
    with pytest.raises(ValueError, match="无效自动比例"):
        decide_chat_ratio("做一张主图", "2:3")


@pytest.mark.parametrize("separator", ["x", "X", "×"])
def test_four_k_resolution_is_ignored_by_standard_ratio_parser(separator: str) -> None:
    decision = decide_chat_ratio(f"生成 3840{separator}2160 图片", "3:4")

    assert decision.ratio == "3:4"
    assert decision.source is ChatRatioSource.AUTO
