from dataclasses import dataclass, field

# 种子片段表：(field, value) -> 注入 prompt 的中文话术。正式文案由 image-prompt 出（ISSUE-0022）。
# 覆盖 ISSUE-0021 用户确认的首版下拉枚举全部取值，否则正常选项会 fail-fast 400。
_SEED_FRAGMENTS: dict[tuple[str, str], str] = {
    # 电商平台（4，收窄国内：去跨境亚马逊/Temu/TikTok→未登记 400，PRD §3.12.11）
    ("platform", "淘宝天猫1688"): "用于淘宝/天猫/1688 电商平台的商品展示图",
    ("platform", "拼多多"): "用于拼多多电商平台的商品展示图",
    ("platform", "京东"): "用于京东电商平台的商品展示图",
    ("platform", "抖音电商"): "用于抖音电商的商品展示图",
    # 国家地区（收窄：花生=中国方向，仅留中国；前端固定发 region=中国，PRD §3.12.12）
    ("region", "中国"): "商品面向中国市场",
    # 语言（收窄：仅中文/英文，默认中文，PRD §3.12.12）
    ("language", "中文"): "广告文字使用中文",
    ("language", "英文"): "广告文字使用英文",
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


# FOOD 通用产品保真块（产品中性，#366 修「万物皆花生」）：逐字对齐
# image-prompt/category-cards/food/通用.md 的 ```text 块（行长 >100 故隐式拼接，勿改一字）。
# 单一事实源在卡、此处硬编码引用、三方核对 code 串==卡串；花生专属卡降级 backlog(food/peanut.md)。
_FOOD_FIDELITY = (
    "产品绝对保真：上传参考图里的产品（外形、结构、材质、配色、图案、品牌标识、包装上所有文字与排版）"
    "100% 原样保留——一个字、一个像素都不改、不重画、不翻译；"
    "只重绘产品周围的背景、衬托道具与光线。\n"
    "真实质感：严格按产品本身的真实材质表现质感（金属有金属光、塑料有塑料面、织物有布纹、"
    "食品有食品的自然光泽），不套用统一的假高光；表面真实、干爽、自然，"
    "严禁糖浆般高光/油亮反光/塑料假光泽与过度修图，保留材质本身的细微不均与真实细节。\n"
    "光与镜头：50mm f/2.8 近景浅景深，侧前方自然漫射光勾出产品的体积与凹凸、"
    "柔中带方向性硬阴影、与台面真实接触阴影；前景主体锐利、质感清晰。\n"
    "背景与道具：干净、得体、与产品调性相符的简洁背景与少量衬托道具，只为衬托产品、不喧宾夺主；"
    "严禁堆砌与产品无关的道具、食材或物件，不要无故出现与该产品无关的食物/植物/杂物。\n"
    "画面禁止：改动/重画/翻译产品本体与包装文字、塑料假高光、油亮反光、过度鲜艳饱和、"
    "堆砌与产品无关的道具/食材/物件、完美整齐的摆拍排列、人物/水印/多余文字。"
)

# 品类 → 保真块（PRD §3.12.11/12，MVP 只 FOOD 通用块；扩品类/产品级专属卡=加一条，YAGNI）。
_CATEGORY_CARDS: dict[str, str] = {
    "FOOD": _FOOD_FIDELITY,
}


@dataclass
class CategoryCardRegistry:
    """品类 → 保真块（PRD §3.12.11/12）。单一事实源=image-prompt 品类卡；未知品类 fail-fast。"""

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
