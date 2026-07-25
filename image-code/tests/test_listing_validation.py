"""listing 校验矩阵 + 组装序（固化历轮 QA/dev 自查，B-3 门禁 test 步）。"""

import pytest

from design_hub.application.listing.listing_service import build_listing_prompts
from design_hub.application.listing.prompt_composer import (
    CategoryCardRegistry,
    CloneModeRegistry,
    EditModeRegistry,
    ImageTypeRegistry,
    PromptModifierRegistry,
    compose_clone_prompt,
    compose_edit_prompt,
    compose_prompt,
)
from design_hub.application.listing.requests import ListingGenerateRequest
from design_hub.application.listing.sizing import ratio_to_size

_MR = PromptModifierRegistry()
_CR = CategoryCardRegistry()
_TR = ImageTypeRegistry()
_CL = CloneModeRegistry()
_ED = EditModeRegistry()
_MODS = {"platform": "抖音电商", "language": "中文"}


def test_category_is_optional_without_food_fallback() -> None:
    from design_hub.application.listing.prompt_composer import _FOOD_FIDELITY

    req = ListingGenerateRequest(
        upload_ids=["u"], prompt="极简品牌海报", ratio="1:1", n=1
    )
    assert req.category is None

    out = compose_prompt(
        req.prompt,
        {},
        PromptModifierRegistry(),
        category=req.category,
        card_registry=CategoryCardRegistry(),
    )
    assert "参考图是画面主体的唯一事实来源" in out
    assert _FOOD_FIDELITY not in out


def test_explicit_category_keeps_specialized_fidelity() -> None:
    from design_hub.application.listing.prompt_composer import _FOOD_FIDELITY

    out = compose_prompt(
        "清晨场景",
        {},
        PromptModifierRegistry(),
        category="FOOD",
        card_registry=CategoryCardRegistry(),
    )
    assert _FOOD_FIDELITY in out


def _build(**kw):
    kw.setdefault("n", None)
    kw.setdefault("plan", None)
    return build_listing_prompts(
        "春节红色背景", _MODS, _MR, _CR, _TR, category="FOOD", **kw
    )


# 用户可见文案不得泄漏内部字段/schema 名（P3-#5：校验失败信息过用户话术）。
_INTERNAL_TOKENS = ("upload_ids", "overlay_texts", "plan", "modifiers", "ratio", "category")


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
    with pytest.raises(ValueError) as ei:
        _build(**kw)
    msg = str(ei.value)
    for tok in _INTERNAL_TOKENS:
        assert tok not in msg, f"用户可见校验文案泄漏内部字段名 {tok!r}：{msg}"


def test_ratio_to_size_message_is_user_facing() -> None:
    # 无效比例报错=用户话术：含无效值+可选项、不吐内部字段名 "ratio"（P3-#5）。
    with pytest.raises(ValueError) as ei:
        ratio_to_size("5:5")
    msg = str(ei.value)
    assert "5:5" in msg and "1:1" in msg
    assert "ratio" not in msg


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [
        ("1:1", (1024, 1024)),
        ("3:4", (1152, 1536)),
        ("4:3", (1536, 1152)),
        ("9:16", (864, 1536)),
        ("16:9", (1536, 864)),
    ],
)
def test_ratio_to_size_preserves_requested_aspect_ratio(
    ratio: str, expected: tuple[int, int]
) -> None:
    assert ratio_to_size(ratio) == expected


def test_single_mode_no_image_type_block() -> None:
    tasks = _build(n=2)
    assert len(tasks) == 2
    assert all(t is None for t, _ in tasks)
    assert "图型·" not in tasks[0][1]


def test_plan_mode_stable_order_and_blocks() -> None:
    from design_hub.application.listing.prompt_composer import _BASE_REFERENCE_FIDELITY

    tasks = _build(plan={"白底": 1, "场景": 2, "卖点": 2}, overlay_texts=("高山七彩花生",))
    assert [t for t, _ in tasks] == ["白底", "场景", "场景", "卖点", "卖点"]
    by_type = dict(tasks)
    assert by_type["白底"].startswith(_BASE_REFERENCE_FIDELITY)  # 基础保真块在最前
    assert "产品绝对保真" in by_type["白底"]  # 显式 FOOD 继续叠加专项保真
    assert "图型·白底主图" in by_type["白底"]
    assert "「高山七彩花生」" in by_type["卖点"]  # 有字版模板填充
    no_overlay = dict(_build(plan={"白底": 1, "场景": 1, "卖点": 1}))
    assert "带文案" not in no_overlay["卖点"]  # 不填→无字版


def test_white_bg_strips_user_styling_scene_selling_keep() -> None:
    from design_hub.application.listing.prompt_composer import _BASE_REFERENCE_FIDELITY

    # ISSUE-0052 档A：白底剥离用户自由文本(prompt='春节红色背景'=强场景/背景描述)，
    # 场景/卖点保留；白底仍保 保真块 + 白底卡块 + modifiers。
    tasks = _build(plan={"白底": 1, "场景": 1, "卖点": 1})
    by_type = dict(tasks)
    white = by_type["白底"]
    assert "春节红色背景" not in white  # 白底剥离用户场景文本（防污染纯白背景）
    assert white.startswith(_BASE_REFERENCE_FIDELITY)  # 基础保真块保留、在最前
    assert "产品绝对保真" in white  # 显式 FOOD 专项保真仍保留
    assert "图型·白底主图" in white  # 白底卡块保留
    assert "抖音电商" in white  # modifiers（平台/语言）保留
    assert "春节红色背景" in by_type["场景"]  # 场景不受损
    assert "春节红色背景" in by_type["卖点"]  # 卖点不受损


def test_compose_prompt_requires_text() -> None:
    with pytest.raises(ValueError):
        compose_prompt("  ", {}, _MR, category="FOOD", card_registry=_CR)


def test_clone_prompt_optional_text_exact_assembly() -> None:
    out = compose_clone_prompt(
        "", {}, _MR, category="FOOD", card_registry=_CR,
        clone_registry=_CL, clone_mode="参考风格",
    )
    from design_hub.application.listing.prompt_composer import (
        _BASE_REFERENCE_FIDELITY,
        _CLONE_REF_STYLE,
        _FOOD_FIDELITY,
    )

    assert out == (
        _BASE_REFERENCE_FIDELITY + "\n" + _FOOD_FIDELITY + "\n" + _CLONE_REF_STYLE
    )  # prompt 空=合法、基础保真→专项保真→复刻档


def test_clone_prompt_order_with_text() -> None:
    out = compose_clone_prompt(
        "要喜庆一点", _MODS, _MR, category="FOOD", card_registry=_CR,
        clone_registry=_CL, clone_mode="完全复刻",
    )
    assert out.index("产品绝对保真") < out.index("复刻·完全复刻") < out.index("要喜庆一点")


@pytest.mark.parametrize("mode", ["半复刻", "", "white_bg"])
def test_clone_mode_fail_fast(mode: str) -> None:
    with pytest.raises(ValueError):
        compose_clone_prompt(
            "", {}, _MR, category="FOOD", card_registry=_CR,
            clone_registry=_CL, clone_mode=mode,
        )


def test_edit_prompt_exact_assembly_no_category_block() -> None:
    from design_hub.application.listing.prompt_composer import _EDIT_FULL

    out = compose_edit_prompt("换成节日场景", {}, _MR, edit_registry=_ED, edit_mode="full")
    assert out == _EDIT_FULL + "\n" + "换成节日场景"  # 无品类块/图型卡/父 prompt，精确拼接


def test_edit_prompt_order_with_modifiers() -> None:
    out = compose_edit_prompt("背景换厨房", _MODS, _MR, edit_registry=_ED, edit_mode="delta")
    assert out.index("编辑·微调") < out.index("背景换厨房") < out.index("用于抖音电商")


def test_edit_prompt_requires_text() -> None:
    with pytest.raises(ValueError):
        compose_edit_prompt("  ", {}, _MR, edit_registry=_ED, edit_mode="delta")


@pytest.mark.parametrize("mode", ["半改", "", "DELTA", "微调"])
def test_edit_mode_fail_fast(mode: str) -> None:
    with pytest.raises(ValueError):
        compose_edit_prompt("改背景", {}, _MR, edit_registry=_ED, edit_mode=mode)


def test_narrowed_enums_fail_fast() -> None:
    for field, value in [
        ("platform", "亚马逊"), ("region", "美国"), ("language", "俄语"),
    ]:
        with pytest.raises(ValueError):
            _MR.fragment(field, value)
    assert _MR.fragment("platform", "淘宝天猫1688")
    assert _MR.fragment("region", "中国")
