from dataclasses import dataclass

from design_hub.domain.enums import Style


@dataclass(frozen=True)
class StylePreset:
    """风格预设（调性/色彩）：什么审美。AI 起草→人工定稿→冻结固定库。"""

    style: Style
    color_card: str  # 色卡 HEX
    tint_a: str  # 浅色A（背景渐变起）
    tint_b: str  # 浅色B（背景渐变止）
    light_color: str  # 光色/色温情绪
    mood: str  # 情绪基调（氛围词）
    modifiers: tuple[str, ...]  # 修饰风格词
