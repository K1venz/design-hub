from dataclasses import dataclass, field

# 种子片段表：(field, value) -> 注入 prompt 的中文话术。正式文案由 image-prompt 出（ISSUE-0022）。
# 覆盖 ISSUE-0021 用户确认的首版下拉枚举全部取值，否则正常选项会 fail-fast 400。
_SEED_FRAGMENTS: dict[tuple[str, str], str] = {
    # 电商平台（4，收窄国内：去跨境亚马逊/Temu/TikTok→未登记 400，PRD §3.12.11）
    ("platform", "淘宝天猫1688"): "用于淘宝/天猫/1688 电商平台的商品展示图",
    ("platform", "拼多多"): "用于拼多多电商平台的商品展示图",
    ("platform", "京东"): "用于京东电商平台的商品展示图",
    ("platform", "抖音电商"): "用于抖音电商的商品展示图",
    # 国家地区
    ("region", "中国"): "商品面向中国市场",
    ("region", "美国"): "商品面向美国市场",
    ("region", "欧洲"): "商品面向欧洲市场",
    ("region", "俄罗斯"): "商品面向俄罗斯市场",
    ("region", "东南亚"): "商品面向东南亚市场",
    # 语言
    ("language", "英文"): "广告文字使用英文",
    ("language", "中文"): "广告文字使用中文",
    ("language", "俄语"): "广告文字使用俄语",
    ("language", "西语"): "广告文字使用西班牙语",
}


@dataclass
class PromptModifierRegistry:
    """下拉值 → prompt 话术片段（可版本化、可测）。未知值 fail-fast。"""

    fragments: dict[tuple[str, str], str] = field(
        default_factory=lambda: dict(_SEED_FRAGMENTS)
    )

    def fragment(self, field_name: str, value: str) -> str:
        try:
            return self.fragments[(field_name, value)]
        except KeyError:
            raise ValueError(
                f"未知下拉值：{field_name}={value}（未在话术表登记）"
            ) from None


# 花生(FOOD)保真块定稿(#197)：逐字对齐 image-prompt/category-cards/food/peanut.md 的 ```text 块。
# 单一事实源在卡，此处硬编码引用，三方核对保证 code 串==卡串（行长 >100 故隐式拼接，勿改一字）。
_PEANUT_FIDELITY = (
    "包装绝对保真：上传参考图里的产品包装(袋型、配色、白熊图案、袋面所有文字与排版)"
    "100% 原样保留——一个字、一个像素都不改、不重画、不翻译；只重绘包装周围的背景、道具与光线。\n"
    "花生饱满+真实：花生果仁粒大饱满、充实鼓胀、有真实的体积感与重量感，"
    "像刚剥开的新鲜花生那样鼓实有肉；七彩花生米保持紫罗兰/紫红+奶白大理石纹本色、果实白亮。"
    "表面整体哑光干爽、仅极轻微自然油润，严禁糖浆高光/油亮反光/塑料光泽；带壳花生保持土黄硬壳与清晰网状脉络。"
    "饱满≠光滑滚圆：果形自然不规则、有壳尖、深浅不均、表面带细褶皱，不要完美对称光滑圆球；"
    "颗粒大小不一、自然随意散落，允许个别开口带壳露米/双仁。\n"
    "光与镜头：50mm f/2.8 近景浅景深，侧前方自然漫射光勾出果粒饱满体积与凹凸、"
    "柔中带方向性硬阴影、与台面真实接触阴影；前景花生锐利可见脉络。\n"
    "画面禁止：改动/重画/翻译产品包装、塑料感、糖浆高光、油亮反光、干瘪瘦小的花生、"
    "过度鲜艳饱和、完美整齐排列、人物/水印/多余商品。"
)

# 品类 → 保真块（PRD §3.12.11，MVP 只 FOOD/花生；扩品类=加一条，YAGNI）。
_CATEGORY_CARDS: dict[str, str] = {
    "FOOD": _PEANUT_FIDELITY,
}


@dataclass
class CategoryCardRegistry:
    """品类 → 保真块定稿串（PRD §3.12.11）。单一事实源=image-prompt 花生卡；未知品类 fail-fast。"""

    cards: dict[str, str] = field(default_factory=lambda: dict(_CATEGORY_CARDS))

    def card(self, category: str) -> str:
        try:
            return self.cards[category]
        except KeyError:
            raise ValueError(f"未知品类：{category}（未在品类卡表登记）") from None


def compose_prompt(
    prompt: str,
    modifiers: dict[str, str],
    registry: PromptModifierRegistry,
    *,
    category: str,
    card_registry: CategoryCardRegistry,
) -> str:
    """最终 prompt = 品类保真块 + 用户自由文本 + 各 modifier 片段。

    保真块按 category 选（PRD §3.12.11），拼在最前（用户文本/场景/卖点之前，
    QA #196/#198 验过的位置）；未知品类 / 未知下拉值均 fail-fast。
    """
    base = prompt.strip()
    if not base:
        raise ValueError("prompt 不能为空")
    fidelity = card_registry.card(category)
    fragments = [registry.fragment(k, v) for k, v in modifiers.items()]
    body = base if not fragments else base + "。" + "；".join(fragments)
    return fidelity + "\n" + body
