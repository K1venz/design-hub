"""listing 校验矩阵 + 组装序（固化历轮 QA/dev 自查，B-3 门禁 test 步）。"""

import pytest

from design_hub.application.listing.listing_service import build_listing_prompts
from design_hub.application.listing.prompt_composer import (
    CategoryCardRegistry,
    CloneModeRegistry,
    ImageTypeRegistry,
    PromptModifierRegistry,
    compose_clone_prompt,
    compose_prompt,
)

_MR = PromptModifierRegistry()
_CR = CategoryCardRegistry()
_TR = ImageTypeRegistry()
_CL = CloneModeRegistry()
_MODS = {"platform": "抖音电商", "language": "中文"}


def _build(**kw):
    kw.setdefault("n", None)
    kw.setdefault("plan", None)
    return build_listing_prompts(
        "春节红色背景", _MODS, _MR, _CR, _TR, category="FOOD", **kw
    )


@pytest.mark.parametrize(
    "kw",
    [
        {"n": 1, "plan": {"白底": 3}},  # 互斥-都带
        {},  # 互斥-都不带
        {"plan": {"白底": 1, "其他": 2}},  # 未知图型
        {"plan": {"白底": -1, "场景": 4}},  # 负数
        {"plan": {"白底": 1, "场景": 1}},  # Σ<3
        {"plan": {"白底": 4, "场景": 4, "卖点": 4}},  # Σ>10
        {"plan": {"白底": 0, "场景": 0, "卖点": 0}},  # 全 0
        {"plan": {"白底": 2, "场景": 1}, "overlay_texts": ("好",)},  # overlay 无卖点
        {"plan": {"卖点": 3}, "overlay_texts": ("一", "二", "三")},  # overlay 超条数
        {"plan": {"卖点": 3}, "overlay_texts": ("这一条文案明显超过十二个字了吧",)},  # 超字数
        {"plan": {"卖点": 3}, "overlay_texts": ("  ",)},  # 空白
        {"n": 1, "overlay_texts": ("好",)},  # n 流带 overlay
        {"n": 8},  # n 超上限
    ],
)
def test_build_listing_prompts_fail_fast(kw: dict) -> None:
    with pytest.raises(ValueError):
        _build(**kw)


def test_single_mode_no_image_type_block() -> None:
    tasks = _build(n=2)
    assert len(tasks) == 2
    assert all(t is None for t, _ in tasks)
    assert "图型·" not in tasks[0][1]


def test_plan_mode_stable_order_and_blocks() -> None:
    tasks = _build(plan={"白底": 1, "场景": 2, "卖点": 2}, overlay_texts=("高山七彩花生",))
    assert [t for t, _ in tasks] == ["白底", "场景", "场景", "卖点", "卖点"]
    by_type = dict(tasks)
    assert by_type["白底"].startswith("产品绝对保真")  # 保真块在最前
    assert "图型·白底主图" in by_type["白底"]
    assert "「高山七彩花生」" in by_type["卖点"]  # 有字版模板填充
    no_overlay = dict(_build(plan={"白底": 1, "场景": 1, "卖点": 1}))
    assert "带文案" not in no_overlay["卖点"]  # 不填→无字版


def test_compose_prompt_requires_text() -> None:
    with pytest.raises(ValueError):
        compose_prompt("  ", {}, _MR, category="FOOD", card_registry=_CR)


def test_clone_prompt_optional_text_exact_assembly() -> None:
    out = compose_clone_prompt(
        "", {}, _MR, category="FOOD", card_registry=_CR,
        clone_registry=_CL, clone_mode="参考风格",
    )
    from design_hub.application.listing.prompt_composer import _CLONE_REF_STYLE, _FOOD_FIDELITY

    assert out == _FOOD_FIDELITY + "\n" + _CLONE_REF_STYLE  # prompt 空=合法、精确拼接


def test_clone_prompt_order_with_text() -> None:
    out = compose_clone_prompt(
        "要喜庆一点", _MODS, _MR, category="FOOD", card_registry=_CR,
        clone_registry=_CL, clone_mode="高度复刻",
    )
    assert out.index("产品绝对保真") < out.index("复刻·高度复刻") < out.index("要喜庆一点")


@pytest.mark.parametrize("mode", ["半复刻", "", "white_bg"])
def test_clone_mode_fail_fast(mode: str) -> None:
    with pytest.raises(ValueError):
        compose_clone_prompt(
            "", {}, _MR, category="FOOD", card_registry=_CR,
            clone_registry=_CL, clone_mode=mode,
        )


def test_narrowed_enums_fail_fast() -> None:
    for field, value in [
        ("platform", "亚马逊"), ("region", "美国"), ("language", "俄语"),
    ]:
        with pytest.raises(ValueError):
            _MR.fragment(field, value)
    assert _MR.fragment("platform", "淘宝天猫1688")
    assert _MR.fragment("region", "中国")
