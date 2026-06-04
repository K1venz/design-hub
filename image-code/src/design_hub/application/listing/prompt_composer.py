from dataclasses import dataclass, field

# 种子片段表：(field, value) -> 注入 prompt 的中文话术。正式文案由 image-prompt 出（ISSUE-0022）。
# 覆盖 ISSUE-0021 用户确认的首版下拉枚举全部取值，否则正常选项会 fail-fast 400。
_SEED_FRAGMENTS: dict[tuple[str, str], str] = {
    # 电商平台
    ("platform", "亚马逊"): "用于亚马逊电商平台的商品展示图",
    ("platform", "淘宝天猫1688"): "用于淘宝/天猫/1688 电商平台的商品展示图",
    ("platform", "拼多多"): "用于拼多多电商平台的商品展示图",
    ("platform", "京东"): "用于京东电商平台的商品展示图",
    ("platform", "Temu"): "用于 Temu 跨境电商平台的商品展示图",
    ("platform", "TikTok Shop"): "用于 TikTok Shop 电商的商品展示图",
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


def compose_prompt(
    prompt: str, modifiers: dict[str, str], registry: PromptModifierRegistry
) -> str:
    """最终 prompt = 用户自由文本 + 各 modifier 片段拼接（用户文本为主体）。"""
    base = prompt.strip()
    if not base:
        raise ValueError("prompt 不能为空")
    fragments = [registry.fragment(k, v) for k, v in modifiers.items()]
    if not fragments:
        return base
    return base + "。" + "；".join(fragments)
