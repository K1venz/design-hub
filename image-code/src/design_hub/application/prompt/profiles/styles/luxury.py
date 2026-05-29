from design_hub.application.prompt.profiles.style_preset import StylePreset
from design_hub.domain.enums import Style

LUXURY = StylePreset(
    style=Style.LUXURY,
    color_card="黑金 #1a1a1a + 暖金 #c9a86a + 深红 #6b2020",
    tint_a="深空灰",
    tint_b="墨黑",
    light_color="暖金低调光，明暗对比强",
    mood="高级静奢、精致沉稳",
    modifiers=("精致质感", "克制奢华", "杂志大片感"),
)
