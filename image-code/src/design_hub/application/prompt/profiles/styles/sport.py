from design_hub.application.prompt.profiles.style_preset import StylePreset
from design_hub.domain.enums import Style

SPORT = StylePreset(
    style=Style.SPORT,
    color_card="电光橙 #ff6b1a + 冷灰 #4a5057 + 黑 #1a1a1a",
    tint_a="冷灰",
    tint_b="炭黑",
    light_color="高对比硬光，冷暖撞色",
    mood="动感机能、力量潮酷",
    modifiers=("动感线条", "机能质感", "潮酷撞色"),
)
